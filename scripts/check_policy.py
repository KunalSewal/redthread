"""Check every answer against the fraud policy, not just the schema.

    python scripts/check_policy.py            # cases/
    python scripts/check_policy.py cases_extra

`redthread.validate` proves an answer is well-formed and that its IDs exist. This proves it obeys the
policy it claims to follow: the rules in data/README.md ("Fraud Policy", sections 1-7) and the
answer-format notes. Each finding is an ERROR (the answer breaks a rule a grader can check
mechanically) or a WARN (defensible, but worth a human look).

It also checks the point-in-time rule: in the bank's 4,665 confirmed-fraud cases no transaction
happens after the case opened, so an affected transaction that postdates the alert means the
investigation used information it could not have had.
"""

import argparse
import json
import re
import sys

import pandas as pd

from redthread import paths

RULE = re.compile(r"\b(R\d{1,2}|section \d[ab]?|3[ab])\b", re.I)
BLOCKS = {"BLOCK_CARD", "BLOCK_ALL_CARDS"}


def sentences(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if len(s) > 3])


def check(answer: dict, alert: dict, trace: dict, tx: pd.DataFrame) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def err(msg: str) -> None:
        out.append(("ERROR", msg))

    def warn(msg: str) -> None:
        out.append(("WARN", msg))

    c, nba, sar = answer["case"], answer["next_best_actions"], answer["sar"]
    initial = [a["action"] for a in nba["initial"]]
    final = [a["action"] for a in nba["final"]]
    p, verdict, exposure = c["fraud_probability"], c["verdict"], c["exposure_usd"]
    requested = bool(answer["evidence_requests"])
    disputed = alert["trigger_type"] == "customer_report"
    signals = trace.get("assessment") or {}

    # Section 3a: when a case must be opened.
    reasons = [r for ok, r in ((p >= 0.30, f"probability {p:.2f} >= 0.30"), (requested, "evidence was requested"),
                               (disputed, "the customer disputed the charge")) if ok]
    if reasons and "CREATE_CASE" not in initial + final and verdict != "legitimate":
        err(f"3a: a case must be opened ({'; '.join(reasons)}) but CREATE_CASE is never recommended")
    if reasons and "CREATE_CASE" not in initial + final and verdict == "legitimate":
        warn(f"3a: {'; '.join(reasons)}, yet no CREATE_CASE (closed as legitimate)")

    # Section 3a: a report always has a case behind it, and only when the criteria hold.
    if "FILE_REPORT" in final and "CREATE_CASE" not in initial + final:
        err("3a: FILE_REPORT without CREATE_CASE - a report always has a case behind it")
    suspected = verdict == "fraud" or p >= 0.85
    connected = bool(c["connected_card_ids"] or c["connected_device_profiles"])
    criteria = [r for ok, r in ((exposure > 1000, f"exposure ${exposure:,.2f} > $1,000"),
                                (connected, "connects to other cards or a shared device"),
                                (c["pattern"] == "undocumented", "undocumented pattern (R9)")) if ok]
    if sar["file"] and not suspected:
        err(f"3a: a report is filed but fraud is neither confirmed nor strongly suspected (p={p:.2f}, {verdict})")
    if sar["file"] and not criteria:
        err("3a: a report is filed but none of its criteria hold (exposure, connection, R9)")
    if not sar["file"] and suspected and criteria:
        warn(f"3a: fraud suspected and {'; '.join(criteria)}, but no report is filed")

    # R1: never block on a single weak signal.
    if signals.get("single_signal") and signals.get("probability", p) < 0.70 and BLOCKS & set(initial):
        err("R1: blocks on a single signal below 0.70 without verifying first")
    # R8: uncertain and exposed, or conflicting evidence, goes to an analyst.
    if verdict == "uncertain" and exposure > 500 and "ESCALATE_TO_ANALYST" not in final:
        err(f"R8: uncertain with exposure ${exposure:,.2f} > $500 but not escalated")
    if signals.get("evidence_conflicts") and "ESCALATE_TO_ANALYST" not in final:
        err("R8: the evidence conflicts but the case is not escalated")
    # R10.
    if "BLOCK_ALL_CARDS" in final and signals.get("customer_cards_confirmed_fraud", 0) < 2 \
            and not signals.get("credentials_compromised"):
        err("R10: BLOCK_ALL_CARDS without two confirmed-fraud cards or compromised credentials")

    # Verdict and status must tell the same story.
    if verdict == "legitimate" and (BLOCKS | {"FILE_REPORT"}) & set(final):
        err(f"a legitimate verdict with punitive final actions: {sorted((BLOCKS | {'FILE_REPORT'}) & set(final))}")
    if verdict == "fraud" and "CLOSE_NO_FRAUD" in final:
        err("a fraud verdict closed as no fraud")
    if c["status"] == "escalated" and "ESCALATE_TO_ANALYST" not in final:
        err("status escalated, but ESCALATE_TO_ANALYST is not a final action")
    if c["status"] == "open" and not requested:
        warn("status open with no evidence request outstanding")
    if c["status"] == "open" and "CLOSE_NO_FRAUD" in final:
        err("status open, but the final plan closes the case as no fraud")

    # Section 7: every recommendation cites the rule it follows.
    for a in nba["initial"] + nba["final"]:
        if not RULE.search(a["reason"]):
            err(f"7: {a['action']} does not cite a policy rule: {a['reason'][:80]!r}")
    if requested and final != initial and nba["what_changed"].strip().lower() == "nothing":
        err("3b: the recommendation changed after evidence, but what_changed says nothing")
    for r in answer["evidence_requests"]:
        if not r["assumed_response"].strip():
            err(f"5: evidence request {r['type']} states no assumed response")

    # The answer-format notes.
    n = sentences(c["summary"])
    if not 2 <= n <= 6:
        warn(f"summary has {n} sentences; the format asks for two to six")
    if sar["file"]:
        n = sentences(sar["narrative"])
        if not 6 <= n <= 12:
            warn(f"SAR narrative has {n} sentences; the format asks for six to twelve")
        if not all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in sar["activity_dates"]) \
                or len(sar["activity_dates"]) != 2:
            err(f"SAR activity_dates must be two YYYY-MM-DD dates: {sar['activity_dates']}")
    if c["affected_txn_ids"] and c["first_suspicious_txn_id"]:
        ts = tx.reindex([int(t) for t in c["affected_txn_ids"]])["ts"].dropna()
        if len(ts) and str(ts.idxmin()) != c["first_suspicious_txn_id"]:
            err(f"first_suspicious_txn_id {c['first_suspicious_txn_id']} is not the earliest affected "
                f"transaction ({ts.idxmin()})")

    # Point in time: nothing after the alert.
    opened = pd.Timestamp(alert["opened_at"])
    late = [t for t in c["affected_txn_ids"] if int(t) in tx.index and tx.loc[int(t), "ts"] > opened]
    if late:
        err(f"point in time: {len(late)} affected transaction(s) postdate the alert: {late}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", nargs="?", default="cases")
    args = parser.parse_args()
    folder = paths.ROOT / args.folder

    alerts = {}
    pack = pd.read_csv(paths.CASE_PACK_CSV, dtype={"flagged_txn_id": str})
    alerts.update({r["case_id"]: r for r in pack.to_dict("records")})
    extra = folder / "alerts.json"
    if extra.exists():
        alerts.update({a["case_id"]: a for a in json.loads(extra.read_text(encoding="utf-8"))})
    tx = pd.read_parquet(paths.PROCESSED / "_all.parquet", columns=["tx_id", "ts"]).set_index("tx_id")
    tx["ts"] = pd.to_datetime(tx["ts"])

    errors = warnings = 0
    for path in sorted(folder.glob("*.json")):
        if path.name == "alerts.json":
            continue
        answer = json.loads(path.read_text(encoding="utf-8"))
        trace_path = paths.ROOT / "runs" / f"{answer['case_id']}.trace.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else {}
        findings = check(answer, alerts[answer["case_id"]], trace, tx)
        c = answer["case"]
        head = (f"{answer['case_id']:8} {c['verdict']:10} p={c['fraud_probability']:.2f} "
                f"{', '.join(a['action'] for a in answer['next_best_actions']['final'])}")
        print(("ok   " if not findings else "     ") + head)
        for level, msg in findings:
            print(f"       {level:5} {msg}")
            errors += level == "ERROR"
            warnings += level == "WARN"
    print(f"\n{errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
