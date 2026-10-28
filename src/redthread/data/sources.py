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


def case_pack_csv() -> Path:
    if os.environ.get(ROUND_ENV, "final") == "r1":
        return paths.DATA / "case_pack.csv"
    return paths.DATA_R2 / "cases" / "case_pack_final.csv"


def _concat(files: list[Path], **kwargs) -> pd.DataFrame:
    frames = [pd.read_csv(f, **kwargs) for f in files]
    return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)


def read_transactions(**kwargs) -> pd.DataFrame:
    """All transactions, Round 1 then January, with the same ``read_csv`` arguments for each file."""
    return _concat(transaction_files(), **kwargs)


def read_identity(**kwargs) -> pd.DataFrame:
    return _concat(identity_files(), **kwargs)


def month_index(ts: pd.Series) -> pd.Series:
    """Months since December 2015: July 2016 is 7, October 10, January 2017 13."""
    t = pd.to_datetime(ts)
    return (t.dt.year - 2016) * 12 + t.dt.month
