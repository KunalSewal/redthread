"""Fail closed: when the graph, the tool layer or the model fails, the investigation stops and says so.

The final round's drills inject exactly these faults: a dependency failing mid-run, a model call that
times out or returns garbage. Expected: a clear error, no invented answer, no false "saved" status.
"""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from redthread.agent import llm as llm_module
from redthread.agent import mcp_graph
from redthread.agent.graph import Investigation, InvestigationHalted, halt_record
from redthread.agent.llm import Llm, ModelError
from redthread.agent.mcp_graph import GraphToolError, McpGraph


class Shape(BaseModel):
    verdict: str


class FakeLlm:
    def __init__(self, outputs):
        self.outputs, self.tokens = list(outputs), 0

    async def generate(self, contents, **kwargs):
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(text=out, function_calls=[])


def investigation(llm=None) -> Investigation:
    return Investigation(SimpleNamespace(calls=[]), llm or FakeLlm([]))


def test_a_failed_graph_query_halts_instead_of_continuing():
    inv, state = investigation(), {"case_id": "CASE-X", "events": []}

    async def failing():
        raise GraphToolError("card_window(...) failed: connection reset")

    with pytest.raises(InvestigationHalted) as exc:
        asyncio.run(inv._collect(state, "card_activity", failing()))
    assert exc.value.stage == "card_activity"
    assert "evidence" not in state  # nothing partial was recorded as if it were evidence
    assert state["events"][-1]["kind"] == "halted"


def test_an_unreachable_model_halts():
    inv, state = investigation(FakeLlm([ModelError("model unavailable after 4 attempts")])), {"events": []}
    with pytest.raises(InvestigationHalted) as exc:
        asyncio.run(inv._generate(state, "investigate", []))
    assert exc.value.stage == "investigate" and "unavailable" in exc.value.reason


def test_malformed_model_output_is_retried_once_then_halts():
    inv, state = investigation(FakeLlm(["not json", "{also not json"])), {"events": []}
    with pytest.raises(InvestigationHalted) as exc:
        asyncio.run(inv._structured(state, "assess", "prompt", Shape, temperature=0.1))
    assert exc.value.stage == "assess" and "validation" in exc.value.reason


def test_one_malformed_output_then_a_good_one_succeeds():
    inv = investigation(FakeLlm(["garbage", '{"verdict": "fraud"}']))
    assert asyncio.run(inv._structured({"events": []}, "assess", "p", Shape, temperature=0.1)).verdict == "fraud"


def test_a_halt_leaves_a_record_that_claims_nothing_was_saved():
    exc = InvestigationHalted("open_case", "graph unavailable", [{"kind": "halted"}])
    rec = halt_record({"case_id": "HHF-001"}, exc)
    assert rec["status"] == "halted" and rec["answer_written"] is False and rec["stage"] == "open_case"


def test_a_hung_graph_query_times_out_as_a_tool_error(monkeypatch):
    monkeypatch.setattr(mcp_graph, "QUERY_TIMEOUT_S", 0.05)

    class Hung:
        async def call_tool(self, *a, **k):
            await asyncio.sleep(5)

    g = McpGraph.__new__(McpGraph)
    g._session, g.calls = Hung(), []
    with pytest.raises(GraphToolError, match="timed out"):
        asyncio.run(g.query("card_window", {}))


def test_a_dropped_graph_session_is_a_tool_error():
    class Dropped:
        async def call_tool(self, *a, **k):
            raise ConnectionResetError("peer closed")

    g = McpGraph.__new__(McpGraph)
    g._session, g.calls = Dropped(), []
    with pytest.raises(GraphToolError, match="could not reach the graph"):
        asyncio.run(g.query("alert_context", {}))


def test_a_model_that_never_answers_raises_a_model_error(monkeypatch):
    monkeypatch.setattr(llm_module, "CALL_TIMEOUT_S", 0.05)

    async def never(**kwargs):
        await asyncio.sleep(5)

    model = Llm.__new__(Llm)
    model.tokens = 0
    model.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=never)))
    with pytest.raises(ModelError, match="no response"):
        asyncio.run(model.generate([], system="s", attempts=2))


def test_an_invalid_alert_is_refused_before_anything_runs():
    from redthread.agent.graph import _invalid_alert

    good = {"case_id": "HHF-001", "trigger_type": "risk_score", "flagged_txn_id": "3660108", "card_id": "C05061-K1",
            "opened_at": "2017-01-15 06:00:00"}
    assert _invalid_alert(good) == []
    bad = _invalid_alert({**good, "trigger_type": "rumour", "flagged_txn_id": "3660108; DROP GRAPH",
                          "opened_at": "yesterday", "card_id": ""})
    assert any("trigger_type" in p for p in bad) and any("not a transaction ID" in p for p in bad)
    assert any("timestamp" in p for p in bad) and "missing card_id" in bad
    inv, state = investigation(), {"alert": {**good, "flagged_txn_id": "nan"}, "events": []}
    with pytest.raises(InvestigationHalted) as exc:
        asyncio.run(inv.intake(state))
    assert exc.value.stage == "intake" and "missing flagged_txn_id" in exc.value.reason


def test_a_result_missing_what_it_must_hold_halts():
    inv, state = investigation(), {"case_id": "CASE-X", "events": []}

    async def no_such_txn():
        return [][0]  # alert_context on a transaction the graph does not hold

    with pytest.raises(InvestigationHalted) as exc:
        asyncio.run(inv._collect(state, "alert_context", no_such_txn()))
    assert "unexpected result" in exc.value.reason
