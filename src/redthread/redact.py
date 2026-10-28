"""Redaction for logs and traces: secrets and personal data never leave in plain text.

Covers the values of our own secrets (read from the environment, so a password echoed inside an
error message is caught), API-key and bearer-token shapes, e-mail addresses, phone numbers and
card-number-length digit runs. Dataset identifiers are not personal data and are kept: transaction
IDs are 7 digits, cards and customers are pseudonymous codes, and the audit trail needs them.
"""

import logging
import os
import re

SECRET_ENV = ("TG_PASSWORD", "TG_SECRET", "TG_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY")
_PATTERNS = [
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "[redacted-api-key]"),
    (re.compile(r"\bsk-[0-9A-Za-z_\-]{20,}"), "[redacted-api-key]"),
    (re.compile(r"(?i)\bbearer\s+[0-9A-Za-z_\-\.=]{16,}"), "Bearer [redacted-token]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[=:]\s*\S+"), r"\1=[redacted]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[redacted-email]"),
    # Card numbers come in 4-digit groups (or 13-19 contiguous digits). Two 7-digit transaction IDs
    # side by side ("3660353 3660354") do not fit the grouping, so audit IDs survive.
    (re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{1,7}(?!\d)"), "[redacted-card-number]"),
    (re.compile(r"(?<![\w.])\+\d{1,3}[ -]?\d(?:[ -]?\d){8,11}(?!\d)"), "[redacted-phone]"),  # +country code
    (re.compile(r"(?<!\d)[6-9]\d{4}[ -]?\d{5}(?!\d)"), "[redacted-phone]"),  # Indian mobile
    (re.compile(r"(?<!\d)\(?\d{3}\)?[ -]\d{3}[ -]\d{4}(?!\d)"), "[redacted-phone]"),  # (555) 123-4567
]


def _secret_values() -> list[str]:
    return [v for v in (os.environ.get(k, "") for k in SECRET_ENV) if len(v) >= 6]


def redact(text: str) -> str:
    if not text:
        return text
    for secret in _secret_values():
        text = text.replace(secret, "[redacted-secret]")
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_obj(obj):
    """Redact every string inside a JSON-like structure (a trace or a halt record)."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    return obj


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info and record.exc_info[1] is not None:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


def install() -> None:
    """Attach the filter to every handler in use: the root's, and those of loggers that keep their
    own (uvicorn's do), so no log line leaves unredacted."""
    loggers = [logging.getLogger()] + [lg for lg in logging.root.manager.loggerDict.values()
                                       if isinstance(lg, logging.Logger)]
    handlers = {h for lg in loggers for h in lg.handlers} or {logging.lastResort}
    for handler in handlers:
        if handler is not None and not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
