"""Fill every measured number in README.md from the files that hold it, so the two cannot disagree.

    python scripts/fill_readme.py           # rewrite the marked spans in README.md
    python scripts/fill_readme.py --check   # exit 1 if README.md is out of date (the gate runs this)

Each number lives between ``<!-- numbers:NAME -->`` and ``<!-- /numbers -->``; the text around them
is written by hand. A missing source file leaves its span saying so, rather than keeping a stale figure.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SPAN = re.compile(r"(<!-- numbers:(\w+) -->)(.*?)(<!-- /numbers -->)", re.S)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _answers() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "cases").glob("HHF-*.json"))]


def headline() -> str:
    a = _answers()
    v = [x["case"]["verdict"] for x in a]
    gate = _read(ROOT / "runs" / "gate.json") or {}
    grader = next((r for r in gate.get("results", []) if r.get("check") == "official grader"), None)
    graded = (f"the organisers' grader finds **{grader['hard']}** hard and **{grader['policy']}** policy problems"
              if grader else "the organisers' grader has not been run on these answers")
    return (f"**{len(a)} / 18** final-round cases answered: **{v.count('fraud')}** fraud, "
            f"**{v.count('uncertain')}** uncertain, **{v.count('legitimate')}** legitimate; {graded}")


def ablation() -> str:
    rows = _read(ROOT / "runs" / "ablation.json")
    if not rows:
        return "\n_No ablation has been run (`python scripts/ablation.py`)._\n"
    names = {"full": "As submitted", "no_detectors": "Without the new detectors",
             "old_priors": "With Round 1's priors", "neither": "Without either"}
    lines = ["", "| Recomputed from each answer's own ledger | Fraud | Uncertain | Legitimate |", "|---|---|---|---|"]
    for k, label in names.items():
        c = [sum(1 for r in rows if r["verdict"][k] == x) for x in ("fraud", "uncertain", "legitimate")]
        lines.append(f"| {label} | {c[0]} | {c[1]} | {c[2]} |")
    return "\n".join(lines) + "\n"


def detectors() -> str:
    d = _read(ROOT / "data" / "processed" / "detector_backtest.json")
    if not d:
        return "_not yet backtested_"
    s = d["summary"]["new_kind_run"]
    return (f"on all {d['cases']:,} closed cases the run detector fired on {s['confirmed_fraud_caught']} of "
            f"{s['of_confirmed']:,} confirmed frauds ({s['confirmed_fraud_caught'] / s['of_confirmed']:.1%}) and "
            f"{s['cleared_customers_acted_against']} of {s['of_cleared']} cleared alerts "
            f"({s['cleared_customers_acted_against'] / s['of_cleared']:.1%})")


def drills() -> str:
    d = _read(ROOT / "runs" / "drills.json")
    if not d:
        return "\n_No drills have been run (`python scripts/drills.py`)._\n"
    label = {"dependency_fails": "The graph connection drops mid-run", "model_timeout": "The model times out",
             "model_garbage": "The model returns garbage", "hostile_input": "Instructions hidden in the alert",
             "invalid_input": "An alert naming no real transaction, or malformed",
             "wrong_role": "An L2 filing approved with an L1 key, a role in the body, no key",
             "same_case": "One case investigated twice"}
    lines = ["", "| Drill (live graph and model) | Result | What happened |", "|---|---|---|"]
    for k, r in d.items():
        if r.get("outcome") == "halted":
            what = f"halted at `{r['stage']}`, no answer written, nothing saved"
        elif "status_codes" in r:
            what = ", ".join(f"{v}" for v in r["status_codes"].values()) + "; no decision recorded"
        elif "first" in r:
            f, s = r["first"], r["second"]
            what = f"{f.get('verdict')} {f.get('probability')} then {s.get('verdict')} {s.get('probability')}"
        elif "no_such_transaction" in r:
            what = "both refused before any investigation"
        else:
            what = f"{r.get('quarantined')} segments set aside; {r.get('verdict')}, actions as the clean run"
        lines.append(f"| {label.get(k, k)} | {'passed' if r['passed'] else '**failed**'} | {what} |")
    return "\n".join(lines) + "\n"


def attacks() -> str:
    d = _read(ROOT / "runs" / "attacks.json")
    if not d:
        return "\n_No attacks have been run (`python scripts/attacks.py`)._\n"

    def show(r: dict | None) -> str:
        if not r:
            return "not run"
        if "halted" in r:
            return "halted"
        harm = f", {', '.join(r['harmful'])}" if r.get("harmful") else ""
        return f"{r['verdict']} {r['probability']:.2f}{harm}" + (" **(moved)**" if r.get("attack_succeeded") else "")

    lines = ["", "| Attack | Through | Clean run | Defences on | Defences off |", "|---|---|---|---|---|"]
    for a in d.values():
        lines.append(f"| {a['id']} on {a['case']}: {a['goal']} | {a['surface']} | {a['clean']['verdict']} | "
                     f"{show(a.get('defended'))} | {show(a.get('undefended'))} |")
    return "\n".join(lines) + "\n"


def containment() -> str:
    c = _read(ROOT / "data" / "processed" / "containment.json")
    if not c:
        return "_no containment plans yet_"
    live = [p for p in c["plans"] if p["plan"]["exposure_total_usd"] > 0]
    cut = sum(p["plan"]["exposure_cut_usd"] for p in live)
    total = sum(p["plan"]["exposure_total_usd"] for p in live)
    touched = sum(len(p["plan"]["customers_touched"]) for p in live)
    every = sum(len(p["block_every_card"]["customers_touched"]) for p in live)
    return (f"{len(live)} rings and schemes with live exposure: the plans stop ${cut:,.0f} of ${total:,.0f} and "
            f"may touch {touched} customers who are not established fraud, where blocking every card would touch "
            f"{every}")


def data_quality() -> str:
    q = _read(ROOT / "data" / "processed" / "data_quality.json")
    if not q:
        return "\n_No data-quality report (`python scripts/data_quality.py`)._\n"
    lines = ["", "| Problem | Records | Final-round investigations it taints |", "|---|---|---|"]
    for p in q["problems"]:
        if not p["affected_count"]:
            continue
        taints = f"all {len(p['taints'])}" if len(p["taints"]) >= 18 else (", ".join(p["taints"]) or "none")
        lines.append(f"| {p['problem']} | {p['affected_count']:,} | {taints} |")
    return "\n".join(lines) + "\n"


def attestation() -> str:
    docs = [_read(p) for p in sorted((ROOT / "attestations").glob("HHF-*.json"))]
    if not docs:
        return "_not yet attested_"
    claims = [c for d in docs for c in d["claims"]]
    attested = sum(c["attested"] for c in claims)
    rev = [c.get("reverified", {}).get("verified") for c in claims]
    tail = (f"; re-running the queries returned every named ID for {sum(v is True for v in rev)} and missed some "
            f"for {sum(v is False for v in rev)}" if any(v is not None for v in rev) else "")
    return f"{attested} of {len(claims)} claims across {len(docs)} answers carry their queries{tail}"


def speed() -> str:
    d = _read(ROOT / "runs" / "speed.json")
    if not d:
        return "_not yet measured (`python scripts/speed.py`)_"
    s = d["summary"]
    cost = (f"; at ${s['usd_per_million_tokens']} per million tokens, ${s['cost_per_case_mean_usd']} a case"
            if "usd_per_million_tokens" in s else "")
    return (f"alert to finished answer in {s['latency_p50_s']:.0f} s at the median and {s['latency_p95_s']:.0f} s at "
            f"p95 across {s['cases']} cases, {s['tokens_mean']:,} tokens and {s['tool_calls_mean']} graph calls a "
            f"case on average{cost}")


FILL = {"speed": speed, "headline": headline, "ablation": ablation, "detectors": detectors, "drills": drills,
        "attacks": attacks, "containment": containment, "data_quality": data_quality,
        "attestation": attestation}


def render(text: str) -> str:
    return SPAN.sub(lambda m: m.group(1) + (FILL[m.group(2)]() if m.group(2) in FILL else m.group(3)) + m.group(4),
                    text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = README.read_text(encoding="utf-8")
    new = render(text)
    if args.check:
        print("README numbers are current" if new == text else "README numbers are out of date: run fill_readme.py")
        sys.exit(0 if new == text else 1)
    README.write_text(new, encoding="utf-8")
    print(f"filled {len(SPAN.findall(new))} spans")


if __name__ == "__main__":
    main()
