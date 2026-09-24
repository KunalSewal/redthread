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

from redthread import config, paths
from redthread.agent.graph import investigate_alert
from redthread.agent.mcp_graph import McpGraph

log = logging.getLogger("backtest")


def build_alerts(n: int, month: int, seed: int) -> list[dict]:
    """Rebuild the alert each closed case started from, balanced between fraud and cleared.

    The trigger type is assigned independently of the outcome. It used to be derived from it -- every
    confirmed case arrived as a customer report and every cleared one as a model alert -- which meant
    an agent could score full marks by reading the trigger and never investigating, and made the
    resulting accuracy meaningless. The benchmark case pack is deliberately balanced, so this is too:
    each alert is a coin flip, and the reported accuracy is broken down by trigger so that reading
    the trigger alone would be visible as a gap between the two strata.
    """
    cases = pd.read_csv(paths.CLOSED_CASES_CSV)
    cases = cases[pd.to_datetime(cases["opened_at"]).dt.month == month]
    fraud = cases[cases["outcome"] == "confirmed_fraud"]
    cleared = cases[cases["outcome"] == "cleared"]
    picked = pd.concat([fraud.sample(n // 2, random_state=seed), cleared.sample(n - n // 2, random_state=seed)])
    scores = (pd.read_parquet(paths.PROCESSED / "_all.parquet", columns=["tx_id", "risk_score"])
              .set_index("tx_id")["risk_score"])
    rng = random.Random(seed)
    alerts = []
    for c in picked.sort_values("opened_at").itertuples():
        txns = [t for t in str(c.txn_ids).split("|") if t]
        flagged = str(int(c.first_fraud_txn_id)) if not pd.isna(c.first_fraud_txn_id) else txns[0]
        reported = rng.random() < 0.5
        # The real legacy score on the flagged transaction, not a flattering constant.
        risk = scores.get(int(flagged))
        risk = round(float(risk), 4) if risk is not None and not pd.isna(risk) else 0.5
        alerts.append({
            "case_id": f"BT-{c.case_id}", "opened_at": c.opened_at, "card_id": c.card_id,
            "customer_id": c.customer_id, "flagged_txn_id": flagged,
            "trigger_type": "customer_report" if reported else "risk_score",
            "trigger_text": (f"Customer {c.customer_id} message: 'I never made this purchase. Please check my "
                             f"card.' Refers to {flagged}." if reported else
                             f"Real-time model scored transaction {flagged} at {risk:.2f}. Review and decide."),
            "risk_score": None if reported else risk,
            "truth": {"outcome": c.outcome, "pattern": c.pattern, "txn_ids": txns,
                      "exposure_usd": c.exposure_usd, "report_filed": c.report_filed},
        })
    return alerts


def score(alert: dict, answer: dict, belief: dict | None = None) -> dict:
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
        "trigger_type": alert["trigger_type"],
        # The ledger is kept so aggregation can be recalibrated offline, without paying for a rerun.
        "belief": belief,
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
        # If the agent were reading the trigger rather than investigating, these two would diverge.
        "accuracy_by_trigger": {t: round(g["verdict_correct"].mean(), 3)
                                for t, g in frame.groupby("trigger_type")},
        "n_by_trigger": {t: int(len(g)) for t, g in frame.groupby("trigger_type")},
    }


async def main(n: int, month: int, seed: int, out: str) -> None:
    # Nothing the replay scores itself against may shape the evidence. The fraud model's scores for
    # this month are already out-of-fold; the score calibration and the rings are made so here:
    # calibrate only on earlier months, and build rings only from what was known before the month.
    import os
    import sys

    sys.path.insert(0, str(paths.ROOT / "scripts"))
    import rings

    from redthread.belief import REPORT_PRIOR_ENV
    from redthread.model.calibration import MAX_MONTH_ENV

    os.environ[MAX_MONTH_ENV] = str(month - 1)
    # The replay decides the trigger by coin flip, independent of the outcome, so here a customer
    # report says nothing about fraud and the history's rate for real reports does not apply.
    os.environ[REPORT_PRIOR_ENV] = "0.5"
    rings.ensure(f"2016-{month:02d}-01 00:00:00")
    try:
        await _run(n, month, seed, out)
    finally:
        rings.ensure(rings.benchmark_cutoff())  # leave the graph as the benchmark expects it


CASE_TIMEOUT_S = 900  # a request cut off by a dropped connection can otherwise wait forever
ATTEMPTS = 3


async def _run(n: int, month: int, seed: int, out: str) -> None:
    from contextlib import AsyncExitStack

    alerts = build_alerts(n, month, seed)
    log.info("model=%s thinking=%s", config.REASONING_MODEL, config.THINKING_LEVEL or "default")
    # Each finished case is appended here, so an interrupted run resumes instead of starting over.
    partial = paths.ROOT / "runs" / f"{out.rsplit('.', 1)[0]}.partial.jsonl"
    done = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done[row["case_id"]] = row
        log.info("resuming: %d of %d cases already scored", len(done), len(alerts))
    rows = [done[a["case_id"]] for a in alerts if a["case_id"] in done]
    stack = AsyncExitStack()
    graph = await stack.enter_async_context(McpGraph())
    try:
        for alert in alerts:
            if alert["case_id"] in done:
                continue
            truth = alert.pop("truth")
            state = None
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    state = await asyncio.wait_for(investigate_alert(graph, dict(alert), as_of=alert["opened_at"]),
                                                   CASE_TIMEOUT_S)
                    break
                except Exception:
                    log.exception("%s failed (attempt %d of %d)", alert["case_id"], attempt, ATTEMPTS)
                    # A dropped connection can leave the MCP session unusable: start a fresh one.
                    await stack.aclose()
                    await asyncio.sleep(20)
                    stack = AsyncExitStack()
                    graph = await stack.enter_async_context(McpGraph())
            if state is None:
                log.error("%s failed", alert["case_id"])
                continue
            alert["truth"] = truth
            row = score(alert, state["answer"], state.get("belief"))
            rows.append(row)
            with partial.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            log.info("%s truth=%s/%s -> %s/%s p=%.2f %s", row["case_id"], row["truth_outcome"][:9],
                     row["truth_pattern"][:16], row["verdict"][:9], row["pattern"][:16], row["probability"],
                     "OK" if row["verdict_correct"] else "WRONG")
        # Backtest cases are scratch: remove them so they cannot pollute the memory real cases retrieve.
        for alert in alerts:
            await graph.query("delete_case", {"case_id": f"CASE-{alert['case_id']}"})
    finally:
        await stack.aclose()
    summary = report(rows) | {"model": config.REASONING_MODEL, "thinking": config.THINKING_LEVEL or "default"}
    (paths.ROOT / "runs" / out).write_text(json.dumps({"summary": summary, "cases": rows}, indent=2), encoding="utf-8")
    partial.unlink(missing_ok=True)
    log.info("summary: %s", json.dumps(summary))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "google_genai", "mcp", "sentence_transformers", "pyTigerGraph", "redthread.agent.graph"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--month", type=int, default=10)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--model", help="override the reasoning model for this run")
    parser.add_argument("--thinking", default=None, help="Gemini 3 thinking level: low | high (default: config)")
    parser.add_argument("--out", default="backtest.json", help="file under runs/")
    args = parser.parse_args()
    random.seed(args.seed)
    if args.model:
        config.REASONING_MODEL = args.model
    if args.thinking is not None:
        config.THINKING_LEVEL = args.thinking
    asyncio.run(main(args.n, args.month, args.seed, args.out))
