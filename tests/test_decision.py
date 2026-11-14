import asyncio
import json
from typing import List, Optional

import httpx
from pydantic import BaseModel

from backend.decision import (
    IRIS_QUESTIONS,
    evaluate_ranked_properties,
)


class TeammatePropertyDetails(BaseModel):
    """Matches the `PropertyDetails` schema in `backend/agent.py`."""

    url: str
    price: Optional[int] = None
    sqm: Optional[int] = None
    floor: Optional[str] = None
    features: List[str] = []
    agent_phone: Optional[str] = None
    agentic_score: int = 0
    score_reason: str = ""


def test_iris_questions_strict_scope():
    assert set(IRIS_QUESTIONS["verdict"]["criteria"].keys()) == {"SAFE", "POSSIBLY_SCAM"}
    assert "outreach_channel_strategy" not in IRIS_QUESTIONS


def test_evaluate_ranked_properties_parses_oumi_systemone_response():
    ranked = [
        TeammatePropertyDetails(
            url="https://example.com/listing/bait-1",
            price=400,
            sqm=70,
            floor="3rd",
            features=["renovated", "furnished"],
            agent_phone=None,
            agentic_score=10,
            score_reason="High feature score at suspiciously low price.",
        ),
        TeammatePropertyDetails(
            url="https://example.com/listing/safe-2",
            price=650,
            sqm=55,
            floor="2nd",
            features=["bright", "pet friendly"],
            agent_phone="+30 210 0000000",
            agentic_score=9,
            score_reason="Matches user criteria at normal market price.",
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://inference.oumi.ai/v1/systemone"
        assert request.headers["X-API-Key"] == "test-key"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "projects/test-proj/models/iris-latest"
        rank = body["state"]["initial_rank"]

        if rank == 1:
            return httpx.Response(
                200,
                json={
                    "model": body["model"],
                    "answers": {
                        "verdict": {"type": "choice", "choice": "POSSIBLY_SCAM", "confidence": 0.95},
                        "is_possibly_scam": {"type": "noul", "noul": 0.95},
                        "price_anomaly": {"type": "noul", "noul": 0.97},
                        "advance_fee_lure": {"type": "noul", "noul": 0.91},
                        "stolen_or_cloned_media": {"type": "noul", "noul": 0.88},
                        "metadata_inconsistency": {"type": "noul", "noul": 0.82},
                    },
                    "usage": {"inputTokens": 250, "outputTokens": 0},
                },
            )
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "answers": {
                    "verdict": {"type": "choice", "choice": "SAFE", "confidence": 0.96},
                    "is_possibly_scam": {"type": "noul", "noul": 0.04},
                    "price_anomaly": {"type": "noul", "noul": 0.06},
                    "advance_fee_lure": {"type": "noul", "noul": 0.02},
                    "stolen_or_cloned_media": {"type": "noul", "noul": 0.03},
                    "metadata_inconsistency": {"type": "noul", "noul": 0.05},
                },
                "usage": {"inputTokens": 240, "outputTokens": 0},
            },
        )

    async def _run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as mock_client:
            return await evaluate_ranked_properties(
                ranked,
                api_key="test-key",
                project_id="test-proj",
                client=mock_client,
            )

    batch = asyncio.run(_run())

    assert batch.intercepted_top_match is True
    assert len(batch.possibly_scam_properties) == 1
    assert len(batch.safe_properties) == 1

    first = batch.results[0]
    assert first.verdict == "POSSIBLY_SCAM"
    assert first.initial_rank == 1
    assert first.verified_rank is None
    assert first.scam_risk_pct == 95
    assert first.rubric_probabilities["price_anomaly"] == 0.97

    second = batch.results[1]
    assert second.verdict == "SAFE"
    assert second.initial_rank == 2
    assert second.verified_rank == 1
    assert second.scam_risk_pct == 4
