"""Turn judged evidence into a calibrated fraud probability.

The investigator used to return a probability directly, and it returned near-certainty every time:
across 20 benchmark cases nothing landed between 0.11 and 0.88. That silently disabled half the
policy — `can_stop()` was always true, so the agent never asked for evidence, never recorded an
`uncertain` verdict, and never changed a recommendation.

Here the model judges each piece of evidence (which way it points, how strong it is, and what it
rests on) and this module does the arithmetic:

    posterior odds = prior odds x product of likelihood ratios

Two rules keep it honest:

1. **One voice per basis.** Evidence resting on the same underlying fact (the device, the holder's
   behaviour, the customer's statement...) is grouped, and only the strongest item in each group is
   counted. Five restatements of one device fact are one piece of evidence, not five, which is what
   "independent evidence" in policy section 6 actually means.
2. **The prior is measured, not assumed.** For a model-triggered alert it is the flagged
   transaction's calibrated fraud rate from the closed cases (`model.calibration`); for a customer
   report it is the rate at which disputes turn out to be fraud, tempered because R7 disputes exist.

Every number is reproducible from the ledger, so the dashboard can show why a case sits at 0.62 and
what happens to the recommendation if one line is struck out.
"""

from dataclasses import dataclass
from typing import Literal

from redthread.model.calibration import fraud_rate

Direction = Literal["incriminating", "exculpatory"]
Strength = Literal["weak", "moderate", "strong", "decisive"]

# What a piece of evidence of each strength multiplies the odds by. Deliberately coarse: a model
# asked for "how strong is this" answers reliably, while one asked for "give me a likelihood ratio"
# invents precision it does not have.
STRENGTH_LR: dict[str, float] = {"weak": 1.5, "moderate": 3.0, "strong": 8.0, "decisive": 20.0}

# Independence groups. Evidence in the same group rests on the same underlying fact.
BASES: tuple[str, ...] = (
    "flagged_transaction_model",  # the fraud model's score for the flagged transaction
    "holder_behaviour",           # fits or breaks the resolved account holder's pattern
    "device",                     # the device used: new to the account, proxied, shared, specific
    "cross_card_links",           # other cards caught by the same device/region/email in the window
    "prior_cases",                # closed cases or the agent's own earlier cases
    "customer_statement",         # what the cardholder said
    "amount_or_timing",           # amounts, velocity, recurring cadence, testing sequences
    "region",                     # billing region against the card's home region
)

PRIOR_CUSTOMER_REPORT = 0.6  # a denial is strong evidence, but R7 disputes are real
PRIOR_ANALYST_REQUEST = 0.5
PRIOR_BOUNDS = (0.05, 0.90)  # never start an investigation certain of its own conclusion
P_FLOOR = 0.03  # calibration is scored; claiming 0 or 1 is never supported by evidence this noisy
MODEL_BASIS_LR_CAP = 8.0  # when the model score is evidence rather than the prior


@dataclass(frozen=True)
class Judged:
    """One piece of evidence as the investigator judged it."""

    basis: str
    direction: Direction
    strength: Strength
    claim: str = ""

    @property
    def likelihood_ratio(self) -> float:
        lr = STRENGTH_LR[self.strength]
        return lr if self.direction == "incriminating" else 1 / lr


@dataclass(frozen=True)
class Weighed(Judged):
    """A judged item with its effect on the odds, and whether it counted."""

    counted: bool = True
    lr_applied: float = 1.0


@dataclass(frozen=True)
class Belief:
    prior: float
    prior_reason: str
    posterior: float
    independent_evidence: int
    ledger: tuple[Weighed, ...]

    @property
    def verdict(self) -> str:
        if self.posterior >= 0.85:
            return "fraud"
        return "legitimate" if self.posterior <= 0.15 else "uncertain"

    def explain(self) -> str:
        parts = [f"prior {self.prior:.2f} ({self.prior_reason})"]
        for item in self.ledger:
            if item.counted:
                arrow = "up" if item.lr_applied > 1 else "down"
                parts.append(f"{item.basis} {item.strength} {arrow} (x{item.lr_applied:.2g})")
        return f"{'; '.join(parts)} -> {self.posterior:.2f}"


def prior_for(trigger_type: str, model_score: float | None) -> tuple[float, str]:
    """Where the investigation starts, before any graph evidence."""
    if trigger_type == "customer_report":
        return PRIOR_CUSTOMER_REPORT, "a cardholder disputing a charge"
    if trigger_type == "analyst_request":
        return PRIOR_ANALYST_REQUEST, "an analyst asking for a review"
    rate = fraud_rate(model_score) if model_score is not None else None
    if rate is None:
        return PRIOR_ANALYST_REQUEST, "no model score available"
    low, high = PRIOR_BOUNDS
    return min(max(rate, low), high), f"the calibrated fraud rate for a model score of {model_score:.3f}"


def weigh(items: list[Judged], *, model_is_prior: bool) -> list[Weighed]:
    """Mark the strongest item in each basis as counted; everything else is corroboration.

    When the model score has already set the prior, items resting on it are never counted again.
    """
    ranked = sorted(range(len(items)), key=lambda i: abs(_log_lr(items[i])), reverse=True)
    counted_bases: set[str] = set()
    decisions: dict[int, tuple[bool, float]] = {}
    for i in ranked:
        item = items[i]
        basis = item.basis if item.basis in BASES else "amount_or_timing"
        double_counts_prior = model_is_prior and basis == "flagged_transaction_model"
        if basis in counted_bases or double_counts_prior:
            decisions[i] = (False, 1.0)
            continue
        counted_bases.add(basis)
        lr = item.likelihood_ratio
        if basis == "flagged_transaction_model":
            lr = min(max(lr, 1 / MODEL_BASIS_LR_CAP), MODEL_BASIS_LR_CAP)
        decisions[i] = (True, lr)
    return [Weighed(basis=item.basis, direction=item.direction, strength=item.strength, claim=item.claim,
                    counted=decisions[i][0], lr_applied=decisions[i][1]) for i, item in enumerate(items)]


def assess(trigger_type: str, model_score: float | None, items: list[Judged]) -> Belief:
    """Prior from the trigger, likelihood ratios from the evidence, posterior by Bayes."""
    prior, reason = prior_for(trigger_type, model_score)
    model_is_prior = trigger_type != "customer_report" and model_score is not None
    ledger = weigh(items, model_is_prior=model_is_prior)
    odds = prior / (1 - prior)
    for item in ledger:
        odds *= item.lr_applied
    posterior = min(max(odds / (1 + odds), P_FLOOR), 1 - P_FLOOR)
    return Belief(prior=round(prior, 3), prior_reason=reason, posterior=round(posterior, 3),
                  independent_evidence=sum(1 for i in ledger if i.counted), ledger=tuple(ledger))


def without(belief: Belief, dropped: set[int], trigger_type: str, model_score: float | None) -> Belief:
    """Recompute with some ledger lines struck out: the counterfactual the dashboard offers."""
    kept = [Judged(basis=i.basis, direction=i.direction, strength=i.strength, claim=i.claim)
            for n, i in enumerate(belief.ledger) if n not in dropped]
    return assess(trigger_type, model_score, kept)


def _log_lr(item: Judged) -> float:
    from math import log

    return log(item.likelihood_ratio)
