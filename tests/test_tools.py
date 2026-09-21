from redthread.agent.mcp_graph import _parse
from redthread.agent.tools import _card_testing, _regular


def row(tx_id, ts, amount, channel="online"):
    return {"tx_id": tx_id, "ts": ts, "amount": amount, "channel": channel}


def test_card_testing_sequence_detected():
    rows = [row("1", "2016-11-14 09:12:00", 1.10), row("2", "2016-11-14 09:30:00", 2.40),
            row("3", "2016-11-14 09:52:00", 0.95), row("4", "2016-11-14 10:31:00", 259.98)]
    found = _card_testing(rows)
    assert found == [{"small_auths": ["1", "2", "3"], "followed_by": ["4"], "purchase_over_100_cleared": True}]


def test_card_testing_needs_three_small_auths_within_an_hour():
    rows = [row("1", "2016-11-14 09:12:00", 1.10), row("2", "2016-11-14 10:30:00", 2.40),
            row("3", "2016-11-14 11:52:00", 0.95), row("4", "2016-11-14 12:31:00", 259.98)]
    assert _card_testing(rows) == []


def test_in_person_small_amounts_are_not_card_testing():
    rows = [row(str(i), f"2016-11-14 09:{10 + i}:00", 2.0, "in_person") for i in range(3)]
    rows.append(row("9", "2016-11-14 10:00:00", 300.0))
    assert _card_testing(rows) == []


def test_recurring_cadence():
    assert _regular([7.0, 7.1, 6.9])["cadence"] == "weekly"
    assert _regular([30.0, 31.0, 29.5])["cadence"] == "monthly"
    assert _regular([3.0, 40.0, 11.0])["recurring"] is False
    assert _regular([7.0])["recurring"] is False


def test_mcp_response_parsing_ignores_trailing_text():
    text = '```json\n{"success": true, "data": {"result": [1]}}\n```\n\nSuggestions: {"not": "json"'
    assert _parse(text)["data"]["result"] == [1]


def test_a_policy_rule_is_looked_up_by_name_not_by_similarity():
    """Vector search finds the right rule about one time in five: "R6" carries almost no semantic
    signal, so the neighbours come back as unrelated policy prose and sanctions-list noise. The rule
    is matched by its section name instead."""
    import asyncio

    from redthread.agent.tools import Ledger, Tools

    tools = Tools.__new__(Tools)
    tools.ledger = Ledger()
    tools._policy_sections = [
        {"chunk_id": "DOC-1", "section": "Rule R1: Verify before you block on a weak signal",
         "content": "R1 text", "source": "fraud_policy"},
        {"chunk_id": "DOC-6", "section": "Rule R6: Shared origin", "content": "R6 text",
         "source": "fraud_policy"},
        {"chunk_id": "DOC-9", "section": "Section 3a. A case is not a report", "content": "3a text",
         "source": "fraud_policy"},
    ]
    assert asyncio.run(tools.policy_rule("R6"))["section"] == "Rule R6: Shared origin"
    assert asyncio.run(tools.policy_rule("3a"))["section"] == "Section 3a. A case is not a report"
    # R1 must not match "R10", and a rule that does not exist must not match anything.
    assert asyncio.run(tools.policy_rule("R10")) is None
    assert asyncio.run(tools.policy_rule("R99")) is None
