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
from redthread.belief import Judged, assess
from redthread.policy import AUTO_ACTIONS, Action, Assessment, recommend
from redthread.tg import GRAPH, connection

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


EXTRA = paths.ROOT / "cases_extra"


def _alerts() -> list[dict]:
    """The bank's 20 queued alerts plus the alerts the agent raised for itself.

    Both are investigated the same way; ``source`` is what separates "the queue gave us this" from
    "nobody asked us to look at this", which is the whole point of the monitoring deliverable.
    """
    pack = pd.read_csv(paths.CASE_PACK_CSV, dtype={"flagged_txn_id": str})
    pack["risk_score"] = pack["risk_score"].astype(object).where(pack["risk_score"].notna(), None)
    alerts = [r | {"source": "bank_queue"} for r in pack.to_dict("records")]
    for raised in _read(EXTRA / "alerts.json") or []:
        alerts.append(raised | {"source": raised.get("source", "agent_monitor")})
    return sorted(alerts, key=lambda a: str(a["opened_at"]))


def _answer_for(case_id: str) -> dict | None:
    """An answer file, wherever it lives: graded cases first, then self-raised ones."""
    return (_read(paths.CASES_OUT / f"{case_id}.json")
            or _read(EXTRA / f"{case_id}.json"))


def _approvals() -> dict:
    return _read(APPROVALS) or {}


@app.get("/api/cases")
def list_cases() -> list[dict]:
    out = []
    for alert in _alerts():
        answer = _answer_for(alert["case_id"])
        row = {k: alert.get(k) for k in ("case_id", "opened_at", "trigger_type", "trigger_text", "card_id",
                                         "customer_id", "flagged_txn_id", "risk_score", "source")}
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
    answer = _answer_for(case_id)
    trace = _read(RUNS / f"{case_id}.trace.json") or {}
    final = answer["next_best_actions"]["final"] if answer else []
    decided = _approvals().get(case_id, {})
    actions = [{**a, "state": "executed (simulated)" if a["route"] == "auto" else decided.get(a["action"], {})
                .get("decision", "awaiting approval"), "approval": decided.get(a["action"])} for a in final]
    return {
        "alert": alert, "answer": answer, "events": trace.get("events", []),
        "evidence": trace.get("evidence", {}), "assessment": trace.get("llm_assessment"),
        # The ledger, and belief before and after the customer replied: the case file shows how the
        # probability was computed, not just what it came to.
        "belief": trace.get("belief"), "signals": trace.get("assessment"),
        "final_signals": trace.get("final_assessment"), "request": trace.get("request"),
        "reply": trace.get("reply"), "report": trace.get("report"),
        "actions": actions,
        "graph": case_graph(trace, answer) if trace else {"nodes": [], "edges": [], "steps": 0}}


class Approval(BaseModel):
    action: Action
    decision: str  # "approved" | "rejected"
    approver: str
    role: str  # "L1" | "L2"
    note: str = ""


@app.post("/api/cases/{case_id}/approvals")
def approve(case_id: str, body: Approval) -> dict:
    """Policy section 2: L1 and L2 actions wait for a human with at least that authority."""
    answer = _answer_for(case_id)
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
    at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {"decision": body.decision, "approver": body.approver, "role": body.role, "note": body.note,
              "at": at}
    record["in_graph"] = _record_decision_in_graph(case_id, body, at, len(approvals.get(case_id, {})) + 1)
    approvals.setdefault(case_id, {})[body.action] = record
    RUNS.mkdir(exist_ok=True)
    APPROVALS.write_text(json.dumps(approvals, indent=2), encoding="utf-8")
    return record


def _record_decision_in_graph(case_id: str, body: "Approval", at: str, n: int) -> bool:
    """Write the decision onto the case in the graph, so it becomes memory later cases retrieve.

    The approval is recorded locally either way; if the workspace is suspended the graph simply is
    not updated, and the response says so rather than failing the approval.
    """
    cid = f"CASE-{case_id}"
    text = f"{body.role} {body.approver} {body.decision} {body.action}" + (f" ({body.note})" if body.note else "")
    try:
        conn = connection(GRAPH)
        conn.runInstalledQuery("record_analyst_decision", {"case_id": cid, "decision": text, "decided_at": at})
        conn.runInstalledQuery("add_case_event", {
            "case_id": cid, "event_id": f"{cid}-D{n:02d}", "step": 900 + n, "kind": "analyst_decision",
            "detail": text, "occurred_at": at})
        return True
    except Exception:
        log.exception("could not record the decision on %s in the graph", cid)
        return False


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
        # A self-raised alert's answer belongs with the others in cases_extra/; cases/ holds exactly the
        # twenty graded files.
        folder = paths.CASES_OUT if alert.get("source", "bank_queue") == "bank_queue" else EXTRA
        (folder / f"{case_id}.json").write_text(json.dumps(state["answer"], indent=2), encoding="utf-8")
        trace = {k: state.get(k) for k in ("alert", "events", "evidence", "llm_assessment", "belief", "assessment",
                                           "initial", "request", "reply", "final_assessment", "final", "report",
                                           "policy_evidence")}
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


@app.get("/api/monitoring")
def monitoring() -> dict:
    """What continuous monitoring adds over the bank's queue.

    These alerts were raised by the agent's own sweeps, not by the bank, so each one is a case the
    queue did not open. The flagged transaction's own risk score is shown to make the point: the
    bank's threshold would not have picked it up.
    """
    rows = []
    for alert in _alerts():
        if alert.get("source") == "bank_queue":
            continue
        answer = _answer_for(alert["case_id"])
        case = (answer or {}).get("case", {})
        rows.append({
            "case_id": alert["case_id"], "source": alert.get("source"),
            "opened_at": alert["opened_at"], "card_id": alert.get("card_id"),
            "flagged_txn_id": alert.get("flagged_txn_id"),
            "bank_risk_score": alert.get("risk_score"), "trigger_text": alert.get("trigger_text"),
            "verdict": case.get("verdict"), "pattern": case.get("pattern"),
            "exposure_usd": case.get("exposure_usd"), "sar": (answer or {}).get("sar", {}).get("file"),
        })
    confirmed = [r for r in rows if r["verdict"] == "fraud"]
    return {
        "alerts": rows,
        "raised": len(rows),
        "confirmed_fraud": len(confirmed),
        "exposure_usd": round(sum(r["exposure_usd"] or 0 for r in confirmed), 2),
        "by_source": pd.Series([r["source"] for r in rows]).value_counts().to_dict() if rows else {},
    }


@app.get("/api/rings")
def rings() -> dict:
    data = _read(paths.PROCESSED / "rings.json")
    if not data:
        raise HTTPException(503, "run scripts/export_ui_data.py to build the ring views")
    return data


@app.get("/api/rings/{ring_id}")
def ring(ring_id: int) -> dict:
    data = rings()
    found = next((r for r in data["rings"] if r["ring_id"] == ring_id), None)
    if not found:
        raise HTTPException(404, "unknown ring")
    return found


@app.get("/api/evaluation")
def evaluation() -> dict:
    """Everything measured about this agent, including where it fails."""
    # Newest measurement first. backtest_final.json is the one the README and blog quote.
    backtest = next((b for b in (_read(RUNS / name) for name in
                                 ("backtest_pit.json", "backtest_final.json", "backtest_after.json",
                                  "backtest_60.json",
                                  "backtest.json")) if b), None)
    return {
        "model": _read(paths.PROCESSED / "model_metrics.json"),
        "patterns": _read(paths.PROCESSED / "pattern_eval.json"),
        "calibration": _read(paths.PROCESSED / "score_calibration.json"),
        "community_lift": _read(paths.PROCESSED / "community_lift_lr.json"),
        "baselines": _read(paths.PROCESSED / "baselines.json"),
        "backtest": (backtest or {}).get("summary"),
        "backtest_cases": (backtest or {}).get("cases"),
    }


@app.get("/api/policy")
def policy() -> dict:
    """The retrievable policy and regulatory corpus, so a citation can be read in full."""
    path = paths.PROCESSED / "doc_chunks.csv"
    if not path.exists():
        raise HTTPException(503, "run scripts/build_knowledge.py to build the corpus")
    chunks = pd.read_csv(path)
    return {
        "chunks": chunks.to_dict("records"),
        "by_source": chunks["source"].value_counts().to_dict(),
    }


class Counterfactual(BaseModel):
    dropped: list[int] = []


@app.post("/api/cases/{case_id}/counterfactual")
def counterfactual(case_id: str, body: Counterfactual) -> dict:
    """What the agent would have concluded without some of its evidence.

    The arithmetic is deterministic, so this needs no model call: strike lines out of the ledger and
    reweigh. It runs through the same ``assess`` and the same policy engine the investigation used,
    rather than a second implementation, so the dashboard cannot drift from the agent. Striking a
    line out can promote the corroboration behind it, which is why the ledger is recomputed whole.
    """
    trace = _read(RUNS / f"{case_id}.trace.json") or {}
    belief = trace.get("belief")
    if not belief:
        raise HTTPException(404, "this case has no belief ledger")
    alert = trace.get("alert", {})
    flagged = trace.get("evidence", {}).get("alert_context", {}).get("flagged_txn", {})
    kept = [Judged(basis=i["basis"], direction=i["direction"], strength=i["strength"], claim=i["claim"],
                   entities=tuple(i.get("entities") or ()))
            for n, i in enumerate(belief["ledger"]) if n not in set(body.dropped)]
    new = assess(alert.get("trigger_type", "analyst_request"), flagged.get("model_score"), kept,
                 frozenset(belief.get("subject") or ()))

    # The recommendation is what an analyst acts on, so recompute that too: a probability that moves
    # without changing what the bank does is a curiosity, not a finding.
    actions: list[dict] = []
    signals = trace.get("assessment") or {}
    if signals:
        fields = {f for f in Assessment.__dataclass_fields__}
        kwargs = {k: v for k, v in signals.items() if k in fields}
        kwargs |= {"verdict": new.verdict, "probability": new.posterior,
                   "independent_evidence": new.independent_evidence}
        if isinstance(kwargs.get("connected_cards"), list):
            kwargs["connected_cards"] = tuple(kwargs["connected_cards"])
        try:
            actions = [{"action": str(r.action), "route": r.route, "reason": r.reason}
                       for r in recommend(Assessment(**kwargs))]
        except (TypeError, ValueError):
            log.exception("counterfactual policy recompute failed for %s", case_id)
    return {
        "posterior": new.posterior, "verdict": new.verdict, "prior": new.prior,
        "independent_evidence": new.independent_evidence, "explanation": new.explain(),
        "actions": actions,
        "ledger": [{"basis": i.basis, "counted": i.counted, "lr": round(i.lr_applied, 3),
                    "discounted": i.discounted, "claim": i.claim} for i in new.ledger],
    }


if UI_DIST.exists():
    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
