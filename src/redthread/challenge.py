"""When a person disagrees with the agent, the disagreement has to be evidenced.

An analyst who says "this is not fraud" may be right: they may know something the graph does not. They
may also be wrong, careless, or an insider clearing a case on purpose. A bank cannot let one person's
word silently overturn an evidenced decision, and it cannot let that word become the memory later
investigations learn from. So a challenge is treated as one more piece of evidence, held to the same
standard as every other:

1. The reason is screened like any free text that reaches the agent (redthread.agent.guard): a reason
   that tries to instruct the system is refused.
2. The IDs it cites must exist in this case's record (its transactions, cards, customer, connected
   cards, the entities its evidence rests on). A claim citing nothing from the case is unsupported.
3. The claim enters the case's own evidence ledger as an ``analyst_statement`` finding: weak when
   unsupported, moderate when it rests on the case's records, never stronger. A person's say-so can
   tip a close call; it cannot on its own outweigh the measured record. A genuinely new fact (the
   customer phoned in) belongs in an evidence request, which the policy already weighs.
4. The probability is recomputed with the same arithmetic (redthread.belief.assess). If the evidence
   now agrees with the claim, the challenge is accepted. If it still points the other way, or no
   longer decides either way, the challenge is contested and waits for a second, different L2
   approver: the four-eyes rule.

Only accepted or upheld challenges become memory. Every step is recorded with who, what, the IDs, the
probability before and after, and why.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from redthread.agent.guard import guard
from redthread.belief import STOP_HIGH_POSTERIOR, STOP_LOW_POSTERIOR, Judged, assess

Position = Literal["fraud", "legitimate"]
ID = re.compile(r"^(\d{7}|C\d{5}-K\d|C\d{5}|CC-\d{4}|D\d{6})$")


@dataclass
class Evaluation:
    status: Literal["accepted", "contested", "refused"]
    why: str
    position: Position
    probability_before: float | None = None
    probability_after: float | None = None
    verdict_before: str = ""
    verdict_after: str = ""
    strength: str = ""
    ids_in_case: list[str] = field(default_factory=list)
    ids_not_in_case: list[str] = field(default_factory=list)
    quarantined: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def case_scope(answer: dict, trace: dict) -> set[str]:
    """Every ID this case's record rests on: what a challenge may cite."""
    c, alert = answer["case"], trace.get("alert", {})
    ids = {*c["affected_txn_ids"], *c["connected_card_ids"], *c.get("connected_device_profiles", []),
           *c["similar_prior_cases"], alert.get("card_id"), alert.get("customer_id"),
           str(alert.get("flagged_txn_id", ""))}
    for e in c["evidence"]:
        ids.update(e["entity_ids"])
    for line in (trace.get("belief") or {}).get("ledger", []):
        ids.update(line.get("entities") or [])
    return {str(i) for i in ids if i}


def _verdict(p: float) -> str:
    return "fraud" if p >= STOP_HIGH_POSTERIOR else "legitimate" if p <= STOP_LOW_POSTERIOR else "uncertain"


def evaluate(position: Position, reason: str, evidence_ids: list[str], answer: dict, trace: dict) -> Evaluation:
    screened = guard(reason)
    if screened.hostile:
        return Evaluation("refused", "the reason addresses the system rather than the case; restate it as "
                          "facts about the case", position, quarantined=[f.text for f in screened.findings])
    if len(screened.text.split()) < 5:
        return Evaluation("refused", "a challenge needs a reason an analyst could check: at least a sentence",
                          position)
    belief, alert = trace.get("belief") or {}, trace.get("alert") or {}
    if not belief.get("ledger"):
        return Evaluation("refused", "this case has no evidence ledger to weigh a challenge against", position)
    scope = case_scope(answer, trace)
    cited = [str(i).strip() for i in evidence_ids if str(i).strip()]
    in_case = [i for i in cited if ID.match(i) and i in scope]
    not_in_case = [i for i in cited if i not in in_case]
    strength = "moderate" if in_case else "weak"
    kept = [Judged(basis=i["basis"], direction=i["direction"], strength=i["strength"], claim=i["claim"],
                   entities=tuple(i.get("entities") or ())) for i in belief["ledger"]]
    statement = Judged(basis="analyst_statement",
                       direction="incriminating" if position == "fraud" else "exculpatory",
                       strength=strength, claim=screened.text, entities=tuple(in_case))
    flagged = (trace.get("evidence") or {}).get("alert_context", {}).get("flagged_txn", {})
    subject = frozenset(belief.get("subject") or ())
    as_of = belief.get("as_of") or alert.get("opened_at")
    before = assess(alert.get("trigger_type", "analyst_request"), flagged.get("model_score"), kept, subject, as_of)
    after = assess(alert.get("trigger_type", "analyst_request"), flagged.get("model_score"), [*kept, statement],
                   subject, as_of)
    agrees = _verdict(after.posterior) == position
    if agrees:
        why = (f"with the analyst's {strength} statement added, the evidence now supports '{position}' "
               f"({before.posterior:.2f} to {after.posterior:.2f})")
    else:
        why = (f"with the analyst's {strength} statement added, the evidence reads "
               f"'{_verdict(after.posterior)}' ({before.posterior:.2f} to {after.posterior:.2f}), not '{position}'"
               + ("; no cited ID belongs to this case" if not in_case else "")
               + ". A second, different L2 approver must uphold or overrule it")
    return Evaluation("accepted" if agrees else "contested", why, position, round(before.posterior, 3),
                      round(after.posterior, 3), _verdict(before.posterior), _verdict(after.posterior), strength,
                      in_case, not_in_case)
