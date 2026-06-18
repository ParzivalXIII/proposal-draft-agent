from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.language_models import BaseChatModel
from langchain_core.exceptions import OutputParserException
from loguru import logger

from backend.models import schemas

MAX_RETRIES = 2

class ProposalState(TypedDict):
    brief: schemas.BriefInput
    draft: schemas.ProposalOutput | None
    critique: str | None
    final_proposal: schemas.ProposalOutput | None
    total_hours: int | None
    complexity_tier: str | None
    retry_count: int

def build_proposal_graph(llm: BaseChatModel):
    parser = PydanticOutputParser(pydantic_object=schemas.ProposalOutput)

    async def draft_proposal(state: ProposalState) -> dict:
        logger.info("Drafting initial proposal...")
        prompt = ChatPromptTemplate.from_template(
            "You are an expert solutions architect. Draft a proposal based on this brief:\n"
            "Client: {client_name}\nProblem: {problem_description}\nScope: {rough_scope}\n\n"
            "For the client_summary, write strictly for a non-technical business stakeholder.\n"
            "For feature_breakdown, estimate hours strictly in buckets of 2, 4, 8, 16, 24, or 40.\n\n"
            "{format_instructions}"
        )
        
        chain = prompt | llm | parser
        result = await chain.ainvoke({
            "client_name": state["brief"].client_name,
            "problem_description": state["brief"].problem_description,
            "rough_scope": state["brief"].rough_scope,
            "format_instructions": parser.get_format_instructions()
        })
        return {"draft": result, "retry_count": 0}

    async def critique_proposal(state: ProposalState) -> dict:
        logger.info(f"Critiquing draft (Attempt {state['retry_count'] + 1})...")
        draft = state["draft"]
        if draft is None: raise ValueError("Draft missing.")
            
        prompt = ChatPromptTemplate.from_template(
            "Review this client summary: {summary}\n"
            "If it contains technical jargon, output a critique. If perfect, output exactly: 'APPROVED'."
        )
        response = await (prompt | llm).ainvoke({"summary": draft.client_summary})
        content = response.content if isinstance(response.content, str) else str(response.content)
        return {"critique": content.strip()}


    async def refine_proposal(state: ProposalState) -> dict:
        logger.info("Refining proposal based on critique...")
        draft = state["draft"]
        critique = state["critique"]
        if draft is None:
            raise ValueError("Draft missing.")

        # --- Attempt 1: Standard refinement ---
        prompt = ChatPromptTemplate.from_template(
            "You are an expert solutions architect. Your previous draft was critiqued:\n"
            "CRITIQUE: {critique}\n\n"
            "ORIGINAL BRIEF: {brief}\n\n"
            "Please rewrite the FULL proposal (JSON format) to address this critique. "
            "Ensure the client_summary is now strictly non-technical.\n\n"
            "{format_instructions}"
        )
    
        chain = prompt | llm | parser

        try:
            new_draft = await chain.ainvoke({
                "critique": critique,
                "brief": state["brief"].model_dump_json(),
                "format_instructions": parser.get_format_instructions()
            })
            return {"draft": new_draft, "retry_count": state["retry_count"] + 1}

        except OutputParserException as e:
            # --- Attempt 2: Error recovery with the raw bad output ---
            raw_output = str(e.llm_output) if e.llm_output else "No output captured."
            logger.warning(f"JSON parse failed. Attempting recovery. Raw output: {raw_output[:200]}...")

            recovery_prompt = ChatPromptTemplate.from_template(
                "You previously generated invalid JSON. Here is the broken output:\n"
                "BROKEN OUTPUT: {raw_output}\n\n"
                "Please fix it and return ONLY valid JSON that matches this schema:\n"
                "{format_instructions}\n\n"
                "Do NOT include markdown code fences. Return raw JSON only."
            )

            try:
                recovery_chain = recovery_prompt | llm | parser
                new_draft = await recovery_chain.ainvoke({
                    "raw_output": raw_output,
                    "format_instructions": parser.get_format_instructions()
                })
                logger.info("Recovery succeeded.")
                return {"draft": new_draft, "retry_count": state["retry_count"] + 1}

            except OutputParserException:
                # --- Fallback: Keep the previous valid draft ---
                logger.error("Recovery failed. Falling back to previous draft.")
                return {"retry_count": state["retry_count"] + 1}
                # Note: We do NOT update "draft", so the previous valid version persists

        prompt = ChatPromptTemplate.from_template(
            "You are an expert solutions architect. Your previous draft was critiqued:\n"
            "CRITIQUE: {critique}\n\n"
            "ORIGINAL BRIEF: {brief}\n\n"
            "Please rewrite the FULL proposal (JSON format) to address this critique. "
            "Ensure the client_summary is now strictly non-technical.\n\n"
            "{format_instructions}"
        )
        
        chain = prompt | llm | parser
        new_draft = await chain.ainvoke({
            "critique": critique,
            "brief": state["brief"].model_dump_json(),
            "format_instructions": parser.get_format_instructions()
        })
        
        return {
            "draft": new_draft, 
            "retry_count": state["retry_count"] + 1
        }

    def calculate_metrics(state: ProposalState) -> dict:
        # FIX: The approved draft IS the final proposal. 
        # Promote it here since we bypassed the refine node on approval.
        proposal = state["draft"]
        if proposal is None: 
            raise ValueError("Draft is missing in state, cannot calculate metrics.")
            
        total_hours = sum(f.estimated_hours for f in proposal.feature_breakdown)
        
        if total_hours <= 40: tier = schemas.ComplexityTier.LOW
        elif total_hours <= 160: tier = schemas.ComplexityTier.MEDIUM
        elif total_hours <= 400: tier = schemas.ComplexityTier.HIGH
        else: tier = schemas.ComplexityTier.ENTERPRISE
            
        return {
            "total_hours": total_hours, 
            "complexity_tier": tier.value,
            "final_proposal": proposal # <--- Promote draft to final_proposal
        }

    def route_after_critique(state: ProposalState) -> str:
        if state["critique"] == "APPROVED":
            return "calculate"
        if state["retry_count"] >= MAX_RETRIES:
            logger.warning(f"Max retries ({MAX_RETRIES}) reached. Accepting current draft.")
            return "calculate"
        return "refine"

    workflow = StateGraph(ProposalState)
    workflow.add_node("draft", draft_proposal)
    workflow.add_node("critique", critique_proposal)
    workflow.add_node("refine", refine_proposal)
    workflow.add_node("calculate", calculate_metrics)

    workflow.set_entry_point("draft")
    workflow.add_edge("draft", "critique")
    
    workflow.add_conditional_edges(
        "critique", 
        route_after_critique, 
        {"refine": "refine", "calculate": "calculate"}
    )
    
    workflow.add_edge("refine", "critique")
    workflow.add_edge("calculate", END)

    return workflow.compile()