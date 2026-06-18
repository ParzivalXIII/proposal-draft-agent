from fastapi import FastAPI, HTTPException, Depends
from arq import create_pool
from arq.connections import RedisSettings
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
import json

from backend.models.schemas import BriefInput, ProposalRead
from backend.models.db_models import Proposal, ProposalStatus 
from backend.core.config import settings
from backend.core.db import get_session, init_db, engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await create_pool(
        RedisSettings(host=settings.redis_host, port=settings.redis_port)
    )
    await init_db()
    yield
    await app.state.arq_pool.close()
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

@app.post("/proposals", status_code=202, response_model=ProposalRead)
async def create_proposal(
    brief: BriefInput, 
    session: AsyncSession = Depends(get_session)
):
    # 1. Create DB record
    db_proposal = Proposal(
        client_name=brief.client_name,
        problem_description=brief.problem_description,
        rough_scope=brief.rough_scope
    )
    session.add(db_proposal)
    await session.commit()
    await session.refresh(db_proposal)
    
    # 2. Enqueue ARQ job
    job = await app.state.arq_pool.enqueue_job('generate_proposal', db_proposal.id)
    db_proposal.job_id = job.job_id
    await session.commit()
    await session.refresh(db_proposal)
    
    return _format_proposal_response(db_proposal)

@app.get("/proposals/{proposal_id}", response_model=ProposalRead)
async def get_proposal(
    proposal_id: str, 
    session: AsyncSession = Depends(get_session)
):
    proposal = await session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
        
    return _format_proposal_response(proposal)

@app.post("/proposals/{proposal_id}/brief-card", status_code=202)
async def create_brief_card(
    proposal_id: str,
    session: AsyncSession = Depends(get_session)
):
    proposal = await session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != ProposalStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Proposal must be completed before generating a brief card.")
        
    job = await app.state.arq_pool.enqueue_job('generate_brief_card', proposal_id)
    return {"job_id": job.job_id, "status": "queued", "message": "Brief card generation started."}

# FIX 2: Removed the duplicate definition of this function
def _format_proposal_response(proposal: Proposal) -> dict:
    """Helper to parse the JSON string back into a list for the API response."""
    data = proposal.model_dump()
    if proposal.features_json:
        data["feature_breakdown"] = json.loads(proposal.features_json)
    else:
        data["feature_breakdown"] = None
    return data