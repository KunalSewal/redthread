"""Attestation for every claim in every answer, and a re-run that checks them.

    python scripts/attest.py            # write attestations/<case>.json for every answer in cases/
    python scripts/attest.py --verify   # also re-run each query and check its IDs come back

The brief: a claim nobody can check does not count. Each claim gets four parts:

- what: the claim in one sentence (the evidence line, or a case-level fact such as the exposure);
- evidence: the transaction, card and customer IDs behind it;
- how: the installed queries that produced it, with their exact parameters (from the trace's
  query_log, recorded as the investigation ran them);
- when: the time each query ran (UTC) and the data it ran against (files and the graph's counts).

Claims that rest on the alert itself (the customer's words) or on our own guard cite the case pack
row instead of a query. --verify re-runs every query through the same REST endpoint and checks that
each ID the claim names appears in what comes back; a mismatch is reported, never smoothed over.
"""

import argparse
import json
import re
from datetime import UTC, datetime

from redthread import paths
from redthread.data import sources
from redthread.tg import GRAPH, connection

OUT = paths.ROOT / "attestations"
ID = re.compile(r"^(\d{7}|C\d{5}-K\d|C\d{5}|CC-\d{4})$")


def _data_versions(conn) -> dict:
    files = {p.name: p.stat().st_size for p in [*sources.transaction_files(), sources.closed_cases_csv(),
                                                 sources.case_pack_csv()]}
    counts = {v: conn.getVertexCount(v) for v in ("Txn", "Card", "ClosedCase")}
    return {"files_bytes": files, "graph": GRAPH, "graph_vertex_counts": counts}


def _ids(ids: list[str]) -> dict:
    ids = [str(i) for i in ids if ID.match(str(i))]
    return {"transactions": [i for i in ids if i.isdigit()],
            "cards": [i for i in ids if "-K" in i],
            "customers": sorted({i.split("-")[0] for i in ids if i.startswith("C") and not i.startswith("CC-")}),
            "closed_cases": [i for i in ids if i.startswith("CC-")]}


def attest(answer: dict, trace: dict) -> list[dict]:
    log = trace.get("query_log") or {}
    alert, c = trace["alert"], answer["case"]
    claims = []
    # Every claim also rests on the alert's own context (the flagged transaction, its card and customer),
    # which the first query of every investigation returns.
    context = [q for r, qs in log.items() if r.startswith("query:alert_context(") for q in qs]
    for e in c["evidence"]:
        how = log.get(e["ref"])
        if how is None and e["ref"].startswith(("trigger:", "guard:")):
            how = [{"source": "case pack row", "case_id": alert["case_id"], "field": "trigger_text"}]
        elif how is not None and not e["ref"].startswith("query:alert_context("):
            how = [*how, *context]
        claims.append({"what": e["claim"], "evidence": _ids([*e["entity_ids"], alert["customer_id"]]),
                       "how": how or [], "ref": e["ref"],
                       "when": sorted({q["ran_at"] for q in how or [] if "ran_at" in q}),
                       "attested": bool(how)})
    # Case-level facts: where the episode, the exposure and the connected cards came from.
    episode_refs = [r for r in log if r.startswith(("query:new_kind_run(", "query:card_window("))]
    claims.append({"what": f"The fraud episode is {len(c['affected_txn_ids'])} transaction(s) totalling "
                           f"${c['exposure_usd']:,.2f}, starting at {c['first_suspicious_txn_id'] or '-'}.",
                   "evidence": _ids([*c["affected_txn_ids"], alert["card_id"], alert["customer_id"]]),
                   "how": [q for r in episode_refs for q in log[r]], "ref": "case.affected_txn_ids",
                   "when": sorted({q["ran_at"] for r in episode_refs for q in log[r]}),
                   "attested": not c["affected_txn_ids"] or bool(episode_refs)})
    if c["connected_card_ids"]:
        peer_refs = [r for r in log if r.startswith(("query:scheme_peers(", "query:recipient_cards(",
                                                     "query:device_neighbors(", "query:shared_origin("))]
        claims.append({"what": f"{len(c['connected_card_ids'])} other card(s) are connected to this case.",
                       "evidence": _ids(c["connected_card_ids"]), "how": [q for r in peer_refs for q in log[r]],
                       "ref": "case.connected_card_ids",
                       "when": sorted({q["ran_at"] for r in peer_refs for q in log[r]}),
                       "attested": bool(peer_refs)})
    return claims


SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
ID_IN_TEXT = re.compile(r"\b(\d{7}|C\d{5}-K\d|C\d{5}|CC-\d{4})\b")


def sar_sentences(answer: dict, claims: list[dict]) -> list[dict]:
    """Challenge 4: every sentence of a filed report linked to attested IDs. A sentence that names no
    ID is listed as unsupported rather than passed over."""
    narrative = answer["sar"]["narrative"] if answer["sar"]["file"] else ""
    attested = {i for c in claims if c["attested"] for kind in c["evidence"].values() for i in kind}
    out = []
    for sentence in (s for s in SENTENCE.split(narrative) if s.strip()):
        ids = sorted(set(ID_IN_TEXT.findall(sentence)))
        out.append({"sentence": sentence.strip(), "ids": ids,
                    "supported": bool(ids) and all(i in attested for i in ids),
                    "unattested_ids": [i for i in ids if i not in attested]})
    return out


def verify(conn, claim: dict) -> dict:
    """Re-run the claim's queries; every transaction and card it names must come back somewhere."""
    wanted = set(claim["evidence"]["transactions"]) | set(claim["evidence"]["cards"])
    if not wanted or not claim["how"] or "query" not in claim["how"][0]:
        return {"verified": None, "reason": "nothing to re-run"}
    seen = ""
    for q in claim["how"]:
        # The IDs a query was run on count too: new_kind_run on card C05061-K1 does not echo the card in
        # its output, yet it is exactly what attests a claim about that card.
        seen += json.dumps(q["params"])
        try:
            seen += json.dumps(conn.runInstalledQuery(q["query"], q["params"]))
        except Exception as exc:
            return {"verified": False, "reason": f"{q['query']} failed on re-run: {exc}"[:200]}
    # A whole-token match: holder IDs ("C06220-K1|126|201") and case summaries ("CC-2158|C10055-K1|...")
    # carry card IDs inside them.
    missing = sorted(i for i in wanted if not re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", seen))
    return {"verified": not missing, "missing": missing[:20]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    conn = connection(GRAPH)
    versions = _data_versions(conn)
    OUT.mkdir(exist_ok=True)
    totals = {"claims": 0, "attested": 0, "verified": 0, "mismatched": 0}
    for path in sorted(sources.answers_dir().glob("HHF-*.json")):
        answer = json.loads(path.read_text(encoding="utf-8"))
        trace = json.loads((paths.ROOT / "runs" / f"{path.stem}.trace.json").read_text(encoding="utf-8"))
        claims = attest(answer, trace)
        if args.verify:
            for cl in claims:
                cl["reverified"] = verify(conn, cl)
        sar = sar_sentences(answer, claims)
        doc = {"case_id": path.stem, "attested_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "data": versions, "claims": claims, "sar_sentences": sar}
        (OUT / f"{path.stem}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        n_ok = sum(c["attested"] for c in claims)
        ver = [c.get("reverified", {}).get("verified") for c in claims]
        totals["claims"] += len(claims)
        totals["attested"] += n_ok
        totals["verified"] += sum(v is True for v in ver)
        totals["mismatched"] += sum(v is False for v in ver)
        if sar:
            totals["sar_sentences"] = totals.get("sar_sentences", 0) + len(sar)
            totals["sar_supported"] = totals.get("sar_supported", 0) + sum(x["supported"] for x in sar)
        print(f"{path.stem}: {n_ok}/{len(claims)} attested"
              + (f", report {sum(x['supported'] for x in sar)}/{len(sar)} sentences supported" if sar else "")
              + (f", {sum(v is True for v in ver)} re-verified, {sum(v is False for v in ver)} mismatched"
                 if args.verify else ""))
    print(totals)


if __name__ == "__main__":
    main()
