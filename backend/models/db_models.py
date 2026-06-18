import uuid
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone
from enum import Enum

class ProposalStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class Proposal(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    job_id: Optional[str] = Field(default=None, index=True) # ARQ job ID
    
    # Input
    client_name: str
    problem_description: str
    rough_scope: str
    
    # Status
    status: ProposalStatus = Field(default=ProposalStatus.QUEUED)
    error_message: Optional[str] = None
    
    # Output
    client_summary: Optional[str] = None
    technical_proposal: Optional[str] = None
    features_json: Optional[str] = None # Stored as JSON string for SQLite simplicity
    total_hours: Optional[int] = None
    complexity_tier: Optional[str] = None

    brief_card: Optional[str] = None 
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

