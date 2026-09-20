"""Run the agent on case-pack alerts and write answer files.

    python scripts/run_cases.py                   # all 20, in opened_at order (so case memory builds up)
    python scripts/run_cases.py HHG-014 HHG-001   # selected cases

Writes cases/<case_id>.json (the graded answer) and runs/<case_id>.trace.json (full investigation
trace: events, evidence digests, LLM assessment) for review and the dashboard.
"""

import argparse
import asyncio
import json
import logging
import sys
import time

import pandas as pd

from redthread import paths
from redthread.agent.graph import investigate_alert
from redthread.agent.mcp_graph import McpGraph

log = logging.getLogger("run_cases")
TRACES = paths.ROOT / "runs"


def load_alerts(ids: list[str]) -> list[dict]:
    pack = pd.read_csv(paths.CASE_PACK_CSV, dtype={"flagged_txn_id": str})
    pack["risk_score"] = pack["risk_score"].astype(object).where(pack["risk_score"].notna(), None)
    if ids:
        missing = set(ids) - set(pack["case_id"])
        if missing:
            sys.exit(f"unknown case ids: {sorted(missing)}")
        pack = pack[pack["case_id"].isin(ids)]
    return pack.sort_values("opened_at").to_dict("records")


async def main(ids: list[str]) -> int:
    paths.CASES_OUT.mkdir(exist_ok=True)
    TRACES.mkdir(exist_ok=True)
    failures = 0
    async with McpGraph() as graph:
        for alert in load_alerts(ids):
            start = time.time()
            try:
                # as_of: an alert may only draw on cases opened before it, so a rerun cannot feed a later
                # case's memory backwards into an earlier alert.
                state = await investigate_alert(graph, alert, as_of=alert["opened_at"])
            except Exception:
                log.exception("case %s failed", alert["case_id"])
                failures += 1
                continue
            answer = state["answer"]
            (paths.CASES_OUT / f"{alert['case_id']}.json").write_text(json.dumps(answer, indent=2), encoding="utf-8")
            trace = {k: state.get(k) for k in ("alert", "events", "evidence", "llm_assessment", "assessment",
                                               "initial", "request", "reply", "final_assessment", "final", "report")}
            (TRACES / f"{alert['case_id']}.trace.json").write_text(json.dumps(trace, indent=1, default=str),
                                                                     encoding="utf-8")
            c = answer["case"]
            log.info("%s done in %.0fs: %s p=%.2f %s exposure $%.2f | final: %s | sar=%s | calls=%d tokens=%d",
                     alert["case_id"], time.time() - start, c["verdict"], c["fraud_probability"], c["pattern"],
                     c["exposure_usd"], ", ".join(a["action"] for a in answer["next_best_actions"]["final"]),
                     answer["sar"]["file"], answer["tool_calls"], answer["tokens"])
    return 1 if failures else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "google_genai", "mcp", "sentence_transformers", "pyTigerGraph"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", nargs="*", help="case ids (default: all)")
    sys.exit(asyncio.run(main(parser.parse_args().cases)))
