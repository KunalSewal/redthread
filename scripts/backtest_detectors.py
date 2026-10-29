"""Backtest the new-typology detectors on the bank's closed cases (challenge 1).

    python scripts/backtest_detectors.py              # all 5,585 closed cases
    python scripts/backtest_detectors.py --limit 300  # a quick sample

Every closed case has a card and the moment it was opened, whatever its outcome. Each detector is
replayed on that card at that moment, through the same installed GSQL query the agent calls, with
``as_of`` set to the opening time so nothing later is visible:

- **new_kind_run**: the flagged kind of charge was under 5% of the card's prior 60 days, and the card
  made two or more of them in the last 30 (redthread.schemes.flagged_run).
- **slow_probes**: such a run made only of authorisations under $10, which R5's within-an-hour
  sequence would not catch.

A firing on a confirmed case is a catch; a firing on a cleared case is a legitimate customer the
detector would have acted against. The anchor is the case's last listed transaction for fraud; a
cleared case lists none, but its note gives the alerted amount ("model scored a $442.92
transaction"), so its anchor is the card's charge of that amount nearest before opening. Results go to
data/processed/detector_backtest.json with the query, its parameters and the time it ran.
"""

import argparse
import json
import logging
import re
import time
from datetime import datetime

import pandas as pd
from pyTigerGraph import TigerGraphConnection

from redthread import paths, schemes
from redthread.data import sources
from redthread.tg import GRAPH, connection

log = logging.getLogger("backtest_detectors")
OUT = paths.PROCESSED / "detector_backtest.json"
AMOUNT = re.compile(r"scored a \$([\d,]+\.\d\d) transaction")


def _row(a: dict) -> dict:
    return {"tx_id": a["tx_id"], "ts": a["ts"], "amount": a["amount"], "product": a["product_cd"],
            "channel": a["channel"], "device_status": a.get("device_status") or None,
            "proxy": a.get("proxy_type") or None}


def replay(conn: TigerGraphConnection, card: str, as_of: str, anchor: str) -> dict:
    res = conn.runInstalledQuery("new_kind_run", {"card": card, "as_of": as_of})
    rows = [_row({k.split(".", 1)[-1].lstrip("@"): v for k, v in x["attributes"].items()}) for x in res[1]["shifted"]]
    run = schemes.flagged_run(sorted(rows, key=lambda r: r["ts"]), anchor, res[0]["baseline_txns"])
    probes = bool(run) and all(abs(r["amount"]) < schemes.SMALL_AUTH_USD for r in run)
    return {"new_kind_run": bool(run), "slow_probes": probes and not schemes.fits_card_testing(run),
            "run": [r["tx_id"] for r in run]}


def _cleared_anchor(case, by_card: dict) -> str:
    match = AMOUNT.search(str(case.analyst_notes))
    card = by_card.get(case.card_id)
    if not match or card is None:
        return ""
    amount = float(match.group(1).replace(",", ""))
    hits = card[((card["amount"] - amount).abs() < 0.005) & (card["ts"] <= case.opened_at)]
    return hits.sort_values("ts")["tx_id"].iloc[-1] if len(hits) else ""


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("pyTigerGraph").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    cases = pd.read_csv(sources.closed_cases_csv())
    if args.limit:
        cases = cases.sample(args.limit, random_state=7)
    conn = connection(GRAPH)
    txns = sources.processed_transactions(["card_id", "ts", "amount"])
    by_card = dict(tuple(txns.groupby("card_id")))
    started, rows = datetime.now().isoformat(timespec="seconds"), []
    for n, c in enumerate(cases.itertuples(), 1):
        anchor = str(c.txn_ids).split("|")[-1] if isinstance(c.txn_ids, str) else _cleared_anchor(c, by_card)
        if not anchor:
            rows.append({"case_id": c.case_id, "card_id": c.card_id, "opened_at": c.opened_at,
                         "outcome": c.outcome, "pattern": c.pattern, "error": "alerted transaction not found"})
            continue
        try:
            hit = replay(conn, c.card_id, c.opened_at, anchor)
        except Exception as exc:  # recorded, never silently dropped
            hit = {"error": str(exc)[:200]}
        rows.append({"case_id": c.case_id, "card_id": c.card_id, "opened_at": c.opened_at, "outcome": c.outcome,
                     "pattern": c.pattern, **hit})
        if n % 250 == 0:
            log.info("%d/%d", n, len(cases))
    df = pd.DataFrame(rows)
    ok = df[df.get("error").isna()] if "error" in df else df
    summary = {}
    for det in ("new_kind_run", "slow_probes"):
        fired = ok[ok[det]]
        summary[det] = {
            "fired": int(len(fired)),
            "confirmed_fraud_caught": int((fired.outcome == "confirmed_fraud").sum()),
            "of_confirmed": int((ok.outcome == "confirmed_fraud").sum()),
            "cleared_customers_acted_against": int((fired.outcome == "cleared").sum()),
            "of_cleared": int((ok.outcome == "cleared").sum()),
            "caught_by_pattern": fired[fired.outcome == "confirmed_fraud"].pattern.value_counts().to_dict(),
            "cleared_case_ids": fired[fired.outcome == "cleared"].case_id.tolist()[:50],
        }
    out = {"ran_at": started, "finished_at": datetime.now().isoformat(timespec="seconds"),
           "data": [str(p.name) for p in sources.transaction_files()] + [sources.closed_cases_csv().name],
           "query": "new_kind_run(card, as_of=opened_at, run_days=30, baseline_days=60, max_share=0.05)",
           "cases": len(df), "errors": int(df.get("error", pd.Series(dtype=str)).notna().sum()),
           "summary": summary, "rows": rows}
    OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    log.info("%s", json.dumps(summary, indent=1)[:2000])
    log.info("wrote %s in %.0fs", OUT, time.time() - time.mktime(datetime.fromisoformat(started).timetuple()))


if __name__ == "__main__":
    main()
