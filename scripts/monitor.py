"""Autonomous monitoring of the exam period (optional deliverable, README "Optional").

    python scripts/monitor.py --max-alerts 6

The agent raises its own alerts from the graph, beyond the 20-case pack:
  1. ring activity: transactions on ring devices where the device is new to the account;
  2. model misses: the second-generation model scores >= 0.9 while the legacy score stayed <= 0.3.
One alert per card (the earliest), cards already in the case pack skipped. Each alert is investigated by
the same agent and written to cases_extra/<alert_id>.json (IDs start with MON-).
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from redthread import paths
from redthread.agent.graph import investigate_alert
from redthread.agent.mcp_graph import McpGraph

sys.path.insert(0, str(Path(__file__).parent))
from run_cases import TRACES  # noqa: E402

log = logging.getLogger("monitor")
OUT = paths.ROOT / "cases_extra"
WINDOW = ("2016-11-01 00:00:00", "2016-12-31 23:59:59")


def _rows(result: list[dict]) -> list[dict]:
    return [{k.split(".", 1)[-1].lstrip("@"): v for k, v in h["attributes"].items()} for h in result[0]["hits"]]


async def raise_alerts(graph: McpGraph, max_alerts: int) -> list[dict]:
    pack_cards = set(pd.read_csv(paths.CASE_PACK_CSV)["card_id"])
    ring = _rows(await graph.query("monitor_ring_activity", {"from_ts": WINDOW[0], "to_ts": WINDOW[1]}))
    misses = _rows(await graph.query("monitor_model_misses", {"from_ts": WINDOW[0], "to_ts": WINDOW[1]}))
    candidates = []
    for source, rows, text in [
        ("ring_monitor", sorted(ring, key=lambda r: r["ts"]),
         "Monitoring: transaction {tx} (${amt:.2f}) on card {card} used a device from ring {ring}, new to this "
         "account. The bank's queue raised no alert (risk score {risk:.2f}). Investigate."),
        ("model_monitor", sorted(misses, key=lambda r: -r["model_score"]),
         "Monitoring: the second-generation model scored transaction {tx} (${amt:.2f}, card {card}) at {ms:.2f} "
         "while the legacy risk score was {risk:.2f}, so no alert was raised. Investigate."),
    ]:
        seen: set[str] = set()
        for r in rows:
            if r["card_id"] in pack_cards or r["card_id"] in seen:
                continue
            seen.add(r["card_id"])
            candidates.append({
                "source": source, "flagged_txn_id": r["tx_id"], "card_id": r["card_id"],
                "customer_id": r["card_id"].split("-")[0], "opened_at": r["ts"], "risk_score": r["risk_score"],
                "trigger_text": text.format(tx=r["tx_id"], amt=r["amount"], card=r["card_id"], ring=r.get("ring_id"),
                                            risk=r["risk_score"], ms=r["model_score"]),
            })
    # Alternate sources so a small budget covers both kinds of alert.
    by_source = [[c for c in candidates if c["source"] == s] for s in ("ring_monitor", "model_monitor")]
    picked = [c for pair in zip(*by_source, strict=False) for c in pair][:max_alerts]
    for i, c in enumerate(sorted(picked, key=lambda c: c["opened_at"]), 1):
        c["case_id"] = f"MON-{i:03d}"
        c["trigger_type"] = "risk_score"  # machine-raised alert; the text says which monitor raised it
    log.info("raised %d alerts from %d ring hits and %d model misses", len(picked), len(ring), len(misses))
    return sorted(picked, key=lambda c: c["opened_at"])


async def main(max_alerts: int) -> None:
    OUT.mkdir(exist_ok=True)
    TRACES.mkdir(exist_ok=True)
    async with McpGraph() as graph:
        alerts = await raise_alerts(graph, max_alerts)
        (OUT / "alerts.json").write_text(json.dumps(alerts, indent=2), encoding="utf-8")
        for alert in alerts:
            state = await investigate_alert(graph, alert, as_of=alert["opened_at"])
            (OUT / f"{alert['case_id']}.json").write_text(json.dumps(state["answer"], indent=2), encoding="utf-8")
            trace = {k: state.get(k) for k in ("alert", "events", "evidence", "llm_assessment", "final")}
            (TRACES / f"{alert['case_id']}.trace.json").write_text(json.dumps(trace, indent=1, default=str),
                                                                     encoding="utf-8")
            c = state["answer"]["case"]
            log.info("%s (%s): %s p=%.2f %s $%.2f", alert["case_id"], alert["source"], c["verdict"],
                     c["fraud_probability"], c["pattern"], c["exposure_usd"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "google_genai", "mcp", "sentence_transformers", "pyTigerGraph"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-alerts", type=int, default=6)
    asyncio.run(main(parser.parse_args().max_alerts))
