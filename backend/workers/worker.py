from arq.connections import RedisSettings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate # <--- NEW
from loguru import logger
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from datetime import datetime, timezone
import json

from backend.models.schemas import BriefInput
from backend.models.db_models import Proposal, ProposalStatus
from backend.core.config import settings
from backend.graph import build_proposal_graph, ProposalState

real_llm = ChatOpenAI(
    model=settings.llm_model_name,
    temperature=settings.llm_temperature,
    api_key=SecretStr(settings.openai_api_key),
    base_url=settings.openai_base_url,
)
proposal_graph = build_proposal_graph(real_llm)

async def startup(ctx):
    ctx['db_engine'] = create_async_engine(settings.database_url, echo=False)
    # Create ARQ pool for inter-job communication
    from arq import create_pool
    from arq.connections import RedisSettings
    ctx['arq_pool'] = await create_pool(RedisSettings(host=settings.redis_host, port=settings.redis_port))

async def shutdown(ctx):
    await ctx['db_engine'].dispose()
    await ctx['arq_pool'].close()

async def generate_proposal(ctx, proposal_id: str):
    logger.info(f"Starting proposal generation for {proposal_id}")
    engine = ctx['db_engine']
    
    async with AsyncSession(engine, expire_on_commit=False) as session:
        proposal = await session.get(Proposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
            
        proposal.status = ProposalStatus.RUNNING
        proposal.updated_at = datetime.now(timezone.utc)
        session.add(proposal)
        await session.commit()
        
        try:
            brief = BriefInput(
                client_name=proposal.client_name,
                problem_description=proposal.problem_description,
                rough_scope=proposal.rough_scope
            )
            
            initial_state = ProposalState(
                brief=brief, draft=None, critique=None, final_proposal=None, 
                total_hours=None, complexity_tier=None, retry_count=0
            )
            
            final_state = await proposal_graph.ainvoke(initial_state)
            result = final_state["final_proposal"]
            
            proposal.status = ProposalStatus.COMPLETED
            proposal.client_summary = result.client_summary
            proposal.technical_proposal = result.technical_proposal
            proposal.features_json = json.dumps([f.model_dump() for f in result.feature_breakdown])
            proposal.total_hours = final_state["total_hours"]
            proposal.complexity_tier = final_state["complexity_tier"]
            
            # Auto-trigger brief card generation
            arq_pool = ctx['arq_pool']
            await arq_pool.enqueue_job('generate_brief_card', proposal_id)
            logger.info(f"Auto-triggered brief card generation for {proposal_id}")
            
        except Exception as e:
            logger.exception("Proposal generation failed")
            proposal.status = ProposalStatus.FAILED
            proposal.error_message = str(e)
        finally:
            proposal.updated_at = datetime.now(timezone.utc)
            session.add(proposal)
            await session.commit()

# --- NEW FUNCTION ---
async def generate_brief_card(ctx, proposal_id: str):
    logger.info(f"Starting brief card generation for {proposal_id}")
    engine = ctx['db_engine']
    
    async with AsyncSession(engine, expire_on_commit=False) as session:
        proposal = await session.get(Proposal, proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
            
        try:
            # Format features into a readable string for the prompt
            features_text = "None provided."
            if proposal.features_json:
                features = json.loads(proposal.features_json)
                features_text = "\n".join([f"- {f['feature_name']}: {f['description']} (Est: {f['estimated_hours']}h)" for f in features])
                
            prompt = ChatPromptTemplate.from_template(
                "You are a client success manager. Create a highly readable, plain-language 'Brief Card' "
                "for the client based on the following approved proposal data.\n"
                "Format it in clean Markdown with a welcoming tone, clear sections, and bullet points.\n"
                "STRICT RULE: DO NOT use any technical jargon (no API, DB, backend, deploy, etc.).\n\n"
                "CLIENT SUMMARY: {summary}\n"
                "FEATURES: {features}\n"
                "TOTAL ESTIMATED TIME: {hours} hours\n"
                "COMPLEXITY: {tier}\n"
            )
            
            response = await real_llm.ainvoke(prompt.format(
                summary=proposal.client_summary,
                features=features_text,
                hours=proposal.total_hours,
                tier=proposal.complexity_tier
            ))
            
            content = response.content if isinstance(response.content, str) else str(response.content)
            proposal.brief_card = content.strip()
            
        except Exception as e:
            logger.exception("Brief card generation failed")
            
        finally:
            proposal.updated_at = datetime.now(timezone.utc)
            session.add(proposal)
            await session.commit()

class WorkerSettings:
    functions = [generate_proposal, generate_brief_card] # <--- Register new function
    redis_settings = RedisSettings(host=settings.redis_host, port=settings.redis_port)
    on_startup = startup
    on_shutdown = shutdown