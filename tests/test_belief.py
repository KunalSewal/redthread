import pytest

from redthread.belief import P_FLOOR, Judged, assess, prior_for, weigh, without


def item(basis, direction="incriminating", strength="strong"):
    return Judged(basis=basis, direction=direction, strength=strength, claim=f"{basis} {direction}")


def test_prior_comes_from_the_trigger():
    assert prior_for("customer_report", 0.004)[0] == 0.6  # a denial, not the model, starts the case
    assert prior_for("analyst_request", None)[0] == 0.5
    low = prior_for("risk_score", 0.001)[0]
    high = prior_for("risk_score", 0.99)[0]
    assert 0.05 <= low < high <= 0.90  # calibrated, but never starting at certainty


def test_only_the_strongest_item_per_basis_counts():
    ledger = weigh([item("device", strength="weak"), item("device", strength="decisive"),
                    item("device", strength="moderate"), item("holder_behaviour")], model_is_prior=False)
    counted = [i for i in ledger if i.counted]
    assert len(counted) == 2
    assert {i.basis for i in counted} == {"device", "holder_behaviour"}
    assert next(i for i in counted if i.basis == "device").strength == "decisive"


def test_model_score_is_not_counted_twice_when_it_set_the_prior():
    items = [item("flagged_transaction_model", strength="decisive"), item("device")]
    belief = assess("risk_score", 0.9, items)
    assert belief.independent_evidence == 1
    assert not belief.ledger[0].counted
    # For a customer report the prior is the dispute, so the model score is evidence in its own right.
    disputed = assess("customer_report", 0.9, items)
    assert disputed.independent_evidence == 2
    assert disputed.ledger[0].lr_applied == pytest.approx(8.0)  # capped


def test_exculpatory_evidence_lowers_the_probability():
    up = assess("analyst_request", None, [item("device")])
    down = assess("analyst_request", None, [item("device", direction="exculpatory")])
    assert down.posterior < 0.5 < up.posterior


def test_conflicting_evidence_lands_in_the_uncertain_band():
    belief = assess("risk_score", 0.35, [item("device"), item("holder_behaviour", direction="exculpatory")])
    assert 0.15 < belief.posterior < 0.85
    assert belief.verdict == "uncertain"


def test_strong_agreement_reaches_a_decisive_verdict():
    belief = assess("customer_report", 0.02, [item("device", strength="decisive"),
                                              item("cross_card_links", strength="strong"),
                                              item("customer_statement", strength="strong")])
    assert belief.posterior >= 0.85
    assert belief.verdict == "fraud"
    assert belief.independent_evidence == 3


def test_probability_never_claims_certainty():
    overwhelming = [item(b, strength="decisive") for b in
                    ("device", "cross_card_links", "prior_cases", "customer_statement", "amount_or_timing")]
    assert assess("customer_report", 0.99, overwhelming).posterior == 1 - P_FLOOR
    exculpating = [Judged(b, "exculpatory", "decisive") for b in
                   ("device", "holder_behaviour", "amount_or_timing", "prior_cases")]
    assert assess("risk_score", 0.9, exculpating).posterior == P_FLOOR


def test_no_evidence_leaves_the_prior_untouched():
    belief = assess("risk_score", 0.35, [])
    assert belief.posterior == pytest.approx(belief.prior, abs=0.01)
    assert belief.independent_evidence == 0


def test_counterfactual_drops_a_line_and_recomputes():
    items = [item("device", strength="decisive"), item("holder_behaviour")]
    belief = assess("risk_score", 0.2, items)
    weaker = without(belief, {0}, "risk_score", 0.2)
    assert weaker.posterior < belief.posterior
    assert weaker.independent_evidence == belief.independent_evidence - 1


def test_explanation_is_readable():
    belief = assess("customer_report", 0.02, [item("device"), item("holder_behaviour", direction="exculpatory")])
    text = belief.explain()
    assert "prior 0.60" in text and "device strong up" in text and "->" in text
