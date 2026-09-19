import pytest

from redthread.agent.simulator import bayes, simulate


def test_bayes_update_is_symmetric_and_bounded():
    assert bayes(0.5, 8.0) == pytest.approx(0.889, abs=1e-3)
    assert bayes(0.5, 1 / 8) == pytest.approx(0.111, abs=1e-3)
    assert 0 <= bayes(0.0, 1 / 8) < bayes(1.0, 8.0) <= 1  # extreme priors are clamped, never NaN/inf


def test_reply_follows_the_evidence_before_asking():
    likely_fraud = simulate("customer_validation", 0.62, recurring=False, customer_reported=False)
    assert likely_fraud.response == "denied" and likely_fraud.posterior > 0.9
    likely_legit = simulate("customer_validation", 0.30, recurring=False, customer_reported=False)
    assert likely_legit.response == "confirmed" and likely_legit.posterior < 0.1


def test_recurring_dispute_is_recognised():
    reply = simulate("customer_validation", 0.6, recurring=True, customer_reported=True)
    assert reply.response == "confirmed"
    assert "recurring" in reply.text


def test_step_up_failure_reads_as_denial():
    reply = simulate("step_up_auth", 0.7, recurring=False, customer_reported=False)
    assert reply.response == "denied"
    assert "passcode" in reply.text
    assert "Assumed" in reply.text
