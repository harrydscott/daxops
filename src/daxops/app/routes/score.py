"""GET /api/score — AI readiness scoring."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from daxops.app.state import app_state

router = APIRouter()


class CriterionDetail(BaseModel):
    name: str
    score: int
    max_score: int
    details: list[str]


class ScoreSummary(BaseModel):
    bronze_score: int
    silver_score: int
    gold_score: int
    bronze_pass: bool
    silver_pass: bool
    gold_pass: bool
    tier: str  # "gold", "silver", "bronze", "none"
    thresholds: dict[str, int]


class ScoreResponse(BaseModel):
    bronze: list[CriterionDetail]
    silver: list[CriterionDetail]
    gold: list[CriterionDetail]
    summary: ScoreSummary


@router.get("/score", response_model=ScoreResponse)
def get_score() -> ScoreResponse:
    """Return full scoring result."""
    if not app_state.model_path:
        raise HTTPException(status_code=400, detail="No model path configured")
    model = app_state.ensure_model()
    config = app_state.config

    from daxops.scoring import score_bronze, score_silver, score_gold

    bronze = score_bronze(model)
    silver = score_silver(model)
    gold = score_gold(model)

    b = sum(c.score for c in bronze)
    s = sum(c.score for c in silver)
    g = sum(c.score for c in gold)

    bronze_pass = b >= config.score.bronze_min
    silver_pass = bronze_pass and s >= config.score.silver_min
    gold_pass = silver_pass and g >= config.score.gold_min

    if gold_pass:
        tier = "gold"
    elif silver_pass:
        tier = "silver"
    elif bronze_pass:
        tier = "bronze"
    else:
        tier = "none"

    def _to_details(criteria):
        return [
            CriterionDetail(name=c.name, score=c.score, max_score=c.max_score, details=c.details)
            for c in criteria
        ]

    return ScoreResponse(
        bronze=_to_details(bronze),
        silver=_to_details(silver),
        gold=_to_details(gold),
        summary=ScoreSummary(
            bronze_score=b,
            silver_score=s,
            gold_score=g,
            bronze_pass=bronze_pass,
            silver_pass=silver_pass,
            gold_pass=gold_pass,
            tier=tier,
            thresholds={
                "bronze_min": config.score.bronze_min,
                "silver_min": config.score.silver_min,
                "gold_min": config.score.gold_min,
            },
        ),
    )
