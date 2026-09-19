"""Filesystem locations used across the project."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
CASES_OUT = ROOT / "cases"
GSQL = ROOT / "gsql"

TRANSACTIONS_CSV = DATA / "transactions.csv"
IDENTITY_CSV = DATA / "identity.csv"
CLOSED_CASES_CSV = DATA / "closed_cases_history.csv"
CASE_PACK_CSV = DATA / "case_pack.csv"
