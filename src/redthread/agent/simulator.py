"""Simulated replies to evidence requests (the dataset provides none; README policy section 5).

The assumption is explicit and reproducible: the reply is the one most consistent with the
evidence gathered *before* asking (a customer denies activity the evidence says is fraud, and
recognises activity the evidence says is theirs). The probability is then updated with Bayes' rule
using a likelihood ratio for the reply, so the size of the update is stated, not improvised.
"""

from dataclasses import dataclass

from redthread.policy import Response

# P(reply | fraud) / P(reply | legitimate). Cardholders usually deny fraud and recognise their own
# purchases, but some forget purchases (false denials) and some fraud goes unnoticed.
LIKELIHOOD_RATIO = {"denied": 8.0, "confirmed": 1 / 8.0}


@dataclass(frozen=True)
class SimulatedReply:
    response: Response
    text: str
    prior: float
    posterior: float


def bayes(prior: float, likelihood_ratio: float) -> float:
    prior = min(max(prior, 0.001), 0.999)
    odds = prior / (1 - prior) * likelihood_ratio
    return round(odds / (1 + odds), 3)


def simulate(request_type: str, prior: float, *, recurring: bool, customer_reported: bool) -> SimulatedReply:
    denies = prior >= 0.5 and not recurring
    response: Response = "denied" if denies else "confirmed"
    if request_type == "step_up_auth":
        text = ("Step-up authentication was not completed: the one-time passcode sent to the cardholder's "
                "registered phone was never entered, and the cardholder, contacted, did not recognise the activity"
                if denies else "The cardholder completed step-up authentication on their registered device "
                               "and approved the activity")
    elif recurring:
        text = ("On review the customer recognised the charge as their own recurring payment and withdrew the "
                "dispute")
    elif customer_reported:
        text = ("Customer confirmed on follow-up that they did not make the transaction and still hold the card"
                if denies else "On follow-up the customer recognised the transaction (made by them or an "
                               "authorised household member) and withdrew the dispute")
    else:
        text = ("Customer stated they did not make the transaction and still have the card" if denies
                else "Customer confirmed they made the transaction")
    posterior = bayes(prior, LIKELIHOOD_RATIO[response])
    return SimulatedReply(response, f"{text}. (Assumed: the reply most consistent with the evidence before "
                                    f"asking, probability {prior:.2f}.)", prior, posterior)
