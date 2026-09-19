"""What the LLM must return when it assesses a case (a JSON schema enforced by Gemini)."""

from typing import Literal

from pydantic import BaseModel, Field

from redthread.answer import Pattern


class LlmEvidence(BaseModel):
    claim: str = Field(description="One factual finding, with numbers and dates where relevant")
    source: Literal["graph", "document", "customer", "external"]
    ref: str = Field(description="The exact 'ref' string of the tool result this claim rests on")
    entity_ids: list[str] = Field(description="IDs from tool results: transactions, cards, devices, cases")


class LlmSignals(BaseModel):
    single_signal: bool = Field(description="R1: the case rests on one signal only (e.g. a score or a complaint)")
    card_testing: bool = Field(description="R5 sequence observed: >=3 small online auths within 1h, then larger")
    card_testing_purchase_cleared_over_100: bool
    recurring_match: bool = Field(description="R7: disputed charge matches the holder's own recurring pattern")
    shared_origin: bool = Field(description="R6: several cards show fraud from the same device/region/email")
    shared_element: str = Field(description="The shared device profile / region / email, or ''")
    linked_to_other_fraud: bool = Field(description="Connects to a shared device profile or another card's fraud")
    coordinated_undocumented: bool = Field(description="R9: coordinated abuse across customers, no known pattern")
    evidence_conflicts: bool = Field(description="R8: strong evidence points in opposite directions")
    customer_cards_confirmed_fraud: int = Field(
        description="R10: how many of the customer's cards show fraud IN THIS EPISODE (not historical cases)")
    credentials_compromised: bool = Field(description="R10: login credentials confirmed stolen (account takeover)")


class LlmAssessment(BaseModel):
    reasoning: str = Field(description="Your analysis: what each piece of evidence shows and how it combines")
    verdict: Literal["fraud", "legitimate", "uncertain"]
    fraud_probability: float = Field(ge=0, le=1, description="Calibrated probability the flagged activity is fraud")
    pattern: Pattern
    pattern_description: str = Field(description="2-3 sentences if pattern is 'undocumented', else ''")
    affected_txn_ids: list[str] = Field(description="Every transaction in the fraud episode incl. the flagged one")
    first_suspicious_txn_id: str
    connected_card_ids: list[str] = Field(description="Other cards caught in the same compromise, ring or device")
    connected_device_ids: list[str] = Field(description="Device IDs (D...) linking this case to other cards")
    similar_prior_cases: list[str] = Field(description="Closed-case IDs (CC-...) that informed the assessment")
    evidence: list[LlmEvidence]
    independent_evidence: int = Field(description="Number of independent evidence lines supporting the verdict")
    signals: LlmSignals
    uncertainty: str = Field(description="What remains uncertain and what evidence would resolve it")


class LlmReport(BaseModel):
    summary: str = Field(description="2-6 sentences an analyst could read")
    what_changed: str = Field(description="1-2 sentences on why final actions differ from initial, or 'nothing'")
    stop_reason: str = Field(description="Why the investigation ended here, citing policy section 6")
    sar_narrative: str = Field(description="6-12 sentence SAR narrative if a report is filed, else ''")


def json_schema(model: type[BaseModel]) -> dict:
    return model.model_json_schema()
