import pytest

from redthread.agent.simulator import bayes, simulate


def test_bayes_update_is_symmetric_and_bounded():
    assert bayes(0.5, 8.0) == pytest.approx(0.889, abs=1e-3)
    assert bayes(0.5, 1 / 8) == pytest.approx(0.111, abs=1e-3)
    assert 0 <= bayes(0.0, 1 / 8) < bayes(1.0, 8.0) <= 1  # extreme priors are clamped, never NaN/inf


def test_reply_follows_the_evidence_before_asking():
    likely_fraud = simulate("customer_validation", 0.62, recurring=False, customer_reported=False)
    assert likely_fraud.response == "denied"
    likely_legit = simulate("customer_validation", 0.30, recurring=False, customer_reported=False)
    assert likely_legit.response == "confirmed"


def test_an_inferred_reply_cannot_move_the_belief_it_was_inferred_from():
    """The reply is derived from the prior, so scoring it as evidence is circular.

    It used to be worth eight to one, which turned every mid-range case into a confident verdict in
    the direction it already leaned — wrong ten times in thirteen on a 59-case backtest.
    """
    for prior in (0.30, 0.45, 0.62, 0.84):
        reply = simulate("customer_validation", prior, recurring=False, customer_reported=False)
        assert reply.posterior == pytest.approx(prior, abs=0.001)
        assert reply.informative is False
        assert "does not move the probability" in reply.text


def test_a_recurring_match_is_real_evidence_and_does_move_it():
    """It is read out of the holder's own history, not out of the agent's belief."""
    reply = simulate("customer_validation", 0.6, recurring=True, customer_reported=True)
    assert reply.informative is True
    assert reply.posterior < 0.3


def test_recurring_dispute_is_recognised():
    reply = simulate("customer_validation", 0.6, recurring=True, customer_reported=True)
    assert reply.response == "confirmed"
    assert "recurring" in reply.text


def test_step_up_failure_reads_as_denial():
    reply = simulate("step_up_auth", 0.7, recurring=False, customer_reported=False)
    assert reply.response == "denied"
    assert "passcode" in reply.text
    assert "Assumed" in reply.text
