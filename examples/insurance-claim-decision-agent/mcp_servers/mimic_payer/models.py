"""Pydantic input contracts for the MCP tools.

Validating inputs at the boundary keeps the tool surface domain-shaped and makes
the resulting tool-call records semantic and control-mappable rather than opaque.
"""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class GetClaimIn(BaseModel):
    claim_id: str


class GetMemberCoverageIn(BaseModel):
    member_id: str


class GetBenefitRulesIn(BaseModel):
    plan_id: str
    procedure_codes: Optional[list[str]] = None  # None = the whole plan (heavy)


class GetAccumulatorsIn(BaseModel):
    member_id: str
    plan_year: int


class GetClaimHistoryIn(BaseModel):
    member_id: str
    procedure_code: Optional[str] = None
    window_days: int = 365


class CheckNetworkIn(BaseModel):
    provider_id: str
    plan_id: str


class GetAllowedAmountIn(BaseModel):
    plan_id: str
    procedure_codes: list[str]


class LookupReasonCodeIn(BaseModel):
    code: str


class AdjudicateLineIn(BaseModel):
    claim_id: str
    line_number: int


class LineDecision(BaseModel):
    line_number: int
    decision: Literal["pay", "deny", "reduce", "pend"]
    allowed_cents: int = 0
    plan_paid_cents: int = 0
    patient_resp_cents: int = 0
    deductible_cents: int = 0
    coinsurance_cents: int = 0
    copay_cents: int = 0
    carc: list[dict] = Field(default_factory=list)
    rarc: list[str] = Field(default_factory=list)
    rule_basis: list[str] = Field(default_factory=list)
    # The model passes the evidence handles from payer_adjudicate_line, which returns
    # them as a {name: handle} map; accept that or a plain list of handles.
    evidence: Union[list[str], dict[str, str]] = Field(default_factory=list)
    rationale: str = ""

    @field_validator("evidence", mode="after")
    @classmethod
    def _flatten_evidence(cls, v):
        return list(v.values()) if isinstance(v, dict) else v


class RecordDecisionIn(BaseModel):
    claim_id: str
    model_version: str
    prompt_version_hash: str
    lines: list[LineDecision]


class RequestReviewIn(BaseModel):
    claim_id: str
    summary: str
    reason: str = "adverse_or_above_threshold"
    reviewer_role: str = "claims_examiner"


class PostAdjudicationIn(BaseModel):
    claim_id: str
