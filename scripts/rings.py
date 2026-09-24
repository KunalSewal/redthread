"""Ring detection as of a cut-off, so no investigation sees a ring that only formed later.

    python scripts/rings.py                     # rings from the labelled history only (the default)
    python scripts/rings.py --cutoff 2016-10-01 # rings as of a date, e.g. before a backtest month

ring_wcc stores a ring_id on every card and device, so the rings in the graph reflect one cut-off at
a time. Every runner calls ensure() with the cut-off its alerts need:

- benchmark and monitoring runs use the start of the exam period, so no alert sees a ring
  built from activity after it - rings come from the labelled history (July-October) alone;
- a backtest uses the first day of the month it replays, so it never seeds a ring from the very
  confirmed-fraud outcomes it is scoring itself against, then restores the benchmark cut-off.

The cut-off last applied is recorded in data/processed/rings_state.json so a run that needs the same
one does not repeat the detection.
"""

import argparse
import json
import logging

import pandas as pd

from redthread import paths
from redthread.tg import GRAPH, connection

log = logging.getLogger("rings")
STATE = paths.PROCESSED / "rings_state.json"


def benchmark_cutoff() -> str:
    """The start of the exam period: rings come from the labelled history only.

    Not the earliest benchmark alert: monitoring sweeps the whole exam period from its first day, so
    a cut-off at the first benchmark alert (12 November) would let a monitoring alert on 6 November
    rely on rings built from the six days after it. The first day of the month the exam alerts begin
    in is before every benchmark and monitoring alert alike.
    """
    opened = pd.to_datetime(pd.read_csv(paths.CASE_PACK_CSV, usecols=["opened_at"])["opened_at"])
    return opened.min().replace(day=1, hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")


def current() -> str | None:
    return json.loads(STATE.read_text()).get("cutoff") if STATE.exists() else None


def detect(cutoff: str) -> dict:
    result = connection(GRAPH).runInstalledQuery("ring_wcc", {"cutoff": cutoff}, timeout=1_800_000)
    summary = {k: v for block in result for k, v in block.items()}
    STATE.write_text(json.dumps({"cutoff": cutoff, **summary}, indent=2), encoding="utf-8")
    log.info("rings as of %s: %s", cutoff, summary)
    return summary


def ensure(cutoff: str) -> None:
    """Make the rings in the graph reflect this cut-off, detecting them again only if needed."""
    if current() == cutoff:
        log.info("rings already as of %s", cutoff)
        return
    detect(cutoff)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser()
    parser.add_argument("--cutoff", help="YYYY-MM-DD[ HH:MM:SS]; default: the first benchmark alert")
    args = parser.parse_args()
    cutoff = args.cutoff or benchmark_cutoff()
    if len(cutoff) == 10:
        cutoff += " 00:00:00"
    detect(cutoff)


if __name__ == "__main__":
    main()
