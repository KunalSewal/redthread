"""Measure the pattern classifier against every confirmed-fraud closed case.

    python scripts/eval_patterns.py

Rebuilds each closed case's episode from the transactions and compares
``redthread.patterns.classify`` with the pattern the bank's analysts recorded. Writes
data/processed/pattern_eval.json.
"""

import json
import logging

import pandas as pd

from redthread import paths
from redthread.patterns import classify

log = logging.getLogger("eval_patterns")
COLS = ["tx_id", "card_id", "ts", "amount", "channel", "region", "device_status"]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    txns = pd.concat(pd.read_csv(f, usecols=COLS, low_memory=False)
                     for f in sorted(paths.PROCESSED.glob("transactions_*.csv")))
    txns["region"] = txns["region"].map(lambda v: None if pd.isna(v) else str(int(float(v))))
    by_id = txns.set_index("tx_id")
    by_card = dict(tuple(txns.groupby("card_id")))

    cases = pd.read_csv(paths.CLOSED_CASES_CSV)
    cases = cases[cases["outcome"] == "confirmed_fraud"]
    rows = []
    for case in cases.itertuples():
        ids = [int(t) for t in str(case.txn_ids).split("|") if t]
        episode = by_id.reindex([i for i in ids if i in by_id.index]).dropna(subset=["ts"])
        if episode.empty:
            continue
        history = by_card[case.card_id]
        prior = history[history["ts"] < episode["ts"].min()]
        predicted = classify(episode.to_dict("records"), prior["region"].value_counts().to_dict())
        rows.append({"case_id": case.case_id, "truth": case.pattern, "predicted": predicted})

    frame = pd.DataFrame(rows)
    frame["correct"] = frame["truth"] == frame["predicted"]
    per_pattern = frame.groupby("truth")["correct"].agg(["mean", "size"]).round(3)
    report = {
        "n": len(frame),
        "accuracy": round(float(frame["correct"].mean()), 4),
        "per_pattern": {k: {"recall": v["mean"], "n": int(v["size"])} for k, v in per_pattern.iterrows()},
        "confusion": pd.crosstab(frame["truth"], frame["predicted"]).to_dict(),
    }
    (paths.PROCESSED / "pattern_eval.json").write_text(json.dumps(report, indent=2))
    log.info("pattern accuracy %.4f on %d confirmed-fraud closed cases", report["accuracy"], report["n"])
    log.info("%s", per_pattern)


if __name__ == "__main__":
    main()
