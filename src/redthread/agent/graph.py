"""The investigation workflow as a LangGraph state machine.

    intake -> gather -> investigate -> assess -> decide_initial -> [request_evidence] -> decide_final
           -> report -> write_back -> answer

Graph evidence comes only from MCP tools; the LLM investigates, assesses and writes; the policy
engine decides actions and routes; the simulator supplies the assumed reply to evidence requests.
"""

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypedDict

from google.genai import types
from langgraph.graph import END, StateGraph

from redthread.agent import memory, prompts
from redthread.agent.llm import Llm
from redthread.agent.mcp_graph import GraphToolError, McpGraph
from redthread.agent.schemas import LlmAssessment, LlmReport, json_schema
from redthread.agent.simulator import simulate
from redthread.agent.tools import Tools
from redthread.answer import Answer
from redthread.policy import Action, Assessment, evidence_request, recommend, sar_required

log = logging.getLogger(__name__)
FOLLOW_UP_BUDGET = 5
STOP_HIGH, STOP_LOW = 0.85, 0.15
P_FLOOR = 0.03  # calibration is scored: never claim certainty the evidence cannot support


class CaseState(TypedDict, total=False):
    alert: dict
    case_id: str
    started: float
    events: list[dict]
    evidence: dict[str, dict]
    llm_assessment: dict
    assessment: dict
    initial: list[dict]
    request: str | None
    reply: dict | None
    final_assessment: dict
    final: list[dict]
    report: dict
    written: bool
    investigation_calls: int
    answer: dict


class Investigation:
    """One alert's investigation. Holds the tools and LLM the graph nodes share."""

    def __init__(self, graph: McpGraph, llm: Llm, on_event: Callable[[dict], None] | None = None,
                 as_of: str | None = None):
        self.graph, self.llm = graph, llm
        self.tools = Tools(graph, as_of)
        self.on_event = on_event  # e.g. the dashboard's live stream

    # ------------------------------------------------------------------ helpers
    def _event(self, state: CaseState, kind: str, detail: str) -> None:
        events = state.setdefault("events", [])
        event = {"step": len(events) + 1, "kind": kind, "detail": detail, "at": memory.now()}
        events.append(event)
        log.info("[%s] %s: %s", state.get("case_id"), kind, detail[:160])
        if self.on_event:
            self.on_event({"case_id": state.get("case_id"), **event})

    async def _collect(self, state: CaseState, key: str, coro) -> dict | None:
        try:
            result = await coro
        except GraphToolError as exc:
            self._event(state, "tool_error", f"{key}: {str(exc)[:300]}")
            return None
        state.setdefault("evidence", {})[key] = result
        self._event(state, "evidence", f"{result['ref']}")
        return result

    # ------------------------------------------------------------------ nodes
    async def intake(self, state: CaseState) -> CaseState:
        alert = state["alert"]
        state["case_id"] = f"CASE-{alert['case_id']}"
        state["started"] = time.time()
        # A re-investigation starts clean: memory should carry other cases' lessons, not an earlier answer
        # to this same alert.
        await self.graph.query("delete_case", {"case_id": state["case_id"]})
        self._event(state, "alert", f"{alert['trigger_type']}: {alert['trigger_text']}")
        return state

    async def gather(self, state: CaseState) -> CaseState:
        """Core evidence checklist: the same baseline for every alert, before the LLM chooses follow-ups."""
        a, t = state["alert"], self.tools
        tx = str(a["flagged_txn_id"])
        ctx = await self._collect(state, "alert_context", t.alert_context(tx))
        flagged = ctx["flagged_txn"]
        await self._collect(state, "card_activity", t.card_activity(a["card_id"], flagged["ts"], flagged_tx=tx))
        if ctx.get("holder"):
            await self._collect(state, "holder_baseline", t.holder_baseline(ctx["holder"]["holder_id"], tx))
        device = ctx.get("device")
        if device:
            await self._collect(state, "device_check", t.device_check(device["device_id"], flagged["ts"]))
        await self._collect(state, "shared_origin", t.shared_origin(tx))
        await self._collect(state, "linked_cases", t.linked_cases(tx))
        await self._collect(state, "similar_cases", t.similar_cases(_describe(a, flagged, device)))
        ring_id = (device or {}).get("ring_id", -1)
        if ring_id is not None and ring_id >= 0:
            await self._collect(state, "ring", t.ring(ring_id, flagged["ts"]))
        return state

    async def investigate(self, state: CaseState) -> CaseState:
        """The LLM decides which follow-up tools to call, within a budget."""
        contents = [_user(self._case_brief(state) + "\n\n" + prompts.INVESTIGATE_TASK.format(budget=FOLLOW_UP_BUDGET))]
        tools = [types.Tool(function_declarations=FOLLOW_UP_TOOLS)]
        for _ in range(FOLLOW_UP_BUDGET + 1):
            resp = await self.llm.generate(contents, system=prompts.INVESTIGATOR, tools=tools)
            calls = resp.function_calls or []
            if not calls or any(c.name == "finish_investigation" for c in calls):
                reason = next((c.args.get("reason", "") for c in calls if c.name == "finish_investigation"), "")
                self._event(state, "analysis", f"Investigation complete: {reason or (resp.text or '')[:300]}")
                break
            contents.append(resp.candidates[0].content)
            parts = []
            for call in calls[:2]:
                result = await self._follow_up(state, call.name, dict(call.args or {}))
                parts.append(types.Part.from_function_response(name=call.name, response={"result": result}))
            contents.append(types.Content(role="user", parts=parts))
        return state

    async def _follow_up(self, state: CaseState, name: str, args: dict) -> dict:
        t, flagged = self.tools, state["evidence"]["alert_context"]["flagged_txn"]
        key = f"{name}:{json.dumps(args, sort_keys=True)}"
        if key in state.get("evidence", {}):
            return {"note": "already retrieved", "ref": state["evidence"][key]["ref"]}
        dispatch = {
            "card_activity": lambda: t.card_activity(args["card_id"], args.get("center_ts") or flagged["ts"],
                                                     int(args.get("days_before", 10)), int(args.get("days_after", 3))),
            "holder_baseline": lambda: t.holder_baseline(args["holder_id"], flagged["tx_id"]),
            "device_check": lambda: t.device_check(args["device_id"], flagged["ts"], int(args.get("days", 30))),
            "ring": lambda: t.ring(int(args["ring_id"]), flagged["ts"]),
            "similar_cases": lambda: t.similar_cases(args["description"]),
            "policy": lambda: t.policy(args["question"]),
        }
        if name not in dispatch:
            return {"error": f"unknown tool {name}"}
        result = await self._collect(state, key, dispatch[name]())
        return result or {"error": "query failed"}

    async def assess(self, state: CaseState) -> CaseState:
        prompt = self._case_brief(state) + "\n\n" + prompts.ASSESS_TASK
        resp = await self.llm.generate([_user(prompt)], system=prompts.INVESTIGATOR,
                                       response_schema=json_schema(LlmAssessment), temperature=0.1)
        raw = LlmAssessment.model_validate_json(resp.text)
        clean = self._validate(state, raw)
        state["llm_assessment"] = clean.model_dump()
        state["assessment"] = asdict(self._to_policy(state, clean))
        self._event(state, "assessment", f"verdict {clean.verdict}, p={clean.fraud_probability:.2f}, pattern "
                                         f"{clean.pattern}, exposure ${state['assessment']['exposure_usd']:,.2f}")
        return state

    def _validate(self, state: CaseState, a: LlmAssessment) -> LlmAssessment:
        """Keep only IDs the tools actually returned; make the episode consistent with the verdict."""
        led, flagged = self.tools.ledger, state["evidence"]["alert_context"]["flagged_txn"]
        dropped = []

        def keep(ids, known):
            out = []
            for i in dict.fromkeys(str(x) for x in ids):
                (out if i in known else dropped).append(i)
            return out

        affected = keep(a.affected_txn_ids, led.txns)
        if a.verdict == "legitimate":
            affected = []
        elif flagged["tx_id"] not in affected:
            affected.insert(0, flagged["tx_id"])
        affected.sort(key=lambda t: led.txns[t]["ts"])
        cards = [c for c in keep(a.connected_card_ids, led.cards) if c != state["alert"]["card_id"]]
        devices = keep(a.connected_device_ids, led.devices)
        similar = [c for c in keep(a.similar_prior_cases, led.closed_cases) if c.startswith("CC-")]
        evidence = []
        for ev in a.evidence:
            if ev.ref not in led.refs and not ev.ref.startswith(("trigger:", "evidence_request:")):
                dropped.append(f"ref {ev.ref}")
                continue
            # The source follows from the tool, not the model's wording: policy search is a document, the rest graph.
            source = "document" if led.refs.get(ev.ref) == "policy" else ev.source if ev.ref.startswith(
                ("trigger:", "evidence_request:")) else "graph"
            evidence.append(ev.model_copy(update={
                "source": source, "entity_ids": [e for e in ev.entity_ids if _dataset_id(e) and led.entity_known(e)]}))
        if dropped:
            self._event(state, "validation", f"Discarded unsupported IDs/refs from the assessment: {dropped[:12]}")
        return a.model_copy(update={
            "fraud_probability": min(max(a.fraud_probability, P_FLOOR), 1 - P_FLOOR),
            "affected_txn_ids": affected, "first_suspicious_txn_id": affected[0] if affected else "",
            "connected_card_ids": cards, "connected_device_ids": devices, "similar_prior_cases": similar,
            "evidence": evidence,
            "pattern_description": a.pattern_description if a.pattern == "undocumented" else "",
        })

    def _to_policy(self, state: CaseState, a: LlmAssessment) -> Assessment:
        led = self.tools.ledger
        exposure = round(sum(abs(led.txns[t]["amount"]) for t in a.affected_txn_ids), 2)
        s = a.signals
        return Assessment(
            verdict=a.verdict, probability=round(a.fraud_probability, 3), pattern=a.pattern, exposure_usd=exposure,
            independent_evidence=a.independent_evidence,
            customer_disputed=state["alert"]["trigger_type"] == "customer_report",
            single_signal=s.single_signal, card_testing=s.card_testing,
            card_testing_purchase_cleared_over_100=s.card_testing_purchase_cleared_over_100,
            recurring_match=s.recurring_match, shared_origin=s.shared_origin, shared_element=s.shared_element,
            linked_to_other_fraud=s.linked_to_other_fraud, coordinated_undocumented=s.coordinated_undocumented,
            connected_cards=tuple(a.connected_card_ids), evidence_conflicts=s.evidence_conflicts,
            # R10 inputs come from the episode, not the model's judgement: cards of THIS customer caught in the
            # fraud (the alert card if fraud, plus connected cards with the same customer prefix).
            customer_cards_confirmed_fraud=_customer_cards_in_episode(state["alert"], a),
            # R10 needs credentials *confirmed* compromised; no evidence available here confirms it (an inferred
            # account takeover is not a confirmation), and analysts never blocked all cards in 5,565 closed cases.
            credentials_compromised=False,
            online=led.txns[str(state["alert"]["flagged_txn_id"])]["channel"] == "online",
        )

    async def decide_initial(self, state: CaseState) -> CaseState:
        a = Assessment(**{**state["assessment"], "connected_cards": tuple(state["assessment"]["connected_cards"])})
        recs = recommend(a)
        state["initial"] = [asdict(r) for r in recs]
        state["request"] = evidence_request(a)
        self._event(state, "recommendation", "Initial: " + ", ".join(f"{r.action} ({r.route})" for r in recs))
        return state

    async def request_evidence(self, state: CaseState) -> CaseState:
        a = state["assessment"]
        self._event(state, "evidence_request", f"Requested {state['request']} (policy section 5; "
                                               f"probability {a['probability']:.2f} not decisive)")
        reply = simulate(state["request"], a["probability"], recurring=a["recurring_match"],
                         customer_reported=a["customer_disputed"])
        state["reply"] = asdict(reply)
        self._event(state, "reply",
                    f"{reply.response}: {reply.text} Probability {reply.prior:.2f} -> {reply.posterior:.2f}")
        return state

    async def decide_final(self, state: CaseState) -> CaseState:
        reply = state.get("reply")
        if not reply:
            state["final"], state["final_assessment"] = state["initial"], state["assessment"]
            return state
        a = dict(state["assessment"])
        p = min(max(reply["posterior"], P_FLOOR), 1 - P_FLOOR)
        a["probability"] = p
        a["verdict"] = "fraud" if p >= STOP_HIGH else "legitimate" if p <= STOP_LOW else "uncertain"
        a["independent_evidence"] = a["independent_evidence"] + 1
        if a["verdict"] == "legitimate":
            a.update(exposure_usd=0.0, pattern="none", shared_origin=False, linked_to_other_fraud=False,
                     coordinated_undocumented=False, connected_cards=[])
        policy_a = Assessment(**{**a, "connected_cards": tuple(a["connected_cards"])})
        recs = recommend(policy_a, reply["response"])
        state["final_assessment"], state["final"] = a, [asdict(r) for r in recs]
        self._event(state, "decision", "Final: " + ", ".join(f"{r.action} ({r.route})" for r in recs))
        return state

    async def report(self, state: CaseState) -> CaseState:
        record = self._record_for_report(state)
        prompt = prompts.REPORT_TASK + "\n\nCASE RECORD:\n" + json.dumps(record, indent=1)
        resp = await self.llm.generate([_user(prompt)], system=prompts.INVESTIGATOR,
                                       response_schema=json_schema(LlmReport), temperature=0.2)
        rep = LlmReport.model_validate_json(resp.text)
        if not state.get("reply"):
            rep = rep.model_copy(update={"what_changed": "nothing"})
        if not any(r["action"] == Action.FILE_REPORT for r in state["final"]):
            rep = rep.model_copy(update={"sar_narrative": ""})
        state["report"] = rep.model_dump()
        self._event(state, "report", rep.summary)
        return state

    async def write_back(self, state: CaseState) -> CaseState:
        state["investigation_calls"] = len(self.graph.calls)  # graph + retrieval calls, before memory writes
        answer = self._build_answer(state, written=True)
        fa, la = state["final_assessment"], state["llm_assessment"]
        final_la = self._final_llm_view(state)
        record = {
            "case_id": state["case_id"], "alert_id": state["alert"]["case_id"],
            "trigger_type": state["alert"]["trigger_type"], "status": answer["case"]["status"],
            "verdict": fa["verdict"], "fraud_probability": fa["probability"], "pattern": fa["pattern"],
            "pattern_description": final_la["pattern_description"], "exposure_usd": fa["exposure_usd"],
            "summary": state["report"]["summary"], "opened_at": state["alert"]["opened_at"],
            "sar_filed": answer["sar"]["file"], "final_actions": [r["action"] for r in state["final"]],
            "record_json": json.dumps(answer)[:60000], "flagged_txn_id": str(state["alert"]["flagged_txn_id"]),
            "affected_txn_ids": final_la["affected_txn_ids"], "card_id": state["alert"]["card_id"],
            "connected_card_ids": final_la["connected_card_ids"], "device_ids": la["connected_device_ids"],
            "similar_prior_cases": la["similar_prior_cases"],
        }
        try:
            self._event(state, "memory", f"Case written to graph as {state['case_id']}")
            await memory.write_case(self.graph, record, state["events"])
            state["written"] = True
        except Exception as exc:  # keep the answer even if write-back fails; record why
            log.exception("write-back failed")
            self._event(state, "memory_error", str(exc)[:300])
            state["written"] = False
        return state

    async def answer(self, state: CaseState) -> CaseState:
        state["answer"] = self._build_answer(state, written=state.get("written", False))
        Answer.model_validate(state["answer"])
        return state

    # ------------------------------------------------------------------ assembly
    def _final_llm_view(self, state: CaseState) -> dict:
        la = dict(state["llm_assessment"])
        if state["final_assessment"]["verdict"] == "legitimate":
            la.update(affected_txn_ids=[], first_suspicious_txn_id="", connected_card_ids=[],
                      pattern="none", pattern_description="")
        return la

    def _build_answer(self, state: CaseState, written: bool) -> dict:
        alert, fa = state["alert"], state["final_assessment"]
        la, led = self._final_llm_view(state), self.tools.ledger
        final_actions = [r["action"] for r in state["final"]]
        reply = state.get("reply")
        evidence = [e for e in la["evidence"]]
        if alert["trigger_type"] == "customer_report":
            evidence.insert(0, {"claim": f"Customer reported: {alert['trigger_text']}", "source": "customer",
                                "ref": "trigger:customer_report", "entity_ids": [str(alert["flagged_txn_id"])]})
        if reply:
            evidence.append({"claim": reply["text"], "source": "customer", "ref": "evidence_request:1",
                             "entity_ids": [str(alert["flagged_txn_id"])]})
        if Action.ESCALATE_TO_ANALYST in final_actions:
            status = "escalated"  # handed to a human analyst, whatever the verdict
        elif fa["verdict"] == "fraud":
            status = "closed_fraud"
        elif fa["verdict"] == "legitimate":
            status = "closed_legitimate"
        else:
            status = "open"
        file_sar = Action.FILE_REPORT in final_actions
        policy_a = Assessment(**{**fa, "connected_cards": tuple(fa["connected_cards"])})
        sar_reason = sar_required(policy_a, reply["response"] if reply else None)[1]
        if file_sar and not sar_required(policy_a, reply["response"] if reply else None)[0]:
            sar_reason = next(r["reason"] for r in state["final"] if r["action"] == Action.FILE_REPORT)
        dates = sorted(led.txns[t]["ts"][:10] for t in la["affected_txn_ids"])
        request_step = next((e["step"] for e in state["events"] if e["kind"] == "evidence_request"), 0)
        answer = {
            "case_id": alert["case_id"],
            "case": {
                "status": status, "verdict": fa["verdict"], "fraud_probability": fa["probability"],
                "pattern": fa["pattern"], "pattern_description": la["pattern_description"],
                "affected_txn_ids": la["affected_txn_ids"], "first_suspicious_txn_id": la["first_suspicious_txn_id"],
                "connected_card_ids": la["connected_card_ids"],
                "connected_device_profiles": [led.devices[d] for d in state["llm_assessment"]["connected_device_ids"]],
                "exposure_usd": fa["exposure_usd"], "evidence": evidence,
                "similar_prior_cases": state["llm_assessment"]["similar_prior_cases"],
                "summary": state.get("report", {}).get("summary", ""),
                "written_to_graph": written, "graph_case_id": state["case_id"] if written else "",
            },
            "evidence_requests": [{"type": state["request"], "asked_after_step": request_step,
                                   "assumed_response": reply["text"]}] if reply else [],
            "next_best_actions": {
                "initial": [_action(r) for r in state["initial"]],
                "final": [_action(r) for r in state["final"]],
                "what_changed": state.get("report", {}).get("what_changed", "nothing"),
            },
            "sar": {
                "file": file_sar, "reason": sar_reason,
                "narrative": state.get("report", {}).get("sar_narrative", "") if file_sar else "",
                "subjects": _sar_subjects(alert, la) if file_sar else [],
                "total_amount_usd": fa["exposure_usd"] if file_sar else 0,
                "activity_dates": [dates[0], dates[-1]] if file_sar and dates else [],
            },
            "stop_reason": state.get("report", {}).get("stop_reason", ""),
            "tool_calls": state.get("investigation_calls", len(self.graph.calls)),
            "tokens": self.llm.tokens,
            "latency_s": round(time.time() - state["started"], 1),
        }
        return answer

    def _case_brief(self, state: CaseState) -> str:
        alert = {k: state["alert"][k] for k in ("case_id", "opened_at", "trigger_type", "trigger_text",
                                                 "flagged_txn_id", "card_id", "customer_id", "risk_score")}
        return ("ALERT:\n" + json.dumps(alert, default=str) + "\n\nEVIDENCE (tool results; cite 'ref'):\n"
                + json.dumps(state.get("evidence", {}), default=str))

    def _record_for_report(self, state: CaseState) -> dict:
        la = self._final_llm_view(state)
        return {
            "alert": {k: state["alert"][k] for k in ("case_id", "opened_at", "trigger_type", "trigger_text")},
            "initial_assessment": {k: state["llm_assessment"][k] for k in ("verdict", "fraud_probability", "pattern",
                                                                            "reasoning", "uncertainty")},
            "final": {"verdict": state["final_assessment"]["verdict"],
                      "probability": state["final_assessment"]["probability"],
                      "pattern": la["pattern"], "pattern_description": la["pattern_description"],
                      "exposure_usd": state["final_assessment"]["exposure_usd"],
                      "affected_txns": [self.tools.ledger.txns[t] for t in la["affected_txn_ids"]],
                      "connected_cards": la["connected_card_ids"],
                      "devices": {d: self.tools.ledger.devices[d]
                                  for d in state["llm_assessment"]["connected_device_ids"]}},
            "evidence": la["evidence"],
            "evidence_request": state.get("request"), "assumed_reply": state.get("reply"),
            "initial_actions": state["initial"], "final_actions": state["final"],
            "customer_id": state["alert"]["customer_id"], "card_id": state["alert"]["card_id"],
        }


def _dataset_id(entity_id: str) -> bool:
    """IDs that exist in the dataset: transactions, cards, customers, closed cases. Holder and device IDs are
    RedThread's own derived identifiers and must not appear where the answer format expects dataset IDs."""
    return bool(re.fullmatch(r"\d+|C\d{5}(-K\d)?|CC-\d{4}", entity_id))


def _customer_cards_in_episode(alert: dict, a: LlmAssessment) -> int:
    if a.verdict != "fraud":
        return 0
    cards = {alert["card_id"], *(c for c in a.connected_card_ids if c.split("-")[0] == alert["customer_id"])}
    return len(cards)


def _sar_subjects(alert: dict, la: dict) -> list[str]:
    return list(dict.fromkeys([alert["customer_id"], alert["card_id"], *la["connected_card_ids"]]))


def _action(r: dict) -> dict:
    return {"action": str(r["action"]), "route": r["route"], "reason": r["reason"]}


def _user(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=text)])


def _describe(alert: dict, flagged: dict, device: dict | None) -> str:
    """A plain description of the alert for similar-case retrieval."""
    parts = [f"{alert['trigger_type'].replace('_', ' ')}: {alert['trigger_text']}",
             f"{flagged['channel']} transaction of ${flagged['amount']:.2f}, product {flagged['product']}"]
    if flagged.get("device_status"):
        parts.append(f"device {flagged['device_status'].lower()} for this account")
    if flagged.get("proxy"):
        parts.append(f"behind a {flagged['proxy'].split(':')[-1].lower()} proxy")
    if device and device.get("ring_id", -1) >= 0:
        parts.append("device shared with other cardholders in suspicious activity")
    return "; ".join(parts)


def _decl(name: str, description: str, properties: dict, required: list[str]) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(name=name, description=description, parameters_json_schema={
        "type": "object", "properties": properties, "required": required})


FOLLOW_UP_TOOLS = [
    _decl("card_activity", "Transactions on a card in a time window, with devices, scores and R5 detection.",
          {"card_id": {"type": "string"}, "center_ts": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"},
           "days_before": {"type": "integer"}, "days_after": {"type": "integer"}}, ["card_id"]),
    _decl("holder_baseline", "A resolved account holder's history before the alert, incl. recurring charges.",
          {"holder_id": {"type": "string"}}, ["holder_id"]),
    _decl("device_check", "Cards that used a device around the alert, and all-time cases on that device.",
          {"device_id": {"type": "string"}, "days": {"type": "integer"}}, ["device_id"]),
    _decl("ring", "Members, devices and fraud history of a ring found by connected-components analysis.",
          {"ring_id": {"type": "integer"}}, ["ring_id"]),
    _decl("similar_cases", "Vector search over closed and prior agent cases, then graph traversal to devices.",
          {"description": {"type": "string"}}, ["description"]),
    _decl("policy", "Search the fraud policy, pattern definitions and regulatory guidance.",
          {"question": {"type": "string"}}, ["question"]),
    _decl("finish_investigation", "Call when you have enough evidence to assess the case.",
          {"reason": {"type": "string"}}, ["reason"]),
]


def build(inv: Investigation):
    g = StateGraph(CaseState)
    for name in ("intake", "gather", "investigate", "assess", "decide_initial", "request_evidence",
                 "decide_final", "report", "write_back", "answer"):
        g.add_node(name, getattr(inv, name))
    g.set_entry_point("intake")
    for a, b in [("intake", "gather"), ("gather", "investigate"), ("investigate", "assess"),
                 ("assess", "decide_initial"), ("request_evidence", "decide_final"), ("decide_final", "report"),
                 ("report", "write_back"), ("write_back", "answer"), ("answer", END)]:
        g.add_edge(a, b)
    g.add_conditional_edges("decide_initial", lambda s: "request_evidence" if s.get("request") else "decide_final",
                            {"request_evidence": "request_evidence", "decide_final": "decide_final"})
    return g.compile()


async def investigate_alert(graph: McpGraph, alert: dict[str, Any],
                            on_event: Callable[[dict], None] | None = None,
                            as_of: str | None = None) -> CaseState:
    """Run one alert end to end on an open MCP session. Tool calls/tokens are counted per case.

    ``as_of`` hides cases opened at or after that time (used by the backtest to replay a closed case
    without letting the agent see its outcome)."""
    graph.calls.clear()
    inv = Investigation(graph, Llm(), on_event, as_of)
    workflow = build(inv)
    return await workflow.ainvoke({"alert": alert}, config={"recursion_limit": 40})
