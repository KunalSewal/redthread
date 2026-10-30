"""Map a bank's schema onto RedThread's target model, and score the mapper (challenge 13).

    python scripts/schema_map.py map test_schema/*.gsql     # propose and check a mapping per schema
    python scripts/schema_map.py eval test_schema/*.gsql    # ...and score it against the file's own key

``map`` strips every comment, parses the schema, has the model propose a mapping with a reason for each
choice, and checks it against the schema (redthread.schemamap). Results: runs/schema_map/<graph>.json.

``eval`` also reads the "Expected mapping (ground truth)" block the organisers wrote into each test
file, which the mapper never sees, and scores every concept, relation and attribute: right (the key's
schema elements are all in ours), partial (some are), wrong, or a disagreement about whether it maps
at all. Results: data/processed/schema_map_eval.json.
"""

import asyncio
import json
import re
import sys
from pathlib import Path

from redthread import paths
from redthread.schemamap import ATTRIBUTES, CONCEPTS, RELATIONS, Schema, parse_gsql, propose

OUT = paths.ROOT / "runs" / "schema_map"
EVAL = paths.PROCESSED / "schema_map_eval.json"
TRUTH_LINE = re.compile(r"^#\s{3}(\S.*?)\s+(exact|approximate|unmapped)\b\s*(.*)$")


def ground_truth(text: str) -> dict[str, dict]:
    """The key written in the file's comments: item -> {confidence, text}. Read only to score."""
    block = text.split("Expected mapping (ground truth):", 1)[-1].split("\nCREATE", 1)[0]
    truth, last = {}, None
    for line in block.splitlines():
        m = TRUTH_LINE.match(line)
        if m:
            for name in (n.strip() for n in m.group(1).split(",")):
                truth[name] = {"confidence": m.group(2), "text": m.group(3)}
            last = [n.strip() for n in m.group(1).split(",")]
        elif last and line.startswith("#") and line[1:].strip():
            for name in last:
                truth[name]["text"] += " " + line[1:].strip()
    return truth


def _names(schema: Schema) -> set[str]:
    names = set(schema.vertices) | set(schema.edges) | {e.reverse for e in schema.edges.values() if e.reverse}
    for v in schema.vertices.values():
        names |= set(v.attributes)
    for e in schema.edges.values():
        names |= set(e.attributes)
    return names


def _base(name: str, schema: Schema) -> str:
    """A reverse edge is its base edge walked the other way: the same element of the schema."""
    for e in schema.edges.values():
        if e.reverse == name:
            return e.name
    return name


def key_elements(text: str, names: set[str], schema: Schema) -> set[str]:
    """Schema elements the key names as the answer: parenthesised asides ('(not STMT_ENTRY)',
    '(InstdAmt is the pre-FX amount)') are explanations, not the answer."""
    text = re.sub(r"\([^)]*\)", " ", text)
    return {_base(t, schema) for t in re.findall(r"[A-Za-z_][\w]*", text) if t in names}


def our_elements(item: dict, names: set[str], schema: Schema) -> set[str]:
    """Our mapping's schema elements, including the vertex types each edge path passes through (a key
    may describe a path by its vertices rather than its edges)."""
    paths = [*item.get("paths", []), *([{"edges": item["path"], "filter": ""}] if item.get("path") else [])]
    sources = [*item.get("sources", []), *([item["source"]] if item.get("source") else [])]
    passed = [v for p in paths for e in p["edges"] for pair in schema.hop(e) for v in pair]
    blob = " ".join([*item.get("vertices", []), *(e for p in paths for e in p["edges"]), *passed,
                     *(p.get("filter", "") for p in paths), *(s.replace(".", " ") for s in sources),
                     item.get("filter", ""), item.get("transform", "")])
    return {_base(t, schema) for t in re.findall(r"[A-Za-z_][\w]*", blob) if t in names}


def score(result: dict, schema: Schema, truth: dict) -> dict:
    names = _names(schema)
    ours = {**{c["concept"]: c for c in result["mapping"]["concepts"]},
            **{r["relation"]: r for r in result["mapping"]["relations"]},
            **{a["attribute"]: a for a in result["mapping"]["attributes"]}}
    rows = []
    for item, key in truth.items():
        mine = ours.get(item)
        if mine is None:
            rows.append({"item": item, "verdict": "missing", "key": key["confidence"]})
            continue
        key_unmapped, my_unmapped = key["confidence"] == "unmapped", mine["confidence"] == "unmapped"
        want, got = key_elements(key["text"], names, schema), our_elements(mine, names, schema)
        if key_unmapped or my_unmapped:
            verdict = "right" if key_unmapped == my_unmapped else "wrong"
        elif want and want <= got:
            verdict = "right"
        elif want & got:
            verdict = "partial"
        else:
            verdict = "wrong"
        rows.append({"item": item, "verdict": verdict, "key": key["confidence"], "ours": mine["confidence"],
                     "key_elements": sorted(want), "our_elements": sorted(got), "reason": mine.get("reason", "")})
    count = {v: sum(r["verdict"] == v for r in rows) for v in ("right", "partial", "wrong", "missing")}
    same_conf = sum(1 for r in rows if r.get("ours") == r["key"])
    return {"graph": schema.graph, "items": len(rows), **count, "confidence_agrees": same_conf, "rows": rows}


async def main(cmd: str, files: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    reports = []
    for f in files:
        text = Path(f).read_text(encoding="utf-8")
        schema = parse_gsql(text)  # comments are stripped inside: the key never reaches the mapper
        saved = OUT / f"{schema.graph}.json"
        if cmd == "rescore":  # score the mapping already made, without asking the model again
            result = json.loads(saved.read_text(encoding="utf-8"))
        else:
            result = await propose(schema)
            saved.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"{schema.graph}: {len(result['first_round_problems'])} problem(s) found by the check in round 1, "
              f"{len(result['problems'])} left after {result['rounds']} round(s)")
        for p in result["problems"]:
            print(f"   rejected: {p}")
        if cmd in ("eval", "rescore"):
            s = score(result, schema, ground_truth(text))
            reports.append(s)
            print(f"   scored on {s['items']} items: {s['right']} right, {s['partial']} partial, {s['wrong']} wrong, "
                  f"{s['missing']} missing; confidence agrees on {s['confidence_agrees']}")
            for r in s["rows"]:
                if r["verdict"] != "right":
                    print(f"     {r['verdict']:8} {r['item']:28} key {r.get('key_elements')} "
                          f"ours {r.get('our_elements')}")
    if reports:
        total = {k: sum(r[k] for r in reports) for k in ("items", "right", "partial", "wrong", "missing",
                                                        "confidence_agrees")}
        EVAL.write_text(json.dumps({"total": total, "target_model": {"concepts": list(CONCEPTS),
                                    "relations": list(RELATIONS), "attributes": list(ATTRIBUTES)},
                                    "schemas": reports}, indent=1), encoding="utf-8")
        print("total", total)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("map", "eval", "rescore"):
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
