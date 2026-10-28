"""The policy engine, checked against the organisers' own grader.

Round 1 lost a policy point on HHG-014 (R9: an undocumented pattern needs FILE_REPORT). Rather than
re-derive the grader's rules, this runs its ``grade_case`` over the engine's plans for every
combination of the inputs those rules read, and fails on any policy finding.
"""

import importlib.util
import itertools

import pytest

from redthread import paths
from redthread.agent.simulator import simulate
from redthread.policy import Action, Assessment, after_reply, evidence_request, recommend, sar_required

GRADER = paths.DATA_R2 / "grader" / "grade.py"
pytestmark = pytest.mark.skipif(not GRADER.exists(), reason="Round 2 grader not present")


@pytest.fixture(scope="module")
def grade_case():
    spec = importlib.util.spec_from_file_location("official_grader", GRADER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.grade_case


def answer(a: Assessment, initial, final, cid="HHX-001") -> dict:
    """The fields the grader reads, laid out as our answer builder writes them."""
    acts = lambda recs: [{"action": r.action.value, "route": r.route, "reason": r.reason} for r in recs]  # noqa: E731
    fin = acts(final)
    fraudish = a.verdict != "legitimate"
    return {
        "case_id": cid,
        "case": {
            "verdict": a.verdict, "fraud_probability": a.probability, "pattern": a.pattern,
            "affected_txn_ids": ["1"] if fraudish else [], "first_suspicious_txn_id": "1" if fraudish else "",
            "exposure_usd": a.exposure_usd if fraudish else 0.0,
            "connected_card_ids": list(a.connected_cards) if fraudish else [],
        },
        "next_best_actions": {"initial": acts(initial), "final": fin,
                              "what_changed": "" if initial == final else "the reply changed the plan"},
        "sar": {"file": any(x["action"] == Action.FILE_REPORT.value for x in fin)},
        "evidence_requests": [],
    }


def test_r9_an_undocumented_pattern_files_a_report_even_when_uncertain():
    """HHG-014: undocumented, uncertain at 0.81. The bank filed a report; we did not."""
    a = Assessment(verdict="uncertain", probability=0.81, pattern="undocumented", exposure_usd=187.33,
                   independent_evidence=4, coordinated_undocumented=True, connected_cards=("C1-K1",))
    acts = {r.action for r in recommend(a)}
    assert {Action.CREATE_CASE, Action.FILE_REPORT, Action.ESCALATE_TO_ANALYST} <= acts
    assert sar_required(a)[0]


def test_r9_holds_when_the_coordination_signal_was_dropped():
    """The pattern can stay undocumented after an unbacked cross-card flag is removed."""
    a = Assessment(verdict="uncertain", probability=0.7, pattern="undocumented", exposure_usd=50.0,
                   independent_evidence=3)
    acts = {r.action for r in recommend(a)}
    assert {Action.CREATE_CASE, Action.FILE_REPORT, Action.ESCALATE_TO_ANALYST} <= acts


def test_3a_fraud_connected_to_other_cards_files_a_report_however_small():
    """The brief: 'A $23 loss that connects to other cards still needs a report.'"""
    a = Assessment(verdict="fraud", probability=0.95, pattern="card_not_present_fraud", exposure_usd=23.0,
                   independent_evidence=3, connected_cards=("C2-K1",))
    assert Action.FILE_REPORT in {r.action for r in recommend(a)}


def test_a_confirmed_reply_never_files_a_report():
    a = Assessment(verdict="uncertain", probability=0.6, pattern="undocumented", exposure_usd=50.0,
                   independent_evidence=3, coordinated_undocumented=True)
    assert Action.FILE_REPORT not in {r.action for r in recommend(a, "confirmed")}


def test_no_plan_the_engine_makes_draws_a_grader_policy_finding(grade_case):
    combos = itertools.product(
        (("legitimate", 0.03), ("uncertain", 0.5), ("uncertain", 0.81), ("fraud", 0.9)),
        ("none", "card_not_present_fraud", "undocumented", "card_testing"),
        (23.0, 800.0, 1500.0, 3000.0),
        ((), ("C2-K1",)),
        (False, True),  # customer report
        (False, True),  # the holder's recurring-charge match
    )
    checked = 0
    for (verdict, p), pattern, exposure, connected, disputed, recurring in combos:
        if verdict == "legitimate" and pattern != "none":
            continue  # the answer builder never names a pattern for a legitimate verdict
        if verdict != "legitimate" and pattern == "none":
            continue
        if verdict == "legitimate":
            exposure, connected = 0.0, ()  # as _to_policy: no episode, so no exposure and no ring
        a = Assessment(verdict=verdict, probability=p, pattern=pattern, exposure_usd=exposure,
                       independent_evidence=3, customer_disputed=disputed, connected_cards=connected,
                       recurring_match=recurring,
                       coordinated_undocumented=pattern == "undocumented", card_testing=pattern == "card_testing")
        # As in the pipeline: a reply exists only when the policy asked, and the simulator chooses it.
        request = evidence_request(a)
        initial, final_a, response = recommend(a), a, None
        if request:
            reply = simulate(request, p, recurring=recurring, customer_reported=disputed)
            final_a, response = after_reply(a, reply.posterior, reply.informative, reply.response), reply.response
        final = recommend(final_a, response)
        meta = {"trigger_type": "customer_report" if disputed else "risk_score", "flagged_txn_id": "1"}
        findings = [f for f in grade_case("HHX-001", answer(final_a, initial, final), meta, {}) if f[0] != "warning"]
        assert not findings, (verdict, p, pattern, exposure, connected, disputed, response, findings)
        checked += 1
    assert checked > 300
