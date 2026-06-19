from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
import markdown

from backend.core.db import get_session
from backend.models.db_models import Proposal

router = APIRouter(prefix="/ui", tags=["UI"])

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Proposal).order_by(Proposal.created_at.desc()))
    proposals = result.scalars().all()
    
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"proposals": proposals}
    )

@router.post("/proposals")
async def create_proposal_ui(
    request: Request,
    client_name: str = Form(...),
    problem_description: str = Form(...),
    rough_scope: str = Form(...),
    session: AsyncSession = Depends(get_session)
):
    db_proposal = Proposal(
        client_name=client_name,
        problem_description=problem_description,
        rough_scope=rough_scope
    )
    session.add(db_proposal)
    await session.commit()
    await session.refresh(db_proposal)
    
    proposal_id = db_proposal.id
    
    job = await request.app.state.arq_pool.enqueue_job('generate_proposal', proposal_id)
    db_proposal.job_id = job.job_id
    await session.commit()
    
    return RedirectResponse(url=f"/ui/proposals/{proposal_id}", status_code=303)

# Static route MUST come before parameterized routes
@router.get("/proposals/fragment", response_class=HTMLResponse)
async def proposal_list_fragment(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Proposal).order_by(Proposal.created_at.desc()))
    proposals = result.scalars().all()
    
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="fragments/proposal_list.html",
        context={"proposals": proposals}
    )

@router.get("/proposals/{proposal_id}", response_class=HTMLResponse)
async def detail(request: Request, proposal_id: str, session: AsyncSession = Depends(get_session)):
    proposal = await session.get(Proposal, proposal_id)
    if not proposal:
        return HTMLResponse("Not found", status_code=404)
        
    brief_card_html = ""
    if proposal.brief_card:
        brief_card_html = markdown.markdown(proposal.brief_card, extensions=['tables', 'fenced_code'])
        
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="detail.html",
        context={"proposal": proposal, "brief_card_html": brief_card_html}
    )

@router.get("/proposals/{proposal_id}/fragment", response_class=HTMLResponse)
async def status_fragment(request: Request, proposal_id: str, session: AsyncSession = Depends(get_session)):
    proposal = await session.get(Proposal, proposal_id)
    if not proposal:
        return HTMLResponse("Not found", status_code=404)
        
    brief_card_html = ""
    if proposal.brief_card:
        brief_card_html = markdown.markdown(proposal.brief_card, extensions=['tables', 'fenced_code'])
        
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="fragments/status.html",
        context={"proposal": proposal, "brief_card_html": brief_card_html}
    )