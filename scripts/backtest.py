"""Measure investigation accuracy by replaying closed cases as if they were new alerts.

    python scripts/backtest.py --n 12 --month 10

The case pack's answer key is hidden, so accuracy is measured against the closed cases instead: take
October cases, rebuild the alert that started them, and investigate with point-in-time retrieval
(``as_of`` = the case's opened_at), so the agent cannot see that case or anything later. Then compare
its verdict, pattern and affected transactions with what the bank's analysts concluded.

Writes runs/backtest.json.
"""

import argparse
import asyncio
import json
import logging
import random

import pandas as pd

from redthread import paths
from redthread.agent.graph import investigate_alert
from redthread.agent.mcp_graph import McpGraph

log = logging.getLogger("backtest")
OUT = paths.ROOT / "runs" / "backtest.json"


def build_alerts(n: int, month: int, seed: int) -> list[dict]:
    """Rebuild the alert each closed case started from, balanced between fraud and cleared."""
    cases = pd.read_csv(paths.CLOSED_CASES_CSV)
    cases = cases[pd.to_datetime(cases["opened_at"]).dt.month == month]
    fraud = cases[cases["outcome"] == "confirmed_fraud"]
    cleared = cases[cases["outcome"] == "cleared"]
    picked = pd.concat([fraud.sample(n // 2, random_state=seed), cleared.sample(n - n // 2, random_state=seed)])
    alerts = []
    for c in picked.sort_values("opened_at").itertuples():
        txns = [t for t in str(c.txn_ids).split("|") if t]
        flagged = str(int(c.first_fraud_txn_id)) if not pd.isna(c.first_fraud_txn_id) else txns[0]
        confirmed = c.outcome == "confirmed_fraud"
        alerts.append({
            "case_id": f"BT-{c.case_id}", "opened_at": c.opened_at, "card_id": c.card_id,
            "customer_id": c.customer_id, "flagged_txn_id": flagged,
            "trigger_type": "customer_report" if confirmed else "risk_score",
            "trigger_text": (f"Customer {c.customer_id} message: 'I never made this purchase. Please check my "
                             f"card.' Refers to {flagged}." if confirmed else
                             f"Real-time model scored transaction {flagged} at 0.90. Review and decide."),
            "risk_score": None if confirmed else 0.9,
            "truth": {"outcome": c.outcome, "pattern": c.pattern, "txn_ids": txns,
                      "exposure_usd": c.exposure_usd, "report_filed": c.report_filed},
        })
    return alerts


def score(alert: dict, answer: dict) -> dict:
    truth, case = alert["truth"], answer["case"]
    fraud = truth["outcome"] == "confirmed_fraud"
    predicted, found = set(case["affected_txn_ids"]), set(truth["txn_ids"])
    overlap = len(predicted & found)
    return {
        "case_id": alert["case_id"], "truth_outcome": truth["outcome"], "truth_pattern": truth["pattern"],
        "verdict": case["verdict"], "pattern": case["pattern"], "probability": case["fraud_probability"],
        "verdict_correct": (case["verdict"] == "fraud") == fraud,
        "pattern_correct": case["pattern"] == truth["pattern"],
        "txn_recall": round(overlap / len(found), 3) if found else None,
        "txn_precision": round(overlap / len(predicted), 3) if predicted else None,
        "sar": answer["sar"]["file"], "truth_report_filed": truth["report_filed"] == "Yes",
        "actions": [a["action"] for a in answer["next_best_actions"]["final"]],
    }


def report(rows: list[dict]) -> dict:
    frame = pd.DataFrame(rows)
    fraud = frame[frame["truth_outcome"] == "confirmed_fraud"]
    cleared = frame[frame["truth_outcome"] == "cleared"]
    brier = ((frame["probability"] - (frame["truth_outcome"] == "confirmed_fraud").astype(float)) ** 2).mean()
    return {
        "n": len(frame),
        "verdict_accuracy": round(frame["verdict_correct"].mean(), 3),
        "fraud_recall": round(fraud["verdict_correct"].mean(), 3) if len(fraud) else None,
        "cleared_accuracy": round(cleared["verdict_correct"].mean(), 3) if len(cleared) else None,
        "pattern_accuracy_on_fraud": round(fraud["pattern_correct"].mean(), 3) if len(fraud) else None,
        "txn_recall_mean": round(fraud["txn_recall"].dropna().mean(), 3) if len(fraud) else None,
        "txn_precision_mean": round(fraud["txn_precision"].dropna().mean(), 3) if len(fraud) else None,
        "brier": round(float(brier), 4),
        "sar_agreement": round((frame["sar"] == frame["truth_report_filed"]).mean(), 3),
    }


async def main(n: int, month: int, seed: int) -> None:
    alerts = build_alerts(n, month, seed)
    rows = []
    async with McpGraph() as graph:
        for alert in alerts:
            truth = alert.pop("truth")
            try:
                state = await investigate_alert(graph, alert, as_of=alert["opened_at"])
            except Exception:
                log.exception("%s failed", alert["case_id"])
                continue
            alert["truth"] = truth
            row = score(alert, state["answer"])
            rows.append(row)
            log.info("%s truth=%s/%s -> %s/%s p=%.2f %s", row["case_id"], row["truth_outcome"][:9],
                     row["truth_pattern"][:16], row["verdict"][:9], row["pattern"][:16], row["probability"],
                     "OK" if row["verdict_correct"] else "WRONG")
        # Backtest cases are scratch: remove them so they cannot pollute the memory real cases retrieve.
        for alert in alerts:
            await graph.query("delete_case", {"case_id": f"CASE-{alert['case_id']}"})
    summary = report(rows)
    OUT.write_text(json.dumps({"summary": summary, "cases": rows}, indent=2), encoding="utf-8")
    log.info("summary: %s", json.dumps(summary))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "google_genai", "mcp", "sentence_transformers", "pyTigerGraph", "redthread.agent.graph"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--month", type=int, default=10)
    parser.add_argument("--seed", type=int, default=7)
    random.seed(parser.parse_args().seed)
    args = parser.parse_args()
    asyncio.run(main(args.n, args.month, args.seed))
