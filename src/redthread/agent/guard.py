"""Quarantine text in an alert that is addressed to the agent rather than to an analyst.

Alert text is written by people, and some of it is hostile: a fake "SYSTEM NOTE", a role tag such as
``[[assistant: ...]]``, an HTML comment, or a claimed authority ("compliance already cleared this")
telling the agent what to conclude. The agent's outcome is computed by code from judged evidence, so
such text has no direct path to the answer; this module also keeps it away from the model.

The text is cut into segments. A segment that addresses the system, dictates an outcome, suppresses
an action or claims an authority nobody can verify is removed and recorded; the rest (the customer's
denial, the score, the analyst's question) is kept word for word. Nothing is inverted: a hostile
segment that happens to ask for the right outcome is removed just the same.
"""

import re
from dataclasses import dataclass, field

# (kind, pattern). Each describes text aimed at the system, not facts about the case.
PATTERNS: list[tuple[str, re.Pattern]] = [(kind, re.compile(p, re.I)) for kind, p in [
    ("role_marker", r"\bsystem\s*(note|prompt|message|override|instruction)s?\b"),
    ("role_marker", r"\[\[\s*(assistant|system|agent|ai|model)\s*:"),
    ("role_marker", r"<!--"),
    ("role_marker", r"^\s*(assistant|agent|ai|model|llm)\s*:"),
    ("override", r"\b(prior|previous|above|earlier|all)\s+(instructions?|rules?|prompts?)\b"),
    ("override", r"\b(ignore|disregard|override|forget|bypass)\b.{0,40}"
                 r"\b(instructions?|polic(y|ies)|rules?|guidelines?)\b"),
    ("outcome_directive", r"\b(classify|mark|label|treat|set)\b.{0,40}"
                          r"\b(legitimate|fraud|closed|cleared|probability)\b"),
    ("outcome_directive", r"\bfraud_probability\s*="),
    ("outcome_directive", r"\breply\s+[A-Z][A-Z_]{3,}\b"),
    # "approve it" is an instruction; "I did not approve it" is a customer's denial and is kept.
    ("outcome_directive", r"(?<!not\s)(?<!n't\s)(?<!never\s)\b(close|approve|clear)\s+(it|the\s+(case|file|alert))\b"),
    ("suppression", r"\b(do\s+not|don't|never)\s+(file|escalate|report|block|flag)\b"),
    ("suppression", r"\bskip\s+(the\s+)?(report|filing|escalation|review)\b"),
    ("suppression", r"\bno\s+need\s+to\s+(report|escalate|file|review)\b"),
    ("authority_claim", r"\b(compliance|legal|management|manager|supervisor|fraud\s+team)\b.{0,30}"
                        r"\b(already\s+)?(cleared|approved|signed\s+off|reviewed)\b"),
]]

# Boundaries between segments: sentence ends, plus the openers hostile text tends to hide behind.
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[<])|(?=\[\[)|(?=<!--)|(?=\bP\.S\.)|(?=\bAlso,\s)|(?=\bNote from\b)")


@dataclass(frozen=True)
class Finding:
    kind: str
    text: str


@dataclass(frozen=True)
class Guarded:
    text: str  # what the agent may read
    original: str
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def hostile(self) -> bool:
        return bool(self.findings)


def _kinds(segment: str) -> list[str]:
    return sorted({kind for kind, pattern in PATTERNS if pattern.search(segment)})


def guard(text: str | None) -> Guarded:
    original = text or ""
    kept, findings = [], []
    for segment in (s for s in _SPLIT.split(original) if s and s.strip()):
        kinds = _kinds(segment)
        if kinds:
            findings.append(Finding(kind=",".join(kinds), text=segment.strip()))
        else:
            kept.append(segment.strip())
    return Guarded(text=" ".join(kept), original=original, findings=tuple(findings))
