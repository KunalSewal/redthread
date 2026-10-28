"""Filesystem locations used across the project."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
CASES_OUT = ROOT / "cases"
GSQL = ROOT / "gsql"

DATA_R2 = DATA / "round2"  # final round: January 2017, the replacement closed cases, the HHF pack

# Raw inputs span both rounds: read them through redthread.data.sources, never by path here.
