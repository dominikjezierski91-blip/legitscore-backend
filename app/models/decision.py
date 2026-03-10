from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class EvidenceRef(BaseModel):
    asset_id: str
    area: str
    note: Optional[str] = None


class Recommendation(BaseModel):
    code: str
    priority: Literal["low", "medium", "high"]


class Reason(BaseModel):
    code: str
    severity: int = Field(..., ge=1, le=5)
    facts: List[str]
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)

    @field_validator("facts")
    @classmethod
    def validate_facts_not_empty(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("facts must contain at least one item")
        return value


class Trace(BaseModel):
    trace_id: str
    model: str
    prompt_version: str
    agent_mode: str
    generated_at: str  # ISO 8601 UTC
    latency_ms: int
    usage: Optional[Dict[str, Any]] = None


class Decision(BaseModel):
    decision_version: str = "1.0"
    verdict: Literal["likely_authentic", "inconclusive", "likely_not_authentic"]
    risk_score: int = Field(..., ge=0, le=100)
    risk_tier: Literal["low", "medium", "high"]
    reasons: List[Reason]
    recommendations: List[Recommendation] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    trace: Trace

    @field_validator("decision_version")
    @classmethod
    def validate_decision_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("decision_version must be '1.0'")
        return value

    @model_validator(mode="after")
    def validate_consistency(self) -> "Decision":
        score = self.risk_score
        tier = self.risk_tier
        verdict = self.verdict

        # risk_tier zgodny z risk_score
        if score <= 33 and tier != "low":
            raise ValueError("risk_tier must be 'low' for risk_score <= 33")
        if 34 <= score <= 66 and tier != "medium":
            raise ValueError("risk_tier must be 'medium' for 34 <= risk_score <= 66")
        if score >= 67 and tier != "high":
            raise ValueError("risk_tier must be 'high' for risk_score >= 67")

        # verdict zgodny z tier
        if tier == "low" and verdict == "likely_not_authentic":
            raise ValueError("low risk_tier cannot have verdict 'likely_not_authentic'")
        if tier == "high" and verdict == "likely_authentic":
            raise ValueError("high risk_tier cannot have verdict 'likely_authentic'")

        return self

