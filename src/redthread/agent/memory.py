"""Case memory: write each investigation into the graph so later investigations can retrieve it."""

import logging
from datetime import datetime

from redthread.agent.mcp_graph import McpGraph
from redthread.rag.embed import embed_passages
from redthread.tg import connection

log = logging.getLogger(__name__)


async def write_case(graph: McpGraph, record: dict, events: list[dict]) -> None:
    """Replace any earlier version of the case, then write the case, its edges and its timeline.

    Goes through the installed write queries on the agent's MCP session (the only write path the agent
    has). The case embedding is loaded by the backend connection, since vector upserts are not exposed
    to the agent.
    """
    cid = record["case_id"]
    await graph.query("delete_case", {"case_id": cid})
    await graph.query("write_case", {
        "case_id": cid, "alert_id": record["alert_id"], "trigger_type": record["trigger_type"],
        "status": record["status"], "verdict": record["verdict"],
        "fraud_probability": record["fraud_probability"], "pattern": record["pattern"],
        "pattern_description": record["pattern_description"], "exposure_usd": record["exposure_usd"],
        "summary": record["summary"], "opened_at": record["opened_at"], "sar_filed": record["sar_filed"],
        "final_actions": "|".join(record["final_actions"]), "record_json": record["record_json"],
        "flagged": record["flagged_txn_id"], "affected": record["affected_txn_ids"], "card": record["card_id"],
        "connected": record["connected_card_ids"], "devices": record["device_ids"],
        "similar": record["similar_prior_cases"],
    })
    for ev in events:
        await graph.query("add_case_event", {
            "case_id": cid, "event_id": f"{cid}-E{ev['step']:02d}", "step": ev["step"], "kind": ev["kind"],
            "detail": ev["detail"][:2000], "occurred_at": ev["at"],
        })
    text = f"{record['verdict']}; pattern {record['pattern']}. {record['pattern_description']} {record['summary']}"
    vector = embed_passages([text])[0]
    line = f"{cid}|{','.join(f'{v:.6f}' for v in vector)}\n"
    connection().runLoadingJobWithData(line, "f", "load_fraud_case_emb", sep="|", eol="\n")
    log.info("case %s written to graph with %d events", cid, len(events))


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
