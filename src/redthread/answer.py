"""The answer file format from data/README.md ("Answer Format"), as a validated model.

Structural and cross-field rules live here. Checks that need the dataset (IDs exist, exposure equals
the sum of amounts) live in ``redthread.validate``.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from redthread.policy import Action, route_for

Pattern = Literal[
    "card_testing", "card_not_present_fraud", "card_not_present_new_device", "out_of_region_use",
    "account_takeover", "undocumented", "none",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(_Strict):
    claim: str = Field(min_length=1)
    source: Literal["graph", "document", "customer", "external"]
    ref: str = Field(min_length=1)
    entity_ids: list[str]


class Case(_Strict):
    status: Literal["open", "closed_fraud", "closed_legitimate", "escalated"]
    verdict: Literal["fraud", "legitimate", "uncertain"]
    fraud_probability: float = Field(ge=0, le=1)
    pattern: Pattern
    pattern_description: str
    affected_txn_ids: list[str]
    first_suspicious_txn_id: str
    connected_card_ids: list[str]
    connected_device_profiles: list[str]
    exposure_usd: float = Field(ge=0)
    evidence: list[Evidence] = Field(min_length=1)
    similar_prior_cases: list[str]
    summary: str = Field(min_length=1)
    written_to_graph: bool
    graph_case_id: str

    @model_validator(mode="after")
    def _consistent(self) -> "Case":
        if (self.pattern == "undocumented") != bool(self.pattern_description.strip()):
            raise ValueError("pattern_description is required for 'undocumented' and must be '' otherwise")
        if self.verdict == "legitimate" and (self.affected_txn_ids or self.exposure_usd):
            raise ValueError("a legitimate verdict has no affected transactions and zero exposure")
        if self.first_suspicious_txn_id and self.first_suspicious_txn_id not in self.affected_txn_ids:
            raise ValueError("first_suspicious_txn_id must be one of affected_txn_ids")
        if self.written_to_graph != bool(self.graph_case_id):
            raise ValueError("graph_case_id is set exactly when written_to_graph is true")
        return self


class EvidenceRequest(_Strict):
    type: Literal["customer_validation", "step_up_auth", "analyst_info"]
    asked_after_step: int = Field(ge=0)
    assumed_response: str = Field(min_length=1)


class ActionItem(_Strict):
    action: Action
    route: Literal["auto", "L1", "L2"]
    reason: str = Field(min_length=1)


class NextBestActions(_Strict):
    initial: list[ActionItem] = Field(min_length=1)
    final: list[ActionItem] = Field(min_length=1)
    what_changed: str = Field(min_length=1)


class Sar(_Strict):
    file: bool
    reason: str = Field(min_length=1)
    narrative: str
    subjects: list[str]
    total_amount_usd: float = Field(ge=0)
    activity_dates: list[str]

    @model_validator(mode="after")
    def _filled_iff_filed(self) -> "Sar":
        if self.file:
            if not self.narrative.strip() or not self.subjects or len(self.activity_dates) != 2:
                raise ValueError("a filed SAR needs a narrative, subjects and two activity dates")
        elif self.narrative or self.subjects or self.total_amount_usd or self.activity_dates:
            raise ValueError("an unfiled SAR has empty narrative/subjects/dates and zero amount")
        return self


class Answer(_Strict):
    case_id: str
    case: Case
    evidence_requests: list[EvidenceRequest]
    next_best_actions: NextBestActions
    sar: Sar
    stop_reason: str = Field(min_length=1)
    tool_calls: int = Field(ge=0)
    tokens: int = Field(ge=0)
    latency_s: float = Field(ge=0)

    @model_validator(mode="after")
    def _policy_consistent(self) -> "Answer":
        nba = self.next_best_actions
        exposure = self.case.exposure_usd
        for item in nba.initial + nba.final:
            expected = route_for(item.action, exposure)
            if item.route != expected:
                raise ValueError(f"{item.action} must route {expected} at exposure ${exposure:,.2f}")
        filed = any(i.action == Action.FILE_REPORT for i in nba.final)
        if filed != self.sar.file:
            raise ValueError("sar.file must agree with FILE_REPORT in next_best_actions.final")
        if not self.evidence_requests:
            if [i.model_dump() for i in nba.initial] != [i.model_dump() for i in nba.final]:
                raise ValueError("with no evidence requests, final must equal initial")
            if nba.what_changed != "nothing":
                raise ValueError('with no evidence requests, what_changed is "nothing"')
        return self
