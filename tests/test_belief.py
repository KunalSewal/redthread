import pytest

from redthread.belief import P_FLOOR, Judged, assess, prior_for, weigh, without


def item(basis, direction="incriminating", strength="strong"):
    return Judged(basis=basis, direction=direction, strength=strength, claim=f"{basis} {direction}")


def test_prior_comes_from_the_trigger():
    # A denial opens the case but does not decide it: neutral, so the evidence moves it.
    assert prior_for("customer_report", 0.004)[0] == 0.5
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
                    ("device", "cross_card_links", "prior_cases", "customer_statement",
                     "amount_or_timing", "region", "holder_behaviour")]
    assert assess("customer_report", 0.99, overwhelming).posterior == 1 - P_FLOOR
    exculpating = [Judged(b, "exculpatory", "decisive") for b in
                   ("device", "holder_behaviour", "amount_or_timing", "prior_cases",
                    "cross_card_links", "region")]
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
    assert "prior 0.50" in text and "device strong up" in text and "->" in text


def test_findings_sharing_an_entity_do_not_compound_as_independent():
    """Three bases, one device: the later findings carry half their weight in log-odds."""
    items = [
        Judged(basis="device", direction="incriminating", strength="strong", entities=("D004630",)),
        Judged(basis="cross_card_links", direction="incriminating", strength="strong",
               entities=("D004630", "C05448-K2")),
        Judged(basis="prior_cases", direction="incriminating", strength="strong",
               entities=("D004630", "CC-2649")),
    ]
    ledger = weigh(items, model_is_prior=False)
    assert [w.counted for w in ledger] == [True, True, True]
    assert [w.discounted for w in ledger] == [False, True, True]
    assert ledger[0].lr_applied == pytest.approx(8.0)
    assert ledger[1].lr_applied == pytest.approx(8.0 ** 0.5)
    assert ledger[2].lr_applied == pytest.approx(8.0 ** 0.5)


def test_independent_entities_still_compound_fully():
    items = [
        Judged(basis="device", direction="incriminating", strength="strong", entities=("D004630",)),
        Judged(basis="holder_behaviour", direction="incriminating", strength="strong",
               entities=("C13487-K1",)),
    ]
    ledger = weigh(items, model_is_prior=False)
    assert [w.discounted for w in ledger] == [False, False]
    assert all(w.lr_applied == pytest.approx(8.0) for w in ledger)


def test_evidence_with_no_entity_ids_is_never_treated_as_correlated():
    items = [
        Judged(basis="device", direction="incriminating", strength="strong", entities=()),
        Judged(basis="region", direction="incriminating", strength="moderate", entities=()),
    ]
    ledger = weigh(items, model_is_prior=False)
    assert [w.discounted for w in ledger] == [False, False]


def test_the_card_under_investigation_never_correlates_two_findings():
    """Every claim names the subject card; that must not halve the weight of all but one."""
    subject = frozenset({"C02923-K1"})
    items = [
        Judged(basis="device", direction="incriminating", strength="strong",
               entities=("C02923-K1", "D000178")),
        Judged(basis="holder_behaviour", direction="incriminating", strength="strong",
               entities=("C02923-K1",)),
    ]
    ledger = weigh(items, model_is_prior=False, subject=subject)
    assert [w.discounted for w in ledger] == [False, False]
    assert all(w.lr_applied == pytest.approx(8.0) for w in ledger)
    # but a genuinely shared third-party entity still correlates them
    items[1] = Judged(basis="holder_behaviour", direction="incriminating", strength="strong",
                      entities=("C02923-K1", "D000178"))
    assert [w.discounted for w in weigh(items, model_is_prior=False, subject=subject)] == [False, True]


def test_ids_are_read_out_of_the_claim_text():
    """The model names the device in the prose but often omits it from entity_ids, and that device
    is exactly what makes two findings correlated. A silent failure here disables the rule, so the
    pattern is asserted directly."""
    from types import SimpleNamespace

    from redthread.agent.graph import _claim_entities

    e = SimpleNamespace(
        claim="Device D004630 belongs to ring 36700632, seen on C05448-K2 in case CC-2649 (txn 3478561)",
        entity_ids=["C13487-K1"])
    found = set(_claim_entities(e))
    assert {"D004630", "C05448-K2", "CC-2649", "3478561", "C13487-K1"} <= found
    assert "belongs" not in found


def test_striking_out_a_line_promotes_the_next_one_in_that_basis():
    """The counterfactual must reweigh, not just remove: corroboration becomes the counted line."""
    items = [
        Judged(basis="device", direction="incriminating", strength="strong", claim="strong device",
               entities=("D1",)),
        Judged(basis="device", direction="incriminating", strength="weak", claim="weak device",
               entities=("D1",)),
    ]
    belief = assess("analyst_request", None, items)
    assert [w.counted for w in belief.ledger] == [True, False]
    dropped = without(belief, {0}, "analyst_request", None)
    assert [w.counted for w in dropped.ledger] == [True]
    assert dropped.ledger[0].claim == "weak device"
    assert dropped.posterior < belief.posterior


def test_a_counterfactual_keeps_the_subject_exclusion():
    subject = frozenset({"C1"})
    items = [
        Judged(basis="device", direction="incriminating", strength="strong", entities=("C1", "D1")),
        Judged(basis="region", direction="incriminating", strength="strong", entities=("C1",)),
        Judged(basis="prior_cases", direction="incriminating", strength="weak", entities=("C1",)),
    ]
    belief = assess("analyst_request", None, items, subject)
    assert not any(w.discounted for w in belief.ledger)
    # Dropping a line must not suddenly make the subject card correlate the survivors.
    assert not any(w.discounted for w in without(belief, {0}, "analyst_request", None).ledger)


def test_evidence_is_tempered_so_correlated_bases_do_not_multiply_into_certainty():
    """Six findings pointing one way should raise belief, not settle it.

    Untempered, six moderate findings multiply to 3^6 = 729 and land at the clamp. Bases are not
    independent in a real fraud, so the sum is tempered before it becomes a probability.
    """
    six = [item(b, strength="moderate") for b in
           ("device", "cross_card_links", "prior_cases", "holder_behaviour", "amount_or_timing", "region")]
    belief = assess("analyst_request", None, six)
    assert belief.independent_evidence == 6
    assert 0.7 < belief.posterior < 1 - P_FLOOR  # convinced, not certain
    # and it still beats the same evidence with two findings
    two = [item(b, strength="moderate") for b in ("device", "region")]
    assert assess("analyst_request", None, two).posterior < belief.posterior


def test_tempering_leaves_the_direction_of_the_evidence_alone():
    up = assess("analyst_request", None, [item("device", strength="strong")])
    down = assess("analyst_request", None, [item("device", "exculpatory", "strong")])
    assert up.posterior > 0.5 > down.posterior
