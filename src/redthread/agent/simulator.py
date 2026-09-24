"""Simulated replies to evidence requests (the dataset provides none; README policy section 5).

The assumption is explicit and reproducible: the reply is the one most consistent with the evidence
gathered *before* asking — a customer denies activity the evidence says is fraud, and recognises
activity the evidence says is theirs.

**A reply inferred from the prior cannot then be used to update the prior.** That is circular, and it
was doing real damage: a case weighed at 0.65 produced a denial, the denial was scored at eight to
one, and the case came out at 0.94. Every mid-range case was slammed to a confident verdict in the
direction it already leaned, which erased the `uncertain` verdicts the policy depends on and, on a
59-case backtest, was wrong ten times out of thirteen. Removing the update moved verdict accuracy
from 0.593 to 0.661 and cut cleared customers wrongly accused of fraud from 17 to 11.

So the reply moves the probability only when it carries information the prior did not already
determine. One case qualifies: a charge matching the holder's own recurring pattern is read out of
the holder's history, not out of the belief, so it is genuine exculpatory evidence. Everything else
supplies narrative and drives the policy paths (R4 no reply, R7 recurring, step-up failure) while
leaving belief where the evidence left it.
"""

from dataclasses import dataclass

from redthread.policy import Response

# A recurring-charge match comes from the holder's transaction history, so it is evidence:
# P(reply | fraud) / P(reply | legitimate). Everything else is inferred from the prior and is worth
# exactly nothing as an update.
RECURRING_MATCH_LR = 1 / 8.0
NO_INFORMATION = 1.0


@dataclass(frozen=True)
class SimulatedReply:
    response: Response
    text: str
    prior: float
    posterior: float
    #: False when the reply was inferred from the evidence and so cannot move belief.
    informative: bool = False


def bayes(prior: float, likelihood_ratio: float) -> float:
    prior = min(max(prior, 0.001), 0.999)
    odds = prior / (1 - prior) * likelihood_ratio
    return round(odds / (1 + odds), 3)


def simulate(request_type: str, prior: float, *, recurring: bool, customer_reported: bool) -> SimulatedReply:
    denies = prior >= 0.5 and not recurring
    response: Response = "denied" if denies else "confirmed"
    if request_type == "analyst_info":
        text = ("The fraud analyst checked the bank's own records for anything contradicting the "
                "cardholder's dispute - a prior verification of this device, a contact-centre call "
                "authorising the purchase - and found none" if denies else
                "The fraud analyst found a record consistent with the cardholder's own activity, such as "
                "this device previously verified on the account")
    elif request_type == "step_up_auth":
        text = ("Step-up authentication was not completed: the one-time passcode sent to the cardholder's "
                "registered phone was never entered, and the cardholder, contacted, did not recognise the activity"
                if denies else "The cardholder completed step-up authentication on their registered device "
                               "and approved the activity")
    elif recurring:
        text = ("The customer recognised the charge as their own recurring payment"
                + (" and withdrew the dispute" if customer_reported else ""))
    elif customer_reported:
        text = ("Customer confirmed on follow-up that they did not make the transaction and still hold the card"
                if denies else "On follow-up the customer recognised the transaction (made by them or an "
                               "authorised household member) and withdrew the dispute")
    else:
        text = ("Customer stated they did not make the transaction and still have the card" if denies
                else "Customer confirmed they made the transaction")

    if recurring:
        note = ("Assumed reply. The recurring match comes from the holder's own history, so it counts as "
                "evidence.")
        return SimulatedReply(response, f"{text}. ({note})", prior,
                              bayes(prior, RECURRING_MATCH_LR), informative=True)
    note = (f"Assumed: the reply most consistent with the evidence before asking, probability {prior:.2f}. "
            f"Because it was inferred from that evidence, it does not move the probability.")
    return SimulatedReply(response, f"{text}. ({note})", prior, bayes(prior, NO_INFORMATION),
                          informative=False)
