"""Where the raw data lives, across both rounds, and the one definition of "labelled history".

Round 2 adds January 2017 as separate files in the same schema and replaces the closed-case
history with a superset (the Round 1 benchmark cases appended, with their real outcomes). Every
reader goes through this module, so nothing reads one round's files and silently misses the other.

Months are counted continuously (``month_index``): July 2016 is 7, October 10, January 2017 13.
"Labelled history" is index <= 10, as in Round 1. Counting calendar months instead would make
January (month 1) look like labelled history and train the model on it as "not fraud".
"""

import os
from pathlib import Path

import pandas as pd

from redthread import paths

LABELLED_MAX_MONTH = 10  # the closed cases label July-October 2016; later months are unlabelled
ROUND_ENV = "REDTHREAD_ROUND"  # "final" (default) or "r1", which case pack to answer

_TRANSACTIONS = (paths.DATA / "transactions.csv", paths.DATA_R2 / "transactions_2017q1.csv")
_IDENTITY = (paths.DATA / "identity.csv", paths.DATA_R2 / "identity_2017q1.csv")


def transaction_files() -> list[Path]:
    return [p for p in _TRANSACTIONS if p.exists()]


def identity_files() -> list[Path]:
    return [p for p in _IDENTITY if p.exists()]


def closed_cases_csv() -> Path:
    """The Round 2 history replaces Round 1's: it holds every Round 1 case plus the 20 HHG outcomes."""
    replacement = paths.DATA_R2 / "closed_cases_history.csv"
    return replacement if replacement.exists() else paths.DATA / "closed_cases_history.csv"


def answers_dir() -> Path:
    """Where this round's answer files live: cases/ for the final round (the submission), and
    cases_round1/ for Round 1's twenty, kept as they were submitted."""
    return paths.ROOT / ("cases_round1" if os.environ.get(ROUND_ENV, "final") == "r1" else "cases")


def case_pack_csv() -> Path:
    if os.environ.get(ROUND_ENV, "final") == "r1":
        return paths.DATA / "case_pack.csv"
    return paths.DATA_R2 / "cases" / "case_pack_final.csv"


def reviewed_alerts() -> pd.DataFrame:
    """Earlier benchmark reviews that are now closed cases, with the trigger that raised each one.

    The final round's history closes Round 1's HHG cases as ordinary CC records ("Case HHG-003 from
    the November-December review. ..."); Round 1's pack says what triggered each. Together they are
    the outcomes of alerts drawn the way this pack's alerts are drawn. Columns: review_id, trigger_type,
    opened_at, outcome.
    """
    cases = pd.read_csv(closed_cases_csv(), usecols=["opened_at", "outcome", "analyst_notes"])
    cases["review_id"] = cases["analyst_notes"].str.extract(r"^Case (HHG-\d+) from the ", expand=False)
    cases = cases.dropna(subset=["review_id"])
    pack = paths.DATA / "case_pack.csv"
    if cases.empty or not pack.exists():
        return pd.DataFrame(columns=["review_id", "trigger_type", "opened_at", "outcome"])
    triggers = pd.read_csv(pack, usecols=["case_id", "trigger_type"]).rename(columns={"case_id": "review_id"})
    return cases.merge(triggers, on="review_id")[["review_id", "trigger_type", "opened_at", "outcome"]]


def _concat(files: list[Path], **kwargs) -> pd.DataFrame:
    frames = [pd.read_csv(f, **kwargs) for f in files]
    return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)


def read_transactions(**kwargs) -> pd.DataFrame:
    """All transactions, Round 1 then January, with the same ``read_csv`` arguments for each file."""
    return _concat(transaction_files(), **kwargs)


def read_identity(**kwargs) -> pd.DataFrame:
    return _concat(identity_files(), **kwargs)


def processed_transactions(columns: list[str]) -> pd.DataFrame:
    """Prepared transactions of both rounds (data/processed/transactions_*.csv, from prepare_data),
    with tx_id as a string. These carry the derived card_id and holder_id. The old _all.parquet
    snapshot stops at December 2016 and must not be read: a January transaction is simply absent
    from it, so a check that looks one up passes without checking anything."""
    files = sorted(paths.PROCESSED.glob("transactions_*.csv"))
    if not files:
        raise FileNotFoundError("no data/processed/transactions_*.csv: run scripts/prepare_data.py")
    cols = list(dict.fromkeys(["tx_id", *columns]))
    return pd.concat([pd.read_csv(f, usecols=cols, dtype={"tx_id": str}, low_memory=False) for f in files],
                     ignore_index=True)


def month_index(ts: pd.Series) -> pd.Series:
    """Months since December 2015: July 2016 is 7, October 10, January 2017 13."""
    t = pd.to_datetime(ts)
    return (t.dt.year - 2016) * 12 + t.dt.month
