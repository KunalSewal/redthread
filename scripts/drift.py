"""Schema drift (challenge 12): detect what changed in the data, explain what it breaks, and only
use the new layout once a person has approved it.

    python scripts/drift.py detect                    # compare, explain, write a proposal
    python scripts/drift.py approve --key <L2 key>    # a named L2 approver accepts the proposal
    python scripts/drift.py status                    # what is approved, and does the data still match

``detect`` compares every data file with the layout already approved (or, the first time, with Round
1's): columns and their order, row counts, the closed-case history (superset? any old row changed?),
ID and time ranges, and two meaning-level checks that a column comparison misses: month numbering
(January is month 1, which a "months 7-10 are history" rule would read as labelled history) and
holder linkage through D1. It writes data/processed/drift_proposal.json: the changes, what each one
breaks, and the re-mapping that fixes it.

``approve`` takes an approver key (scripts/approvers.py), refuses anything but L2, records the
decision in the hash-chained ledger runs/drift_approvals.log.jsonl, and writes config/source_map.json:
the approved files with a fingerprint of each (size and a hash of its first 64 KB). redthread.data.sources
reads only that map, and refuses to run when a file on disk no longer matches its fingerprint.
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime

import pandas as pd

from redthread import paths
from redthread.api import auth
from redthread.api.ledger import Ledger
from redthread.data import sources

PROPOSAL = paths.PROCESSED / "drift_proposal.json"
LEDGER = Ledger(paths.ROOT / "runs" / "drift_approvals.log.jsonl")

R1 = {"transactions": [paths.DATA / "transactions.csv"], "identity": [paths.DATA / "identity.csv"],
      "closed_cases": paths.DATA / "closed_cases_history.csv", "case_pack": paths.DATA / "case_pack.csv"}
R2 = {"transactions": [paths.DATA / "transactions.csv", paths.DATA_R2 / "transactions_2017q1.csv"],
      "identity": [paths.DATA / "identity.csv", paths.DATA_R2 / "identity_2017q1.csv"],
      "closed_cases": paths.DATA_R2 / "closed_cases_history.csv",
      "case_pack": paths.DATA_R2 / "cases" / "case_pack_final.csv"}


def _rel(p) -> str:
    return p.relative_to(paths.ROOT).as_posix()


def detect() -> dict:
    changes, breaks = [], []
    old_t, new_t = R1["transactions"][0], R2["transactions"][1]
    if not new_t.exists():
        print("no new transaction file found; nothing to propose")
        sys.exit(0)
    for kind, (a, b) in {"transactions": (old_t, new_t), "identity": (R1["identity"][0], R2["identity"][1])}.items():
        ca, cb = list(pd.read_csv(a, nrows=0).columns), list(pd.read_csv(b, nrows=0).columns)
        changes.append({"what": f"new {kind} file {_rel(b)}",
                        "columns": "identical, same order" if ca == cb else
                        {"added": sorted(set(cb) - set(ca)), "removed": sorted(set(ca) - set(cb)),
                         "reordered": set(ca) == set(cb)}})
        if ca != cb:
            breaks.append(f"{kind}: column layout differs; every reader by position must be re-mapped")
    t1 = pd.read_csv(old_t, usecols=["TransactionID", "ts"])
    t2 = pd.read_csv(new_t, usecols=["TransactionID", "ts"])
    overlap = int(t1["TransactionID"].isin(t2["TransactionID"]).sum())
    changes.append({"what": "transaction ID and time ranges",
                    "old": [int(t1.TransactionID.min()), int(t1.TransactionID.max()), t1.ts.min(), t1.ts.max()],
                    "new": [int(t2.TransactionID.min()), int(t2.TransactionID.max()), t2.ts.min(), t2.ts.max()],
                    "overlapping_ids": overlap})
    if overlap:
        breaks.append(f"{overlap} transaction IDs appear in both files: loading both would merge different rows")
    months = sorted(set(pd.to_datetime(t2.ts).dt.month))
    breaks.append(f"the new file's calendar months are {months}: any rule of the form 'month <= 10 is labelled "
                  "history' would treat January as labelled (and every January transaction as not fraud). "
                  "Months must be counted continuously (redthread.data.sources.month_index: Jan 2017 = 13)")
    old_c, new_c = pd.read_csv(R1["closed_cases"]), pd.read_csv(R2["closed_cases"])
    kept = bool(old_c.case_id.isin(new_c.case_id).all())
    merged = old_c.merge(new_c, on="case_id", suffixes=("_o", "_n"))
    altered = [c for c in old_c.columns if c != "case_id"
               and not (merged[c + "_o"].fillna("").astype(str) == merged[c + "_n"].fillna("").astype(str)).all()]
    added = sorted(set(new_c.case_id) - set(old_c.case_id))
    changes.append({"what": f"closed-case history replaced by {_rel(R2['closed_cases'])}",
                    "rows": [len(old_c), len(new_c)], "old_rows_all_kept": kept, "old_rows_changed_in": altered,
                    "added": [added[0], added[-1]] if added else []})
    breaks.append(f"the closed-case history is replaced, not appended: {len(added)} new cases "
                  f"({added[0]}..{added[-1]}) are earlier benchmark reviews with known outcomes; calibration, priors "
                  "and similar-case "
                  "retrieval must read the new file, and the graph's ClosedCase vertices must be reloaded")
    if not kept or altered:
        breaks.append("old closed cases were removed or edited: earlier answers citing them must be re-checked")
    tx = sources.processed_transactions(["holder_id", "ts"]) if list(paths.PROCESSED.glob("transactions_*.csv")) \
        else None
    if tx is not None:
        tx["m"] = sources.month_index(tx["ts"])
        jan, dec = tx[tx.m == 13], tx[tx.m == 12]
        jl = jan.holder_id.isin(set(tx[tx.m <= 12].holder_id)).mean()
        dl = dec.holder_id.isin(set(tx[tx.m <= 11].holder_id)).mean()
        changes.append({"what": "holder linkage through D1", "december_linked": round(float(dl), 3),
                        "january_linked": round(float(jl), 3)})
        if jl < dl / 2:
            breaks.append(f"D1 no longer continues across the file boundary: {jl:.0%} of January transactions resolve "
                          f"to an earlier holder against {dl:.0%} for December. Holder baselines for January alerts "
                          "are thin; judge 'new for this card' at card level (redthread.schemes)")
    remap = {k: [_rel(p) for p in v] if isinstance(v, list) else _rel(v) for k, v in R2.items()}
    proposal = {"detected_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "changes": changes,
                "breaks": breaks, "remap": remap,
                "fingerprints": {f: _fingerprint(paths.ROOT / f) for f in _files(remap)}}
    proposal["proposal_sha256"] = hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()
    PROPOSAL.write_text(json.dumps(proposal, indent=1), encoding="utf-8")
    for b in breaks:
        print("BREAKS:", b)
    print(f"\nproposal {proposal['proposal_sha256'][:12]} written to {PROPOSAL}; approve it with an L2 key")
    return proposal


def _files(remap: dict) -> list[str]:
    return [f for v in remap.values() for f in (v if isinstance(v, list) else [v])]


def _fingerprint(path) -> dict:
    with open(path, "rb") as f:
        head = f.read(65536)
    return {"bytes": path.stat().st_size, "head_sha256": hashlib.sha256(head).hexdigest()}


def approve(key: str, note: str) -> None:
    approver = auth.resolve(key)
    if approver is None:
        sys.exit("refused: unknown approver key")
    if approver.role != "L2":
        sys.exit(f"refused: {approver.name} is {approver.role}; re-mapping the data needs L2")
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    for f, fp in proposal["fingerprints"].items():
        if _fingerprint(paths.ROOT / f) != fp:
            sys.exit(f"refused: {f} changed since the proposal was made; run detect again")
    record = LEDGER.append({"case_id": "DATA-REMAP", "action": proposal["proposal_sha256"], "decision": "approved",
                            "approver": approver.name, "role": approver.role, "approver_id": approver.id,
                            "note": note, "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")})
    sources.SOURCE_MAP.parent.mkdir(exist_ok=True)
    sources.SOURCE_MAP.write_text(json.dumps({
        "approved": {k: record[k] for k in ("approver", "role", "at", "note", "hash")},
        "proposal_sha256": proposal["proposal_sha256"], "breaks_acknowledged": proposal["breaks"],
        "map": proposal["remap"], "fingerprints": proposal["fingerprints"]}, indent=1), encoding="utf-8")
    print(f"approved by {approver.name} ({approver.role}); {sources.SOURCE_MAP} now defines the data layout")


def status() -> None:
    if not sources.SOURCE_MAP.exists():
        print("no approved layout: only Round 1's files are read")
        return
    m = json.loads(sources.SOURCE_MAP.read_text(encoding="utf-8"))
    print(f"approved by {m['approved']['approver']} ({m['approved']['role']}) at {m['approved']['at']}")
    for f, fp in m["fingerprints"].items():
        ok = (paths.ROOT / f).exists() and _fingerprint(paths.ROOT / f) == fp
        print(f"  {'ok  ' if ok else 'DIFF'} {f}")
    print("ledger intact" if LEDGER.verify()[0] else f"ledger BROKEN at line {LEDGER.verify()[1]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["detect", "approve", "status"])
    parser.add_argument("--key", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    {"detect": detect, "status": status}.get(args.step, lambda: approve(args.key, args.note))()


if __name__ == "__main__":
    main()
