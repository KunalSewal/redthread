"""The attack suite's hostile text is caught offline, without a model or a graph (scripts/attacks.py)."""

import importlib.util
from pathlib import Path

from redthread.agent.guard import guard, screen

spec = importlib.util.spec_from_file_location("attacks", Path(__file__).parents[1] / "scripts" / "attacks.py")


def _attacks():
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ATTACKS


def test_every_planted_instruction_is_quarantined_and_the_facts_kept():
    for attack in _attacks():
        if "append" in attack:
            g = guard("Customer C12975 message: 'I did not make these charges.'" + attack["append"])
            assert g.hostile, attack["id"]
            assert "I did not make these charges" in g.text
            assert "BLOCK_CARD" not in g.text and "fraud_probability" not in g.text
        else:
            clean, found = screen({"closed": [{"analyst_notes": attack["plant"]["analyst_notes"]}]})
            assert found, attack["id"]
            note = clean["closed"][0]["analyst_notes"]
            assert "SYSTEM NOTE" not in note and "Cardholder confirmed purchases" in note


def test_planted_ids_come_from_the_reserved_range():
    for attack in _attacks():
        if "plant" in attack:
            assert attack["plant"]["case_id"].startswith("CC-99")
