import asyncio
import json
import os
from typing import List, Optional

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend import agent, decision  # Import first: both call load_dotenv() on import.
from backend.decision import (
    IRIS_QUESTIONS,
    RED_FLAG_LABELS,
    build_iris_state,
    evaluate_ranked_properties,
    model_path,
    normalize_project_id,
    oumi_configured,
    probe_oumi,
    top_red_flag,
)
from backend.main import app

SYSTEMONE = "https://inference.oumi.ai/v1/systemone"


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


def _answers(scam: float, verdict: Optional[str] = None, **flags: float) -> dict:
    """An Oumi SystemOne response body. `verdict=None` omits the choice answer entirely."""
    answers: dict = {"is_possibly_scam": {"type": "noul", "noul": scam}}
    if verdict is not None:
        answers["verdict"] = {"type": "choice", "choice": verdict, "confidence": 0.9}
    for key in RED_FLAG_LABELS:
        answers[key] = {"type": "noul", "noul": flags.get(key, 0.01)}
    return {"model": "projects/p/models/iris-latest", "answers": answers, "usage": {"inputTokens": 200, "outputTokens": 0}}


def _evaluate(ranked, handler, project_id="test-proj", **kwargs):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await evaluate_ranked_properties(
                ranked, api_key="test-key", project_id=project_id, client=client, **kwargs
            )

    return asyncio.run(go())


@pytest.fixture
def no_oumi_env(monkeypatch):
    monkeypatch.delenv("OUMI_API_KEY", raising=False)
    monkeypatch.delenv("OUMI_PROJECT_ID", raising=False)


@pytest.fixture
def fake_oumi_env(monkeypatch):
    monkeypatch.setenv("OUMI_API_KEY", "test-key")
    monkeypatch.setenv("OUMI_PROJECT_ID", "test-proj")


# ---------------------------------------------------------------------------
# Request contract
# ---------------------------------------------------------------------------
def test_iris_questions_strict_scope():
    assert set(IRIS_QUESTIONS["verdict"]["criteria"].keys()) == {"SAFE", "POSSIBLY_SCAM"}
    assert "outreach_channel_strategy" not in IRIS_QUESTIONS
    assert set(RED_FLAG_LABELS) <= set(IRIS_QUESTIONS)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("abc-123", "abc-123"),
        ("  abc-123  ", "abc-123"),
        ("abc-123/", "abc-123"),
        ("projects/abc-123", "abc-123"),
        ("projects/  abc-123  /", "abc-123"),
        ("projects/abc-123/models/iris-latest", "abc-123"),
        ("projects/abc-123/models/iris-latest/", "abc-123"),
        ("/projects/abc-123/", "abc-123"),
        ("projects/", ""),
        ("/projects/", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_project_id(raw, expected):
    assert normalize_project_id(raw) == expected


def test_model_path_never_double_prefixes():
    assert model_path("projects/abc/models/iris-latest") == "projects/abc/models/iris-latest"
    assert model_path("abc") == "projects/abc/models/iris-latest"


def test_oumi_configured(monkeypatch, no_oumi_env):
    assert oumi_configured() is False
    monkeypatch.setenv("OUMI_API_KEY", "k")
    monkeypatch.setenv("OUMI_PROJECT_ID", "   ")
    assert oumi_configured() is False
    monkeypatch.setenv("OUMI_PROJECT_ID", "projects/abc")
    assert oumi_configured() is True


def test_missing_credentials_raise(no_oumi_env):
    with pytest.raises(ValueError, match="OUMI_API_KEY"):
        asyncio.run(evaluate_ranked_properties([{"url": "u"}]))


def test_evaluate_empty_ranked_properties_returns_empty_batch(fake_oumi_env):
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Empty input must not call {request.url}")

    batch = _evaluate([], fail_if_called)
    assert batch.results == []
    assert batch.safe_properties == []
    assert batch.possibly_scam_properties == []
    assert batch.intercepted_top_match is False


def test_build_iris_state_price_signals():
    state = build_iris_state({"url": "u", "price": 500, "sqm": 50}, initial_rank=1, cohort_median_eur_per_sqm=12.5)
    assert state["initial_rank"] == 1
    assert state["price_signals"] == {
        "eur_per_sqm": 10.0,
        "cohort_median_eur_per_sqm": 12.5,
        "deviation_from_cohort_pct": -20.0,
    }


@pytest.mark.parametrize("prop", [{"price": 500, "sqm": None}, {"price": None, "sqm": 50}, {"price": 500, "sqm": 0}])
def test_build_iris_state_handles_missing_numbers(prop):
    signals = build_iris_state(prop, initial_rank=2, cohort_median_eur_per_sqm=10.0)["price_signals"]
    assert signals["eur_per_sqm"] is None
    assert signals["deviation_from_cohort_pct"] is None


def test_request_uses_cohort_median_and_normalized_model():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SYSTEMONE
        assert request.headers["X-API-Key"] == "test-key"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_answers(0.02, "SAFE"))

    cohort = [{"price": 600, "sqm": 60}, {"price": 800, "sqm": 40}, {"price": 300, "sqm": 0}, {"price": None, "sqm": 50}]
    _evaluate(
        [{"url": "u", "price": 500, "sqm": 50}],
        handler,
        project_id="projects/test-proj/models/iris-latest",
        all_properties=cohort,
    )
    body = bodies[0]
    assert body["model"] == "projects/test-proj/models/iris-latest"
    assert body["questions"] == IRIS_QUESTIONS
    assert body["state"]["price_signals"]["cohort_median_eur_per_sqm"] == 15.0  # median of 10 and 20


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------
def test_evaluate_ranked_properties_parses_oumi_systemone_response():
    ranked = [
        TeammatePropertyDetails(
            url="https://example.com/listing/bait-1", price=400, sqm=70, floor="3rd",
            features=["renovated", "furnished"], agentic_score=10,
            score_reason="High feature score at suspiciously low price.",
        ),
        TeammatePropertyDetails(
            url="https://example.com/listing/safe-2", price=650, sqm=55, floor="2nd",
            features=["bright", "pet friendly"], agent_phone="+30 210 0000000", agentic_score=9,
            score_reason="Matches user criteria at normal market price.",
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "projects/test-proj/models/iris-latest"
        if body["state"]["initial_rank"] == 1:
            return httpx.Response(
                200,
                json=_answers(0.95, "POSSIBLY_SCAM", price_anomaly=0.97, advance_fee_lure=0.91,
                              stolen_or_cloned_media=0.88, metadata_inconsistency=0.82),
            )
        return httpx.Response(200, json=_answers(0.04, "SAFE"))

    batch = _evaluate(ranked, handler)

    assert batch.intercepted_top_match is True
    assert len(batch.possibly_scam_properties) == 1
    assert len(batch.safe_properties) == 1

    first, second = batch.results
    assert first.verdict == "POSSIBLY_SCAM"
    assert first.initial_rank == 1
    assert first.verified_rank is None
    assert first.scam_risk_pct == 95
    assert first.scam_reason == RED_FLAG_LABELS["price_anomaly"]

    assert second.verdict == "SAFE"
    assert second.verified_rank == 1
    assert second.scam_risk_pct == 4
    assert second.scam_reason is None


@pytest.mark.parametrize(
    "prob, choice, expected",
    [
        (0.52, "SAFE", "POSSIBLY_SCAM"),
        (0.50, "SAFE", "POSSIBLY_SCAM"),
        (0.49, "SAFE", "SAFE"),
        (0.36, "POSSIBLY_SCAM", "SAFE"),
    ],
)
def test_probability_threshold_is_sole_verdict_gate(prob, choice, expected):
    batch = _evaluate([{"url": "u"}], lambda r: httpx.Response(200, json=_answers(prob, choice)))
    assert batch.results[0].verdict == expected


def test_missing_verdict_answer_falls_back_to_probability():
    batch = _evaluate([{"url": "u"}], lambda r: httpx.Response(200, json=_answers(0.8, verdict=None)))
    assert batch.results[0].verdict == "POSSIBLY_SCAM"


def test_unexpected_response_raises_clear_error():
    with pytest.raises(ValueError, match="is_possibly_scam"):
        _evaluate([{"url": "u"}], lambda r: httpx.Response(200, json={"answers": {}}))


def test_http_error_propagates():
    with pytest.raises(httpx.HTTPStatusError):
        _evaluate([{"url": "u"}], lambda r: httpx.Response(401, json={"error": "bad key"}))


def test_top_red_flag_only_names_flags_above_threshold():
    assert top_red_flag({}) is None
    assert top_red_flag({"price_anomaly": 0.2, "advance_fee_lure": 0.49}) is None
    assert top_red_flag({"price_anomaly": 0.6, "advance_fee_lure": 0.9}) == RED_FLAG_LABELS["advance_fee_lure"]


def test_top_red_flag_ignores_unknown_keys_and_breaks_ties_deterministically():
    assert top_red_flag({"unknown_flag": 0.9}) is None
    assert top_red_flag({"unknown_flag": 0.9, "price_anomaly": 0.6}) == RED_FLAG_LABELS["price_anomaly"]
    assert (
        top_red_flag({"metadata_inconsistency": 0.8, "price_anomaly": 0.8})
        == RED_FLAG_LABELS["price_anomaly"]
    )
    assert (
        top_red_flag({"price_anomaly": 0.8, "metadata_inconsistency": 0.8})
        == RED_FLAG_LABELS["price_anomaly"]
    )


def test_flagged_listing_with_low_sub_flags_has_no_scam_reason():
    batch = _evaluate([{"url": "u"}], lambda r: httpx.Response(200, json=_answers(0.85, "POSSIBLY_SCAM")))
    assert batch.results[0].verdict == "POSSIBLY_SCAM"
    assert batch.results[0].scam_reason is None


# ---------------------------------------------------------------------------
# Live probe used by `python -m backend.check_env` / `python -m backend.decision`
# ---------------------------------------------------------------------------
def _sync_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_probe_oumi_success(fake_oumi_env):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "projects/test-proj/models/iris-latest"
        assert request.headers["X-API-Key"] == "test-key"
        assert request.headers["Content-Type"].startswith("application/json")
        return httpx.Response(200, json={"answers": {"is_rental": {"type": "noul", "noul": 0.97}}})

    ok, detail = probe_oumi(client=_sync_client(handler))
    assert ok is True
    assert "0.97" in detail


def test_probe_oumi_reports_http_errors(fake_oumi_env):
    ok, detail = probe_oumi(client=_sync_client(lambda r: httpx.Response(403, text="forbidden")))
    assert ok is False
    assert "HTTP 403" in detail


def test_probe_oumi_without_config(no_oumi_env):
    assert probe_oumi() == (False, "OUMI_API_KEY / OUMI_PROJECT_ID not set")


# ---------------------------------------------------------------------------
# Search pipeline step (backend/agent.py `_scam_gate`)
# ---------------------------------------------------------------------------
def _gate(monkeypatch, fake_result=None, error: Optional[Exception] = None):
    def fake_eval(final, all_properties=None):
        if error:
            raise error
        return fake_result

    monkeypatch.setattr(decision, "evaluate_ranked_properties_sync", fake_eval)
    events: list[dict] = []
    props = [
        agent.PropertyDetails(
            url=f"https://example.com/{i}", price=600, sqm=60, floor="2", features=[], agent_name=None,
            agent_phone=None, agent_email=None, missing_info=[], agentic_score=9 - i, score_reason="",
            pros=[], cons=[], metrics=[],
        )
        for i in range(2)
    ]
    verdicts = agent._scam_gate(props, [], agent.StepReporter(events.append))
    return verdicts, events


def test_scam_gate_skips_when_not_configured(monkeypatch, no_oumi_env):
    verdicts, events = _gate(monkeypatch)
    assert verdicts == {}
    assert events[-1] == {"type": "step", "step": "scam", "status": "skipped",
                          "detail": "Skipped: decision model not configured"}


def test_scam_gate_survives_oumi_errors(monkeypatch, fake_oumi_env):
    verdicts, events = _gate(monkeypatch, error=httpx.ConnectTimeout("timeout"))
    assert verdicts == {}
    assert events[-1]["status"] == "skipped"
    assert any(e["type"] == "agent" and e["status"] == "failed" for e in events)


def test_scam_gate_returns_verdict_risk_and_reason(monkeypatch, fake_oumi_env):
    def handler(request: httpx.Request) -> httpx.Response:
        rank = json.loads(request.content)["state"]["initial_rank"]
        if rank == 1:
            return httpx.Response(200, json=_answers(0.9, "POSSIBLY_SCAM", advance_fee_lure=0.95))
        return httpx.Response(200, json=_answers(0.05, "SAFE"))

    batch = _evaluate([{"url": "https://example.com/0"}, {"url": "https://example.com/1"}], handler)
    verdicts, events = _gate(monkeypatch, fake_result=batch)
    assert verdicts == {
        "https://example.com/0": {
            "scam_verdict": "POSSIBLY_SCAM",
            "scam_risk_pct": 90,
            "scam_reason": RED_FLAG_LABELS["advance_fee_lure"],
        },
        "https://example.com/1": {"scam_verdict": "SAFE", "scam_risk_pct": 5, "scam_reason": None},
    }
    assert events[-1]["detail"] == "Flagged 1 possible scam"


def test_run_search_sinks_flagged_listing_to_bottom(monkeypatch, fake_oumi_env):
    bait_url = "https://www.spitogatos.gr/aggelia/bait"
    safe_url = "https://www.spitogatos.gr/aggelia/safe"

    def fake_generate(prompt, schema):
        if schema is agent.SearchURL:
            return agent.SearchURL(url="https://www.spitogatos.gr/enoikiaseis-katoikies/pagkrati?max_price=700")
        if schema is agent.AllProperties:
            return agent.AllProperties(
                properties=[
                    agent.PropertyPreview(url=bait_url, price=250, sqm=80, basic_info="Luxury cheap"),
                    agent.PropertyPreview(url=safe_url, price=620, sqm=60, basic_info="Bright flat"),
                ]
            )
        if schema is agent.PropertyList:
            return agent.PropertyList(links=[agent.PropertyLink(url=bait_url), agent.PropertyLink(url=safe_url)])
        if schema is agent.PropertyDetails:
            if bait_url in prompt or "250" in prompt:
                return agent.PropertyDetails(
                    url=bait_url, price=250, sqm=80, floor="3rd", features=["deposit"],
                    agent_name=None, agent_phone=None, agent_email=None, missing_info=[],
                    agentic_score=10, score_reason="Great price.", pros=[], cons=[], metrics=[],
                )
            return agent.PropertyDetails(
                url=safe_url, price=620, sqm=60, floor="2nd", features=["bright"],
                agent_name="Maria", agent_phone=None, agent_email="maria@example.gr", missing_info=[],
                agentic_score=8, score_reason="Good match.", pros=[], cons=[], metrics=[],
            )
        raise AssertionError(f"Unexpected schema {schema}")

    def fake_scrape(url, images=False):
        if "enoikiaseis" in url:
            return agent.ScrapedPage(markdown="# Results")
        if url == bait_url:
            return agent.ScrapedPage(markdown="Listing 250 EUR")
        return agent.ScrapedPage(markdown="Listing 620 EUR")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["state"]["property"]["url"] == bait_url:
            return httpx.Response(200, json=_answers(0.94, "POSSIBLY_SCAM", price_anomaly=0.96))
        return httpx.Response(200, json=_answers(0.05, "SAFE"))

    monkeypatch.setattr(agent, "_generate", fake_generate)
    monkeypatch.setattr(agent, "scrape_page", fake_scrape)
    monkeypatch.setattr(
        decision,
        "evaluate_ranked_properties_sync",
        lambda ranked, all_properties=None: _evaluate(ranked, handler, all_properties=all_properties),
    )

    outcome = agent.run_search("Bright flat in Pangrati")
    assert [p["url"] for p in outcome.properties] == [safe_url, bait_url]
    assert outcome.properties[0]["scam_verdict"] == "SAFE"
    assert outcome.properties[1]["scam_verdict"] == "POSSIBLY_SCAM"
    assert outcome.properties[1]["scam_reason"] == RED_FLAG_LABELS["price_anomaly"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_health_reports_oumi_status(monkeypatch, fake_oumi_env):
    assert TestClient(app).get("/api/health").json()["oumi_configured"] is True
    monkeypatch.delenv("OUMI_PROJECT_ID")
    assert TestClient(app).get("/api/health").json()["oumi_configured"] is False


def test_decision_endpoint_requires_config(no_oumi_env):
    resp = TestClient(app).post("/api/decision/evaluate", json={"properties": [{"url": "u"}]})
    assert resp.status_code == 503


def test_decision_endpoint_returns_compact_verdicts(monkeypatch, fake_oumi_env):
    from backend import main

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_answers(0.97, "POSSIBLY_SCAM", price_anomaly=0.99))

    async def fake_eval(properties, all_properties=None):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await evaluate_ranked_properties(properties, all_properties, client=client)

    monkeypatch.setattr(main, "evaluate_ranked_properties", fake_eval)
    resp = TestClient(app).post(
        "/api/decision/evaluate", json={"properties": [{"url": "u", "price": 200, "sqm": 90}]}
    )
    assert resp.status_code == 200
    assert resp.json() == [
        {"url": "u", "rank": 1, "scam_verdict": "POSSIBLY_SCAM", "scam_risk_pct": 97,
         "scam_reason": RED_FLAG_LABELS["price_anomaly"]}
    ]


def test_decision_endpoint_reports_upstream_failure(monkeypatch, fake_oumi_env):
    from backend import main

    async def boom(properties, all_properties=None):
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(main, "evaluate_ranked_properties", boom)
    resp = TestClient(app).post("/api/decision/evaluate", json={"properties": [{"url": "u"}]})
    assert resp.status_code == 502


def test_decision_endpoint_rejects_empty_list(fake_oumi_env):
    assert TestClient(app).post("/api/decision/evaluate", json={"properties": []}).status_code == 422


def test_decision_endpoint_forwards_cohort_and_openapi_valid(monkeypatch, fake_oumi_env):
    from backend import main

    seen_bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_answers(0.03, "SAFE"))

    async def fake_eval(properties, all_properties=None):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await evaluate_ranked_properties(properties, all_properties, client=client)

    monkeypatch.setattr(main, "evaluate_ranked_properties", fake_eval)
    resp = TestClient(app).post(
        "/api/decision/evaluate",
        json={
            "properties": [{"url": "u", "price": 600, "sqm": 60}],
            "cohort": [{"price": 800, "sqm": 40}, {"price": 600, "sqm": 60}],
        },
    )
    assert resp.status_code == 200
    assert seen_bodies[0]["state"]["price_signals"]["cohort_median_eur_per_sqm"] == 15.0
    schema = app.openapi()
    assert "/api/decision/evaluate" in schema["paths"]
    assert "/api/health" in schema["paths"]


# ---------------------------------------------------------------------------
# Live call against Oumi (opt-in: costs credits). Run with:  $env:OUMI_LIVE_TEST="1"; uv run pytest -k live_oumi
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    os.getenv("OUMI_LIVE_TEST") != "1" or not oumi_configured(),
    reason="set OUMI_LIVE_TEST=1 with OUMI_API_KEY and OUMI_PROJECT_ID to call the real Oumi Iris",
)
def test_live_oumi_flags_bait_and_passes_normal_listing():
    cohort = [{"price": p, "sqm": s} for p, s in [(600, 60), (650, 65), (700, 70), (580, 55)]]
    bait = {
        "url": "https://example.gr/bait", "price": 250, "sqm": 90, "agentic_score": 10,
        "features": ["Owner abroad, keys sent by courier after deposit via Airbnb"],
        "agent_email": "john.rentals.gr@gmail.com", "missing_info": ["Exact address", "Viewing availability"],
    }
    normal = {
        "url": "https://example.gr/legit", "price": 620, "sqm": 62, "agentic_score": 8,
        "features": ["Balcony", "Pet friendly", "Viewing by appointment"],
        "agent_name": "Pangrati Homes", "agent_phone": None, "agent_email": None,
        "missing_info": ["Are pets allowed?", "What are the monthly building fees?"],
        "cons": ["Pet policy not stated", "No direct phone listed"],
    }
    batch = decision.evaluate_ranked_properties_sync([bait, normal], all_properties=cohort + [bait, normal])
    by_url = {d.url: d for d in batch.results}
    assert by_url[bait["url"]].verdict == "POSSIBLY_SCAM"
    assert by_url[bait["url"]].scam_reason
    assert by_url[normal["url"]].verdict == "SAFE"
    assert by_url[normal["url"]].scam_risk_pct < 25
    assert batch.intercepted_top_match is True
