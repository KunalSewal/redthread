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
