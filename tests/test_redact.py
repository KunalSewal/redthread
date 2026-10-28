"""Secrets and personal data are redacted from logs and traces; dataset identifiers are kept."""

import logging

from redthread.redact import RedactingFilter, redact, redact_obj


def test_our_own_secret_values_are_redacted_wherever_they_appear(monkeypatch):
    monkeypatch.setenv("TG_PASSWORD", "hunter2-very-secret")
    out = redact("login failed for user x with password hunter2-very-secret at host")
    assert "hunter2" not in out


def test_key_and_token_shapes_are_redacted():
    assert "AIza" not in redact("key AIzaSyA1234567890abcdefghijklmnopqrstuv")
    assert "abcdefghijklmnopqrst" not in redact("Authorization: Bearer abcdefghijklmnopqrstuvwx")
    assert "s3cr3t" not in redact("api_key=s3cr3t-value")


def test_personal_data_is_redacted():
    out = redact("Customer wrote: call me on +91 98765 43210 or mail asha.rao@example.com, card 4111 1111 1111 1111")
    assert "asha.rao@example.com" not in out and "4111 1111 1111 1111" not in out and "98765" not in out


def test_dataset_identifiers_survive():
    text = "Transaction 3660353 on card C09241-K2 (customer C09241), device D004630, case CC-5579, HHF-011"
    assert redact(text) == text


def test_traces_are_redacted_throughout():
    trace = {"alert": {"trigger_text": "mail me at a@b.co"}, "events": [{"detail": "token=abc123secret"}]}
    out = redact_obj(trace)
    assert "a@b.co" not in str(out) and "abc123secret" not in str(out)


def test_the_log_filter_redacts_messages_and_tracebacks(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key-123456")
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "call failed with %s", ("gem-key-123456",), None)
    RedactingFilter().filter(record)
    assert "gem-key-123456" not in record.getMessage()


def test_adjacent_transaction_ids_are_not_mistaken_for_card_or_phone_numbers():
    text = "affected 3660353 3660354 3660355 and 3008657|3011862, TransactionDT 18489547"
    assert redact(text) == text
