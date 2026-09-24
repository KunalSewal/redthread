"""Historical fraud rate by score band, from out-of-fold Jul–Oct scores and closed-case labels.

Lets the agent read "model_score 0.62" as "about N% of past transactions scored like this were fraud"
instead of treating either score as a probability. Same table for the bank's risk_score.
"""

import json
import os
from functools import cache

import pandas as pd

from redthread import paths
from redthread.model.features import closed_case_labels

BANDS = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.85, 1.0001]
CACHE = paths.PROCESSED / "score_calibration.json"

# The last labelled month the table may learn from. The benchmark is Nov-Dec, so all of Jul-Oct is
# history and the default is 10. A backtest that replays October must not calibrate its prior on
# October's own outcomes, so it sets this to 9.
MAX_MONTH_ENV = "REDTHREAD_CALIBRATION_MAX_MONTH"


def _max_month() -> int:
    return int(os.environ.get(MAX_MONTH_ENV, "10"))


def _cache_path(max_month: int):
    return CACHE if max_month == 10 else paths.PROCESSED / f"score_calibration_to_m{max_month}.json"


def build(max_month: int = 10) -> dict:
    scores = pd.read_csv(paths.PROCESSED / "txn_scores.csv")
    tx = pd.read_csv(paths.TRANSACTIONS_CSV, usecols=["TransactionID", "risk_score", "ts"], engine="pyarrow")
    df = tx.merge(scores, left_on="TransactionID", right_on="tx_id")
    df = df[pd.to_datetime(df["ts"]).dt.month <= max_month]  # labelled months only
    df["fraud"] = closed_case_labels(df["TransactionID"])
    table = {}
    for col in ["model_score", "risk_score"]:
        bands = pd.cut(df[col], BANDS, right=False)
        grouped = df.groupby(bands, observed=True)["fraud"].agg(["mean", "size"])
        table[col] = [{"from": float(b.left), "to": min(float(b.right), 1.0), "fraud_rate": round(float(r["mean"]), 4),
                       "n": int(r["size"])} for b, r in grouped.iterrows()]
    _cache_path(max_month).write_text(json.dumps(table, indent=2))
    return table


@cache
def _table(max_month: int) -> dict:
    path = _cache_path(max_month)
    return json.loads(path.read_text()) if path.exists() else build(max_month)


def table() -> dict:
    return _table(_max_month())


@cache
def hot_share(score_min: float = 0.5) -> float:
    """Share of all transactions with model_score >= score_min: the baseline for 'unusually many'."""
    scores = pd.read_csv(paths.PROCESSED / "txn_scores.csv")["model_score"]
    return float((scores >= score_min).mean())


@cache
def _report_outcomes(max_month: int) -> tuple[int, int]:
    cases = pd.read_csv(paths.CLOSED_CASES_CSV, usecols=["opened_at", "outcome", "analyst_notes"])
    cases = cases[pd.to_datetime(cases["opened_at"]).dt.month <= max_month]
    reports = cases[cases["analyst_notes"].str.contains(r"cardholder \S+ reported", regex=True, na=False)]
    return int((reports["outcome"] == "confirmed_fraud").sum()), len(reports)


def customer_report_rate() -> tuple[float, int, int]:
    """How often a cardholder's report of activity they did not make turned out to be fraud.

    Read from the closed cases the same way the score table is: labelled months only. Add-one
    smoothing, so a history with no counter-example still leaves room for one.
    """
    fraud, n = _report_outcomes(_max_month())
    return (fraud + 1) / (n + 2), fraud, n


def fraud_rate(score: float, kind: str = "model_score") -> float | None:
    if score is None or score < 0:
        return None
    for band in table()[kind]:
        if band["from"] <= score < band["to"] or (score >= 1.0 and band["to"] >= 1.0):
            return band["fraud_rate"]
    return None
