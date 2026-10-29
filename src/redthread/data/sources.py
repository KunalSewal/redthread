"""Where the raw data lives, across both rounds, and the one definition of "labelled history".

Round 2 adds January 2017 as separate files in the same schema and replaces the closed-case
history with a superset (the Round 1 benchmark cases appended, with their real outcomes). Every
reader goes through this module, so nothing reads one round's files and silently misses the other.

Months are counted continuously (``month_index``): July 2016 is 7, October 10, January 2017 13.
"Labelled history" is index <= 10, as in Round 1. Counting calendar months instead would make
January (month 1) look like labelled history and train the model on it as "not fraud".
"""

import hashlib
import json
import os
from functools import cache
from pathlib import Path

import pandas as pd

from redthread import paths

LABELLED_MAX_MONTH = 10  # the closed cases label July-October 2016; later months are unlabelled
SOURCE_MAP = paths.ROOT / "config" / "source_map.json"  # the approved data layout (scripts/drift.py)
ROUND_ENV = "REDTHREAD_ROUND"  # "final" (default) or "r1", which case pack to answer

# Round 1's layout: what is read until a person approves another (scripts/drift.py).
_R1 = {"transactions": ["data/transactions.csv"], "identity": ["data/identity.csv"],
       "closed_cases": "data/closed_cases_history.csv", "case_pack": "data/case_pack.csv"}
_UNAPPROVED = (paths.DATA_R2 / "transactions_2017q1.csv", paths.DATA_R2 / "closed_cases_history.csv")


class DataLayoutError(RuntimeError):
    """The data on disk is not the layout a person approved. Never read around it."""


@cache
def _layout() -> dict:
    """The approved layout, its files checked against the fingerprints recorded at approval."""
    if not SOURCE_MAP.exists():
        if any(p.exists() for p in _UNAPPROVED):
            raise DataLayoutError("new data files are present but no layout has been approved: run "
                                  "scripts/drift.py detect, then scripts/drift.py approve with an L2 key")
        return _R1
    approved = json.loads(SOURCE_MAP.read_text(encoding="utf-8"))
    for rel, fp in approved["fingerprints"].items():
        f = paths.ROOT / rel
        if not f.exists():
            continue  # a missing file is reported by whoever needs it, as before
        with open(f, "rb") as fh:
            head = fh.read(65536)
        if f.stat().st_size != fp["bytes"] or hashlib.sha256(head).hexdigest() != fp["head_sha256"]:
            raise DataLayoutError(f"{rel} differs from the approved layout: run scripts/drift.py detect")
    return approved["map"]


def transaction_files() -> list[Path]:
    return [p for p in (paths.ROOT / f for f in _layout()["transactions"]) if p.exists()]


def identity_files() -> list[Path]:
    return [p for p in (paths.ROOT / f for f in _layout()["identity"]) if p.exists()]


def closed_cases_csv() -> Path:
    """The approved history. Round 2's replaces Round 1's: every Round 1 case plus the 20 HHG outcomes."""
    return paths.ROOT / _layout()["closed_cases"]


def answers_dir() -> Path:
    """Where this round's answer files live: cases/ for the final round (the submission), and
    cases_round1/ for Round 1's twenty, kept as they were submitted."""
    return paths.ROOT / ("cases_round1" if os.environ.get(ROUND_ENV, "final") == "r1" else "cases")


def case_pack_csv() -> Path:
    if os.environ.get(ROUND_ENV, "final") == "r1":
        return paths.DATA / "case_pack.csv"
    return paths.ROOT / _layout()["case_pack"]


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
