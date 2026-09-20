"""Analyst dashboard backend.

    uvicorn redthread.api.app:app --port 8000

Serves the case queue, full case records (answer + investigation trace), each case's evidence graph,
live investigations streamed as server-sent events, and the approval workflow for L1/L2 actions.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from redthread import paths
from redthread.agent.graph import investigate_alert
from redthread.agent.mcp_graph import McpGraph
from redthread.api.casegraph import case_graph
from redthread.policy import AUTO_ACTIONS, Action

log = logging.getLogger(__name__)
RUNS = paths.ROOT / "runs"
APPROVALS = RUNS / "approvals.json"
UI_DIST = paths.ROOT / "ui" / "dist"
ROUTE_RANK = {"auto": 0, "L1": 1, "L2": 2}

app = FastAPI(title="RedThread")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
_live: dict[str, asyncio.Queue] = {}


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _alerts() -> list[dict]:
    pack = pd.read_csv(paths.CASE_PACK_CSV, dtype={"flagged_txn_id": str})
    pack["risk_score"] = pack["risk_score"].astype(object).where(pack["risk_score"].notna(), None)
    return pack.sort_values("opened_at").to_dict("records")


def _approvals() -> dict:
    return _read(APPROVALS) or {}


@app.get("/api/cases")
def list_cases() -> list[dict]:
    out = []
    for alert in _alerts():
        answer = _read(paths.CASES_OUT / f"{alert['case_id']}.json")
        row = {k: alert[k] for k in ("case_id", "opened_at", "trigger_type", "trigger_text", "card_id",
                                     "customer_id", "flagged_txn_id", "risk_score")}
        if answer:
            c = answer["case"]
            pending = [a for a in answer["next_best_actions"]["final"] if a["route"] != "auto"]
            decided = _approvals().get(alert["case_id"], {})
            row |= {"status": c["status"], "verdict": c["verdict"], "fraud_probability": c["fraud_probability"],
                    "pattern": c["pattern"], "exposure_usd": c["exposure_usd"], "sar": answer["sar"]["file"],
                    "pending_approvals": sum(1 for a in pending if a["action"] not in decided)}
        else:
            row["status"] = "new"
        out.append(row)
    return out


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    alert = next((a for a in _alerts() if a["case_id"] == case_id), None)
    if not alert:
        raise HTTPException(404, "unknown case")
    answer = _read(paths.CASES_OUT / f"{case_id}.json")
    trace = _read(RUNS / f"{case_id}.trace.json") or {}
    final = answer["next_best_actions"]["final"] if answer else []
    decided = _approvals().get(case_id, {})
    actions = [{**a, "state": "executed (simulated)" if a["route"] == "auto" else decided.get(a["action"], {})
                .get("decision", "awaiting approval"), "approval": decided.get(a["action"])} for a in final]
    return {"alert": alert, "answer": answer, "events": trace.get("events", []), "evidence": trace.get("evidence", {}),
            "assessment": trace.get("llm_assessment"), "actions": actions,
            "graph": case_graph(trace, answer) if trace else {"nodes": [], "edges": []}}


class Approval(BaseModel):
    action: Action
    decision: str  # "approved" | "rejected"
    approver: str
    role: str  # "L1" | "L2"
    note: str = ""


@app.post("/api/cases/{case_id}/approvals")
def approve(case_id: str, body: Approval) -> dict:
    """Policy section 2: L1 and L2 actions wait for a human with at least that authority."""
    answer = _read(paths.CASES_OUT / f"{case_id}.json")
    if not answer:
        raise HTTPException(404, "case not investigated yet")
    item = next((a for a in answer["next_best_actions"]["final"] if a["action"] == body.action), None)
    if not item:
        raise HTTPException(400, f"{body.action} is not a recommended action for this case")
    if item["route"] == "auto" or body.action in AUTO_ACTIONS:
        raise HTTPException(400, "auto actions are executed by the agent and need no approval")
    if body.decision not in ("approved", "rejected") or body.role not in ("L1", "L2"):
        raise HTTPException(400, "decision must be approved|rejected and role L1|L2")
    if ROUTE_RANK[body.role] < ROUTE_RANK[item["route"]]:
        raise HTTPException(403, f"{body.action} requires {item['route']} approval; {body.role} is not sufficient")
    approvals = _approvals()
    approvals.setdefault(case_id, {})[body.action] = {
        "decision": body.decision, "approver": body.approver, "role": body.role, "note": body.note,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    RUNS.mkdir(exist_ok=True)
    APPROVALS.write_text(json.dumps(approvals, indent=2), encoding="utf-8")
    return approvals[case_id][body.action]


@app.post("/api/cases/{case_id}/investigate")
async def start_investigation(case_id: str) -> dict:
    alert = next((a for a in _alerts() if a["case_id"] == case_id), None)
    if not alert:
        raise HTTPException(404, "unknown case")
    if case_id in _live:
        raise HTTPException(409, "investigation already running")
    queue: asyncio.Queue = asyncio.Queue()
    _live[case_id] = queue
    asyncio.create_task(_run(alert, queue))
    return {"started": case_id}


async def _run(alert: dict, queue: asyncio.Queue) -> None:
    case_id = alert["case_id"]
    try:
        async with McpGraph() as graph:
            state = await investigate_alert(graph, alert, on_event=queue.put_nowait, as_of=alert["opened_at"])
        (paths.CASES_OUT / f"{case_id}.json").write_text(json.dumps(state["answer"], indent=2), encoding="utf-8")
        trace = {k: state.get(k) for k in ("alert", "events", "evidence", "llm_assessment", "assessment", "initial",
                                           "request", "reply", "final_assessment", "final", "report")}
        RUNS.mkdir(exist_ok=True)
        (RUNS / f"{case_id}.trace.json").write_text(json.dumps(trace, indent=1, default=str), encoding="utf-8")
        await queue.put({"kind": "done", "case_id": case_id})
    except Exception as exc:  # surface failures to the dashboard instead of hanging the stream
        log.exception("live investigation failed")
        await queue.put({"kind": "failed", "case_id": case_id, "detail": str(exc)[:500]})


@app.get("/api/cases/{case_id}/stream")
async def stream(case_id: str):
    queue = _live.get(case_id)
    if not queue:
        raise HTTPException(404, "no investigation running")

    async def events():
        try:
            while True:
                event = await queue.get()
                yield {"data": json.dumps(event)}
                if event["kind"] in ("done", "failed"):
                    break
        finally:
            _live.pop(case_id, None)

    return EventSourceResponse(events())


@app.get("/api/overview")
def overview() -> dict:
    cases = [c for c in list_cases() if c["status"] != "new"]
    metrics = _read(paths.PROCESSED / "model_metrics.json") or {}
    return {
        "cases": len(cases), "alerts": len(_alerts()),
        "by_verdict": pd.Series([c["verdict"] for c in cases]).value_counts().to_dict() if cases else {},
        "by_pattern": pd.Series([c["pattern"] for c in cases]).value_counts().to_dict() if cases else {},
        "exposure_usd": round(sum(c["exposure_usd"] for c in cases), 2),
        "sars": sum(1 for c in cases if c["sar"]),
        "pending_approvals": sum(c.get("pending_approvals", 0) for c in cases),
        "model": metrics.get("validation_train_jul_sep_test_oct"),
    }


if UI_DIST.exists():
    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
