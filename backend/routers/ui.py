import json
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
import markdown
import nh3

from backend.core.db import get_session
from backend.models.db_models import Proposal

# HTML tags allowed through sanitization (nh3)
# Used for rendering LLM-generated brief card content safely
_ALLOWED_BRIEF_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "ul", "ol", "li", "strong", "em",
    "code", "pre", "blockquote",
    "table", "thead", "tbody", "tr", "th", "td",
    "a", "hr", "br",
}

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
    
    return Response(
        status_code=200,
        headers={
            "HX-Trigger": json.dumps({
                "proposalCreated": "",
                "toast": {"msg": f"Proposal '{client_name}' created!", "type": "success"}
            })
        }
    )

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
        raw_html = markdown.markdown(proposal.brief_card, extensions=['tables', 'fenced_code'])
        brief_card_html = nh3.clean(raw_html, tags=_ALLOWED_BRIEF_TAGS)
        
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
        raw_html = markdown.markdown(proposal.brief_card, extensions=['tables', 'fenced_code'])
        brief_card_html = nh3.clean(raw_html, tags=_ALLOWED_BRIEF_TAGS)
        
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="fragments/status.html",
        context={"proposal": proposal, "brief_card_html": brief_card_html}
    )


@router.delete("/proposals/{proposal_id}")
async def delete_proposal_ui(
    request: Request,
    proposal_id: str,
    session: AsyncSession = Depends(get_session)
):
    proposal = await session.get(Proposal, proposal_id)
    if not proposal:
        return HTMLResponse("Not found", status_code=404)
    
    await session.delete(proposal)
    await session.commit()
    
    return Response(
        status_code=200,
        headers={
            "HX-Trigger": json.dumps({
                "toast": {"msg": "Proposal deleted", "type": "success"}
            }),
            "HX-Redirect": "/ui/"
        }
    )