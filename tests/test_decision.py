from typing import List, Optional
from pydantic import BaseModel
from backend.decision import (
    OumiIrisDecisionModel,
    evaluate_ranked_properties_sync,
)


class TeammatePropertyDetails(BaseModel):
    """Mirrors the teammate's `PropertyDetails` schema in `backend/agent.py`."""

    url: str
    price: Optional[int] = None
    sqm: Optional[int] = None
    floor: Optional[str] = None
    features: List[str] = []
    agent_phone: Optional[str] = None
    agentic_score: int = 0
    score_reason: str = ""


def test_decision_evaluates_ranked_properties_safe_vs_possibly_scam():
    ranked_from_teammate = [
        TeammatePropertyDetails(
            url="https://www.spitogatos.gr/enoikiaseis-katoikies/koukaki/111",
            price=420,
            sqm=68,
            floor="3rd",
            features=["renovated", "furnished", "pet friendly"],
            agent_phone="+44 7911 123456",
            agentic_score=10,
            score_reason="Working in London UK, reservation via Airbnb escrow before viewing, WhatsApp only.",
        ),
        TeammatePropertyDetails(
            url="https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati/222",
            price=600,
            sqm=52,
            floor="2nd",
            features=["bright", "pet friendly", "balcony"],
            agent_phone="+30 210 7512345",
            agentic_score=9,
            score_reason="Bright 2nd floor apartment in Pangrati within 600 EUR budget.",
        ),
    ]

    batch = evaluate_ranked_properties_sync(ranked_from_teammate)

    assert batch.telemetry.total_evaluated == 2
    assert batch.telemetry.possibly_scam_count == 1
    assert batch.telemetry.safe_count == 1
    assert batch.telemetry.intercepted_rank_one is True
    assert batch.wow_factor_banner is not None

    scam_res = batch.results[0]
    assert scam_res.verdict == "POSSIBLY_SCAM"
    assert scam_res.initial_rank == 1
    assert scam_res.verified_rank is None
    assert scam_res.intercepted_top_match is True
    assert len(scam_res.forensic_bars) == 4

    safe_res = batch.results[1]
    assert safe_res.verdict == "SAFE"
    assert safe_res.initial_rank == 2
    assert safe_res.verified_rank == 1
    assert len(safe_res.forensic_bars) == 4


def test_iris_state_and_questions_have_no_outreach_strategy():
    from backend.decision import IRIS_SCAM_QUESTIONS, normalize_ranked_property

    model = OumiIrisDecisionModel()
    prop = normalize_ranked_property(
        TeammatePropertyDetails(
            url="https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati/222",
            price=600,
            sqm=50,
            floor="1st",
            features=["pet friendly"],
            agent_phone="+30 697 0000000",
            agentic_score=8,
            score_reason="Matches user budget.",
        ),
        initial_rank=1,
    )
    state = model.build_iris_state(prop)

    assert state["quantitative_signals"]["price_per_sqm"] == 12.0
    assert set(IRIS_SCAM_QUESTIONS["verdict"]["criteria"].keys()) == {"SAFE", "POSSIBLY_SCAM"}
    assert "outreach_channel_strategy" not in IRIS_SCAM_QUESTIONS
