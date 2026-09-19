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
