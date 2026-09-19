"""Fraud Policy v1.0 as code (see data/README.md, "Fraud Policy").

The agent's LLM produces an ``Assessment`` (what the evidence says). This module turns it into the
actions, approval routes, evidence requests, SAR decision and stop decision the policy requires.
Nothing here calls an LLM: every identifier and route is deterministic and unit-tested.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

Verdict = Literal["fraud", "legitimate", "uncertain"]
Response = Literal["denied", "confirmed", "no_reply"]
RequestType = Literal["customer_validation", "step_up_auth", "analyst_info"]


class Action(StrEnum):
    ALLOW_TRANSACTION = "ALLOW_TRANSACTION"
    DECLINE_TRANSACTION = "DECLINE_TRANSACTION"
    MONITOR_CARD = "MONITOR_CARD"
    MONITOR_CONNECTED_CARDS = "MONITOR_CONNECTED_CARDS"
    WARN_CUSTOMER = "WARN_CUSTOMER"
    VERIFY_WITH_CUSTOMER = "VERIFY_WITH_CUSTOMER"
    STEP_UP_AUTH = "STEP_UP_AUTH"
    BLOCK_CARD = "BLOCK_CARD"
    BLOCK_ALL_CARDS = "BLOCK_ALL_CARDS"
    GENERATE_REPORT = "GENERATE_REPORT"
    CREATE_CASE = "CREATE_CASE"
    FILE_REPORT = "FILE_REPORT"
    ESCALATE_TO_ANALYST = "ESCALATE_TO_ANALYST"
    CLOSE_NO_FRAUD = "CLOSE_NO_FRAUD"


AUTO_ACTIONS = frozenset({
    Action.ALLOW_TRANSACTION, Action.MONITOR_CARD, Action.MONITOR_CONNECTED_CARDS, Action.WARN_CUSTOMER,
    Action.VERIFY_WITH_CUSTOMER, Action.STEP_UP_AUTH, Action.GENERATE_REPORT, Action.CREATE_CASE,
    Action.ESCALATE_TO_ANALYST, Action.CLOSE_NO_FRAUD,
})
BLOCK_CARD_L2_THRESHOLD = 2_500.0

# Policy section 1: "Order them by what happens first." Containment, then customer contact,
# then record-keeping, then filing, then protection of other cards, then hand-off / closure.
_ORDER = [
    Action.DECLINE_TRANSACTION, Action.BLOCK_CARD, Action.BLOCK_ALL_CARDS, Action.STEP_UP_AUTH,
    Action.VERIFY_WITH_CUSTOMER, Action.ALLOW_TRANSACTION, Action.MONITOR_CARD, Action.WARN_CUSTOMER,
    Action.CREATE_CASE, Action.GENERATE_REPORT, Action.FILE_REPORT, Action.MONITOR_CONNECTED_CARDS,
    Action.ESCALATE_TO_ANALYST, Action.CLOSE_NO_FRAUD,
]

STOP_HIGH, STOP_LOW = 0.85, 0.15
R1_THRESHOLD = 0.70
CASE_THRESHOLD = 0.30
SAR_EXPOSURE, ESCALATE_EXPOSURE = 1_000.0, 500.0


def route_for(action: Action, exposure_usd: float) -> str:
    """Approval route from policy section 2."""
    if action in AUTO_ACTIONS:
        return "auto"
    if action == Action.DECLINE_TRANSACTION:
        return "L1"
    if action == Action.BLOCK_CARD:
        return "L1" if exposure_usd <= BLOCK_CARD_L2_THRESHOLD else "L2"
    return "L2"  # BLOCK_ALL_CARDS, FILE_REPORT


@dataclass(frozen=True)
class Assessment:
    """What the investigation concluded, in the terms the policy rules test."""

    verdict: Verdict
    probability: float
    pattern: str
    exposure_usd: float
    independent_evidence: int  # count of independent supporting signals (policy section 6)
    customer_disputed: bool = False  # trigger was a customer saying they did not make it
    single_signal: bool = False  # R1: rests on one signal, e.g. the risk score alone
    card_testing: bool = False  # R5 sequence observed
    card_testing_purchase_cleared_over_100: bool = False
    recurring_match: bool = False  # R7: matches the holder's own recurring charge
    shared_origin: bool = False  # R6: several cards with fraud share a device/region/recipient email
    shared_element: str = ""  # the device profile / region / email named under R6
    linked_to_other_fraud: bool = False  # connects to a shared device profile or another card's fraud
    coordinated_undocumented: bool = False  # R9
    connected_cards: tuple[str, ...] = ()
    evidence_conflicts: bool = False  # R8
    customer_cards_confirmed_fraud: int = 0  # R10
    credentials_compromised: bool = False  # R10
    online: bool = True


@dataclass
class Recommendation:
    action: Action
    route: str
    reason: str


@dataclass
class _Plan:
    exposure: float
    reasons: dict[Action, list[str]] = field(default_factory=dict)

    def add(self, action: Action, reason: str) -> None:
        self.reasons.setdefault(action, [])
        if reason not in self.reasons[action]:
            self.reasons[action].append(reason)

    def drop(self, action: Action) -> None:
        self.reasons.pop(action, None)

    def build(self) -> list[Recommendation]:
        ordered = sorted(self.reasons, key=_ORDER.index)
        return [Recommendation(a, route_for(a, self.exposure), "; ".join(self.reasons[a])) for a in ordered]


def sar_required(a: Assessment, response: Response | None = None) -> tuple[bool, str]:
    """Policy 3a: confirmed or strongly suspected fraud AND one of the aggravating conditions."""
    denied = response == "denied" or (a.customer_disputed and response is None and a.verdict == "fraud")
    suspected = a.verdict == "fraud" or a.probability >= STOP_HIGH or denied
    if response == "confirmed" or not suspected:
        return False, "3a: fraud is not confirmed or strongly suspected, so no report is required"
    if a.coordinated_undocumented:
        return True, "3a and R9: coordinated activity that fits no documented pattern"
    if a.shared_origin:
        return True, f"3a and R6: fraud across several cards sharing {a.shared_element or 'a common origin'}"
    if a.linked_to_other_fraud:
        return True, "3a and R2: activity connects to a shared device profile or another card's fraud"
    if a.exposure_usd > SAR_EXPOSURE:
        return True, f"3a: exposure ${a.exposure_usd:,.2f} exceeds $1,000"
    return False, (f"3a: fraud suspected but exposure ${a.exposure_usd:,.2f} is at most $1,000 and there is "
                   "no shared device, region cluster or link to other customers' fraud; case only")


def evidence_request(a: Assessment) -> RequestType | None:
    """Which controlled evidence request the policy calls for before deciding, if any."""
    if can_stop(a):
        return None
    if a.recurring_match:
        return "customer_validation"  # R7
    if a.coordinated_undocumented or a.shared_origin:
        return None  # R6/R9 prescribe actions directly; the ring evidence does not hinge on one customer
    if a.card_testing:
        return "step_up_auth"  # R5
    return "customer_validation"  # R1 / 3b


def can_stop(a: Assessment) -> bool:
    """Policy section 6: decisive probability backed by at least two independent pieces of evidence."""
    decisive = a.probability >= STOP_HIGH or a.probability <= STOP_LOW
    return decisive and a.independent_evidence >= 2 and not a.recurring_match


def recommend(a: Assessment, response: Response | None = None) -> list[Recommendation]:
    """Actions for the current state of the case.

    ``response`` is None before any requested evidence comes back (``initial``), otherwise the
    assumed reply (``final``).
    """
    plan = _Plan(a.exposure_usd)
    if response is not None:
        _after_response(plan, a, response)
    else:
        _before_response(plan, a)
    _ring_actions(plan, a, response)
    _escalation(plan, a, response)
    _block_all_guard(plan, a)
    return plan.build()


def _before_response(plan: _Plan, a: Assessment) -> None:
    request = evidence_request(a)
    if a.recurring_match and a.customer_disputed:
        plan.add(Action.CREATE_CASE, "R7: customer disputes a charge matching their own recurring pattern")
        plan.add(Action.VERIFY_WITH_CUSTOMER, "R7: confirm the recurring charge with the cardholder; do not block")
        plan.add(Action.WARN_CUSTOMER, "R7: remind the cardholder of the recurring charge")
        return
    if a.card_testing:
        plan.add(Action.DECLINE_TRANSACTION, "R5: card-testing sequence; decline pending authorizations")
        plan.add(Action.STEP_UP_AUTH, "R5: require step-up authentication before further activity")
        if a.card_testing_purchase_cleared_over_100:
            plan.add(Action.BLOCK_CARD, "R5: a purchase over $100 has already cleared after the test sequence")
        plan.add(Action.CREATE_CASE, "3a: fraud probability at or above 0.30")
        return
    if can_stop(a) and a.probability <= STOP_LOW:
        if a.customer_disputed:
            plan.add(Action.CREATE_CASE, "3a: a case is opened whenever a customer disputes a charge")
        plan.add(Action.CLOSE_NO_FRAUD, f"Section 6: probability {a.probability:.2f} <= 0.15 on "
                                        f"{a.independent_evidence} independent signals")
        return
    if can_stop(a) and a.probability >= STOP_HIGH:
        if a.customer_disputed:
            _denied(plan, a, "R2: customer states they did not make the transaction")
        else:
            plan.add(Action.BLOCK_CARD, f"Section 6: probability {a.probability:.2f} >= 0.85 on "
                                        f"{a.independent_evidence} independent signals")
            plan.add(Action.CREATE_CASE, "3a: fraud probability at or above 0.30")
        return
    if a.coordinated_undocumented or a.shared_origin:
        plan.add(Action.CREATE_CASE, "3a: fraud probability at or above 0.30")
        return
    if a.customer_disputed and a.probability >= R1_THRESHOLD and not a.single_signal:
        _denied(plan, a, "R2: customer states they did not make the transaction")
        return
    # R1 / 3b: not enough to act on; ask first.
    if request == "step_up_auth" or (a.online and not a.customer_disputed and a.probability < CASE_THRESHOLD):
        plan.add(Action.STEP_UP_AUTH, f"R1: probability {a.probability:.2f} below 0.70 on the available "
                                      "signals; verify before any block")
    else:
        plan.add(Action.VERIFY_WITH_CUSTOMER, f"R1: probability {a.probability:.2f} below 0.70 on the "
                                              "available signals; verify before any block")
    plan.add(Action.CREATE_CASE, "3a: a case is opened whenever evidence is requested"
             + (" or a customer disputes a charge" if a.customer_disputed else ""))


def _after_response(plan: _Plan, a: Assessment, response: Response) -> None:
    if response == "confirmed":
        if a.recurring_match:
            plan.add(Action.WARN_CUSTOMER, "R7: recurring-charge reminder sent")
        plan.add(Action.CLOSE_NO_FRAUD, "R3: cardholder confirmed the transaction; confirmation noted in the case")
        return
    if response == "denied":
        _denied(plan, a, "R2: cardholder denied the transaction")
        return
    plan.add(Action.MONITOR_CARD, "R4: no reply within 24 hours")
    plan.add(Action.DECLINE_TRANSACTION, "R4: decline pending authorizations while unverified")
    plan.add(Action.CREATE_CASE, "3a: evidence was requested")
    if a.exposure_usd > ESCALATE_EXPOSURE:
        plan.add(Action.ESCALATE_TO_ANALYST, f"R4: no reply and exposure ${a.exposure_usd:,.2f} exceeds $500")


def _denied(plan: _Plan, a: Assessment, why: str) -> None:
    plan.add(Action.BLOCK_CARD, f"{why}; exposure ${a.exposure_usd:,.2f}")
    plan.add(Action.CREATE_CASE, "R2")
    file, reason = sar_required(a, "denied")
    if file:
        plan.add(Action.FILE_REPORT, reason)


def _ring_actions(plan: _Plan, a: Assessment, response: Response | None) -> None:
    if response == "confirmed":
        return
    if a.coordinated_undocumented:
        plan.add(Action.CREATE_CASE, "R9: coordinated abuse across customers fitting no known pattern")
        plan.add(Action.FILE_REPORT, "R9")
        plan.add(Action.ESCALATE_TO_ANALYST, "R9")
    if a.shared_origin:
        element = a.shared_element or "a common origin"
        plan.add(Action.CREATE_CASE, f"R6: several cards show fraud from {element}")
        plan.add(Action.FILE_REPORT, f"R6: shared origin {element}")
    if a.connected_cards and (a.shared_origin or a.coordinated_undocumented or a.linked_to_other_fraud):
        plan.add(Action.MONITOR_CONNECTED_CARDS,
                 f"R6: {len(a.connected_cards)} connected card(s) share the same origin")


def _escalation(plan: _Plan, a: Assessment, response: Response | None) -> None:
    if response == "confirmed":
        return
    uncertain_and_exposed = a.verdict == "uncertain" and a.exposure_usd > ESCALATE_EXPOSURE
    if uncertain_and_exposed or a.evidence_conflicts:
        if a.evidence_conflicts:
            why = "evidence conflicts"
        else:
            why = f"verdict uncertain and exposure ${a.exposure_usd:,.2f} > $500"
        plan.add(Action.ESCALATE_TO_ANALYST, f"R8: {why}")


def _block_all_guard(plan: _Plan, a: Assessment) -> None:
    """R10: BLOCK_ALL_CARDS only with two confirmed-fraud cards or confirmed credential compromise."""
    allowed = a.customer_cards_confirmed_fraud >= 2 or a.credentials_compromised
    if not allowed:
        plan.drop(Action.BLOCK_ALL_CARDS)
    elif Action.BLOCK_CARD in plan.reasons:
        plan.drop(Action.BLOCK_CARD)
        plan.add(Action.BLOCK_ALL_CARDS, "R10: at least two of the customer's cards show confirmed fraud "
                                          "or credentials are confirmed compromised")
