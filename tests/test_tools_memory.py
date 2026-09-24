"""The agent reads back its own earlier cases only once a person has ruled on them."""

import asyncio

from redthread.agent.tools import Tools


class FakeGraph:
    def __init__(self):
        self.calls = []

    async def query(self, name, params):
        self.calls.append(name)
        if name == "reviewed_agent_cases":
            return [{"case_ids": ["CASE-HHG-002"]}]
        return [{"agent": [{"case_id": "CASE-HHG-002"}, {"case_id": "CASE-MON-001"}]}]


def test_unreviewed_agent_cases_are_never_shown():
    graph = FakeGraph()
    tools = Tools(graph, as_of="2016-12-01 00:00:00")
    res = asyncio.run(tools._q("linked_cases", tx="1"))
    assert graph.calls == ["reviewed_agent_cases", "linked_cases"]  # the filter is loaded first
    assert tools._reviewed_only(res[0]["agent"]) == [{"case_id": "CASE-HHG-002"}]
    assert tools._reviewed_only(["CASE-MON-001", "CASE-HHG-002"]) == ["CASE-HHG-002"]


def test_nothing_is_shown_before_the_filter_is_loaded():
    tools = Tools(FakeGraph())
    assert tools._reviewed_only(["CASE-HHG-002"]) == []
