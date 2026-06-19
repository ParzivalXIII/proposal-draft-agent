from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
import json

from backend.models.schemas import BriefInput, ProposalRead
from backend.models.db_models import Proposal, ProposalStatus
from backend.core.db import get_session

router = APIRouter(prefix="/api", tags=["API"])

def _format_proposal_response(proposal: Proposal) -> dict:
    """Helper to parse the JSON string back into a list for the API response."""
    data = proposal.model_dump()
    if proposal.features_json:
        data["feature_breakdown"] = json.loads(proposal.features_json)
    else:
        data["feature_breakdown"] = None
    return data

@router.post("/proposals", status_code=202, response_model=ProposalRead)
async def create_proposal(
    request: Request,  # Injected to access app.state.arq_pool
    brief: BriefInput, 
    session: AsyncSession = Depends(get_session)
):
    db_proposal = Proposal(
        client_name=brief.client_name,
        problem_description=brief.problem_description,
        rough_scope=brief.rough_scope
    )
    session.add(db_proposal)
    await session.commit()
    await session.refresh(db_proposal)
    
    job = await request.app.state.arq_pool.enqueue_job('generate_proposal', db_proposal.id)
    db_proposal.job_id = job.job_id
    await session.commit()
    await session.refresh(db_proposal)
    
    return _format_proposal_response(db_proposal)

@router.get("/proposals/{proposal_id}", response_model=ProposalRead)
async def get_proposal(
    proposal_id: str, 
    session: AsyncSession = Depends(get_session)
):
    proposal = await session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
        
    return _format_proposal_response(proposal)

@router.post("/proposals/{proposal_id}/brief-card", status_code=202)
async def create_brief_card(
    request: Request,  # Injected to access app.state.arq_pool
    proposal_id: str,
    session: AsyncSession = Depends(get_session)
):
    proposal = await session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != ProposalStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Proposal must be completed before generating a brief card.")
        
    job = await request.app.state.arq_pool.enqueue_job('generate_brief_card', proposal_id)
    return {"job_id": job.job_id, "status": "queued", "message": "Brief card generation started."}