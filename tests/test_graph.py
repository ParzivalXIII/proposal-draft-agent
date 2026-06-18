import pytest
from langchain_core.language_models import FakeListChatModel

from backend.models import schemas
from backend.graph import build_proposal_graph, ProposalState

@pytest.mark.asyncio
async def test_proposal_graph_happy_path():
    valid_draft_json = schemas.ProposalOutput(
        client_summary="We will automate your invoicing to save 10 hours a week.",
        technical_proposal="FastAPI backend with PostgreSQL.",
        feature_breakdown=[
            schemas.FeatureBreakdown(feature_name="Invoice Gen", description="Auto gen", estimated_hours=16),
            schemas.FeatureBreakdown(feature_name="Dashboard", description="View invoices", estimated_hours=24)
        ]
    ).model_dump_json()

    # Sequence: Draft -> Critique (Approved)
    fake_llm = FakeListChatModel(responses=[valid_draft_json, "APPROVED"])
    graph = build_proposal_graph(fake_llm)
    
    initial_state = ProposalState(
        brief=schemas.BriefInput(client_name="Acme Corp", problem_description="Invoicing takes too long", rough_scope="Automate it"),
        draft=None, critique=None, final_proposal=None, total_hours=None, complexity_tier=None,
        retry_count=0 # <--- Required
    )
    
    final_state = await graph.ainvoke(initial_state)
    
    assert final_state["total_hours"] == 40
    assert final_state["retry_count"] == 0 # No retries needed

@pytest.mark.asyncio
async def test_proposal_graph_refinement_loop():
    """Tests that the agent actually rewrites the draft if the critique fails."""
    
    # 1. Initial Draft (Contains jargon)
    bad_draft = schemas.ProposalOutput(
        client_summary="We will build a REST API with Postgres to fix your data.",
        technical_proposal="Tech stack details...",
        feature_breakdown=[schemas.FeatureBreakdown(feature_name="F1", description="D", estimated_hours=8)]
    ).model_dump_json()

    # 2. The Rewrite (Clean, non-technical)
    good_draft = schemas.ProposalOutput(
        client_summary="We will automate your data entry to eliminate errors.",
        technical_proposal="Tech stack details...",
        feature_breakdown=[schemas.FeatureBreakdown(feature_name="F1", description="D", estimated_hours=8)]
    ).model_dump_json()

    # Sequence:
    # 1. draft_proposal -> returns bad_draft
    # 2. critique_proposal -> returns "CRITIQUE: Too much jargon."
    # 3. refine_proposal -> returns good_draft
    # 4. critique_proposal -> returns "APPROVED"
    fake_llm = FakeListChatModel(responses=[
        bad_draft, 
        "CRITIQUE: Contains technical jargon like 'REST API' and 'Postgres'.", 
        good_draft, 
        "APPROVED"
    ])
    
    graph = build_proposal_graph(fake_llm)
    
    initial_state = ProposalState(
        brief=schemas.BriefInput(client_name="Test", problem_description="Test", rough_scope="Test"),
        draft=None, critique=None, final_proposal=None, total_hours=None, complexity_tier=None,
        retry_count=0
    )
    
    final_state = await graph.ainvoke(initial_state)
    
    # Assertions
    assert final_state["retry_count"] == 1 # It looped once
    assert final_state["critique"] == "APPROVED"
    assert "REST API" not in final_state["final_proposal"].client_summary
    assert final_state["final_proposal"].client_summary == "We will automate your data entry to eliminate errors."

@pytest.mark.asyncio
async def test_proposal_graph_complexity_tiers():
    # ... (Same as before, just ensure retry_count=0 is in initial_state) ...
    valid_draft_json = schemas.ProposalOutput(
        client_summary="Summary", technical_proposal="Tech",
        feature_breakdown=[
            schemas.FeatureBreakdown(feature_name="F1", description="D", estimated_hours=40),
            schemas.FeatureBreakdown(feature_name="F2", description="D", estimated_hours=40),
            schemas.FeatureBreakdown(feature_name="F3", description="D", estimated_hours=40),
            schemas.FeatureBreakdown(feature_name="F4", description="D", estimated_hours=40),
            schemas.FeatureBreakdown(feature_name="F5", description="D", estimated_hours=40)
        ]
    ).model_dump_json()

    fake_llm = FakeListChatModel(responses=[valid_draft_json, "APPROVED"])
    graph = build_proposal_graph(fake_llm)
    
    initial_state = ProposalState(
        brief=schemas.BriefInput(client_name="Test", problem_description="Test", rough_scope="Test"),
        draft=None, critique=None, final_proposal=None, total_hours=None, complexity_tier=None,
        retry_count=0
    )
    
    final_state = await graph.ainvoke(initial_state)
    assert final_state["total_hours"] == 200
    assert final_state["complexity_tier"] == schemas.ComplexityTier.HIGH.value

@pytest.mark.asyncio
async def test_proposal_graph_parse_failure_fallback():
    """If the LLM returns invalid JSON during refinement, fall back to the original draft."""
    
    # 1. Initial valid draft
    valid_draft = schemas.ProposalOutput(
        client_summary="We will use a REST API to solve your problem.",
        technical_proposal="Tech details...",
        feature_breakdown=[schemas.FeatureBreakdown(feature_name="F1", description="D", estimated_hours=8)]
    ).model_dump_json()

    # 2. The refinement returns GARBAGE (not valid JSON)
    garbage_output = "Sure! Here is the revised proposal: { this is not valid json at all }"

    # Sequence:
    # 1. draft_proposal -> returns valid_draft
    # 2. critique_proposal -> returns "CRITIQUE: contains jargon"
    # 3. refine_proposal (attempt 1) -> raises OutputParserException
    # 4. refine_proposal (recovery attempt) -> raises OutputParserException
    # 5. Fallback to valid_draft, retry_count incremented
    # 6. critique_proposal -> returns "APPROVED" (to exit the loop)
    fake_llm = FakeListChatModel(responses=[
        valid_draft,           # draft_proposal
        "CRITIQUE: contains jargon like REST API",  # critique_proposal
        garbage_output,        # refine_proposal (attempt 1 - will fail parse)
        garbage_output,        # refine_proposal (recovery attempt - will fail parse)
        "APPROVED"             # critique_proposal (second pass, exits loop)
    ])

    graph = build_proposal_graph(fake_llm)
    
    initial_state = ProposalState(
        brief=schemas.BriefInput(client_name="Test", problem_description="Test", rough_scope="Test"),
        draft=None, critique=None, final_proposal=None, total_hours=None, complexity_tier=None,
        retry_count=0
    )

    final_state = await graph.ainvoke(initial_state)

    # The graph should NOT crash. It should fall back to the original draft.
    assert final_state["final_proposal"] is not None
    assert final_state["final_proposal"].client_summary == "We will use a REST API to solve your problem."
    assert final_state["retry_count"] == 1
    assert final_state["total_hours"] == 8