from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum
from datetime import datetime

class ComplexityTier(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    ENTERPRISE = "Enterprise"

class BriefInput(BaseModel):
    client_name: str = Field(description="Name of the client or company")
    problem_description: str = Field(description="The core business problem they need solved")
    rough_scope: str = Field(description="Initial thoughts on features or requirements")

class FeatureBreakdown(BaseModel):
    feature_name: str
    description: str = Field(description="Plain language description of what it does")
    estimated_hours: int = Field(description="Estimated hours. Must be one of: 2, 4, 8, 16, 24, 40")

class ProposalOutput(BaseModel):
    client_summary: str = Field(description="Plain-language executive summary. NO technical jargon. Focus strictly on business value and solving the problem.")
    technical_proposal: str = Field(description="Structured technical approach, architecture, and stack recommendations.")
    feature_breakdown: list[FeatureBreakdown]
    # Note: total_hours and complexity_tier will be calculated deterministically in Python

class ProposalRead(BaseModel):
    id: str
    job_id: str | None
    status: str
    client_name: str
    problem_description: str
    rough_scope: str
    error_message: str | None
    client_summary: str | None
    technical_proposal: str | None
    feature_breakdown: list[FeatureBreakdown] | None
    total_hours: int | None
    complexity_tier: str | None
    brief_card: str | None 
    created_at: datetime
    updated_at: datetime