"""Historical fraud rate by score band, from out-of-fold Jul–Oct scores and closed-case labels.

Lets the agent read "model_score 0.62" as "about N% of past transactions scored like this were fraud"
instead of treating either score as a probability. Same table for the bank's risk_score.
"""

import json
from functools import cache

import pandas as pd

from redthread import paths
from redthread.model.features import closed_case_labels

BANDS = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.85, 1.0001]
CACHE = paths.PROCESSED / "score_calibration.json"


def build() -> dict:
    scores = pd.read_csv(paths.PROCESSED / "txn_scores.csv")
    tx = pd.read_csv(paths.TRANSACTIONS_CSV, usecols=["TransactionID", "risk_score", "ts"], engine="pyarrow")
    df = tx.merge(scores, left_on="TransactionID", right_on="tx_id")
    df = df[pd.to_datetime(df["ts"]).dt.month <= 10]  # labelled months only
    df["fraud"] = closed_case_labels(df["TransactionID"])
    table = {}
    for col in ["model_score", "risk_score"]:
        bands = pd.cut(df[col], BANDS, right=False)
        grouped = df.groupby(bands, observed=True)["fraud"].agg(["mean", "size"])
        table[col] = [{"from": float(b.left), "to": min(float(b.right), 1.0), "fraud_rate": round(float(r["mean"]), 4),
                       "n": int(r["size"])} for b, r in grouped.iterrows()]
    CACHE.write_text(json.dumps(table, indent=2))
    return table


@cache
def table() -> dict:
    return json.loads(CACHE.read_text()) if CACHE.exists() else build()


@cache
def hot_share(score_min: float = 0.5) -> float:
    """Share of all transactions with model_score >= score_min: the baseline for 'unusually many'."""
    scores = pd.read_csv(paths.PROCESSED / "txn_scores.csv")["model_score"]
    return float((scores >= score_min).mean())


def fraud_rate(score: float, kind: str = "model_score") -> float | None:
    if score is None or score < 0:
        return None
    for band in table()[kind]:
        if band["from"] <= score < band["to"] or (score >= 1.0 and band["to"] >= 1.0):
            return band["fraud_rate"]
    return None
