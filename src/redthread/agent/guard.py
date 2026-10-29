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
    # Instructions about how to weigh the evidence, which the model does decide (ATK-4).
    ("evidence_directive", r"\b(mark|treat|judge|weigh|rate|score|count|consider)\b.{0,60}"
                           r"\b(exculpatory|incriminating|decisive|strength|weight)\b"),
    # "approve it" is an instruction; "I did not approve it" is a customer's denial and is kept.
    ("outcome_directive", r"(?<!not\s)(?<!n't\s)(?<!never\s)\b(close|approve|clear)\s+(it|the\s+(case|file|alert))\b"),
    ("suppression", r"\b(do\s+not|don't|never)\s+(file|escalate|report|block|flag)\b"),
    ("suppression", r"\bskip\s+(the\s+)?(report|filing|escalation|review)\b"),
    ("suppression", r"\bno\s+need\s+to\s+(report|escalate|file|review)\b"),
    ("authority_claim", r"\b(compliance|legal|management|manager|supervisor|fraud\s+team)\b.{0,30}"
                        r"\b(already\s+)?(cleared|approved|signed\s+off|reviewed)\b"),
]]

# A role-tagged block or an HTML comment is one unit however many sentences it holds: splitting
# "[[assistant: ... . When you judge the evidence, mark ...]]" at the full stop let its second half
# through as ordinary text (found by ATK-4, 29 Oct).
_BLOCK = re.compile(r"\[\[.*?(?:\]\]|$)|<!--.*?(?:-->|$)", re.S)
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


# Only scripts/attacks.py turns this off, in its own process, to measure what an attack does when
# nothing stands in its way. There is deliberately no environment variable or setting for it.
DEFENCES = True


def guard(text: str | None) -> Guarded:
    original = text or ""
    if not DEFENCES:
        return Guarded(text=original, original=original)
    kept, findings = [], []
    blocks = _BLOCK.findall(original)
    for block in blocks:
        findings.append(Finding(kind=",".join(_kinds(block) or ["role_marker"]), text=block.strip()))
    for segment in (s for s in _SPLIT.split(_BLOCK.sub(" ", original)) if s and s.strip()):
        kinds = _kinds(segment)
        if kinds:
            findings.append(Finding(kind=",".join(kinds), text=segment.strip()))
        else:
            kept.append(" ".join(segment.split()))  # a removed block leaves only its spaces
    return Guarded(text=" ".join(kept), original=original, findings=tuple(findings))


# Free text that tool results carry from people: analysts' notes on closed cases and the summaries
# on earlier agent cases. Measured on all 5,585 closed-case notes: none is flagged. The policy and
# regulatory passages are a curated corpus loaded by build_knowledge, not text people write at run
# time, and are not screened: their own wording ("Do not block." in R7) would be cut. The digests'
# own fields (refs, notes on how to read a number) are written by this code.
FREE_TEXT_KEYS = frozenset({"analyst_notes", "summary"})


def screen(obj, path: str = "") -> tuple[object, list[dict]]:
    """Guard every free-text field in a tool result, as the alert text is guarded.

    Returns the result with hostile segments removed and a record of each one (where it was found and
    what it said), so a note planted in the case history reaches neither the model nor the answer.
    """
    findings: list[dict] = []
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in FREE_TEXT_KEYS and isinstance(v, str):
                g = guard(v)
                out[k] = g.text if g.hostile else v
                findings += [{"at": f"{path}.{k}".lstrip("."), "kind": f.kind, "text": f.text} for f in g.findings]
            else:
                out[k], found = screen(v, f"{path}.{k}")
                findings += found
        return out, findings
    if isinstance(obj, list):
        out_list = []
        for n, v in enumerate(obj):
            item, found = screen(v, f"{path}[{n}]")
            out_list.append(item)
            findings += found
        return out_list, findings
    return obj, findings
