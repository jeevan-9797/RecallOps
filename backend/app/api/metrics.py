"""
Metrics API Router.
Handles GET /api/metrics/learning-curve returning provable learning curve numbers for judges and frontend.
Loads canonical evaluation deliverables directly from eval/chart_data.json and eval/headline_metrics.json.
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from backend.app.schemas.api_models import (
    LearningCurveMetricsResponse,
    LearningCurvePoint,
    LearningCurveStats,
)

logger = logging.getLogger("recallops.metrics")

router = APIRouter(prefix="/metrics", tags=["Metrics"])

def _find_eval_dir() -> Path:
    """Locates the evaluation directory containing canonical benchmark artifacts."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        candidate = parent / "eval"
        if candidate.is_dir() and (candidate / "chart_data.json").exists():
            return candidate
    return Path(__file__).resolve().parents[3] / "eval"


EVAL_DIR = _find_eval_dir()
DEFAULT_CHART_DATA_PATH = EVAL_DIR / "chart_data.json"
DEFAULT_HEADLINE_METRICS_PATH = EVAL_DIR / "headline_metrics.json"


def load_learning_curve_metrics(
    chart_path: Optional[Path] = None,
    headline_path: Optional[Path] = None,
) -> LearningCurveMetricsResponse:
    """
    Loads and transforms canonical evaluation replay deliverables into
    the dual-compatible LearningCurveMetricsResponse payload.

    Args:
        chart_path: Optional override for chart_data.json path.
        headline_path: Optional override for headline_metrics.json path.

    Returns:
        LearningCurveMetricsResponse conforming to frontend LearningCurve and backend API.

    Raises:
        HTTPException(503): If metrics files are missing on disk.
        HTTPException(500): If metrics files contain malformed JSON or invalid schema.
    """
    chart_file = chart_path or DEFAULT_CHART_DATA_PATH
    headline_file = headline_path or DEFAULT_HEADLINE_METRICS_PATH

    # 1. Verify existence
    if not chart_file.exists():
        logger.error(f"Replay chart data file not found: {chart_file}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Replay chart metrics unavailable: {chart_file.name} not found on disk.",
        )

    if not headline_file.exists():
        logger.error(f"Replay headline metrics file not found: {headline_file}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Replay headline metrics unavailable: {headline_file.name} not found on disk.",
        )

    # 2. Parse JSON
    try:
        with open(chart_file, "r", encoding="utf-8") as f:
            chart_raw = json.load(f)
    except json.JSONDecodeError as err:
        logger.error(f"Malformed JSON in {chart_file}: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Malformed chart metrics JSON in {chart_file.name}: {err.msg}",
        )

    try:
        with open(headline_file, "r", encoding="utf-8") as f:
            headline_raw = json.load(f)
    except json.JSONDecodeError as err:
        logger.error(f"Malformed JSON in {headline_file}: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Malformed headline metrics JSON in {headline_file.name}: {err.msg}",
        )

    # 3. Validate structure and extract metrics
    if not isinstance(chart_raw, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid chart metrics structure in {chart_file.name}: expected list of point records.",
        )

    try:
        h1 = headline_raw["headline_1_accuracy"]
        h2 = headline_raw["headline_2_mttr"]
        h3 = headline_raw["headline_3_anti_patterns"]

        top1_on = round(float(str(h1["stat"]).replace("%", "").strip()) / 100.0, 4)
        top1_off = round(float(str(h1["baseline"]).replace("%", "").strip()) / 100.0, 4)

        avg_mttr_on_min = float(str(h2["stat"]).replace("min", "").strip())
        avg_mttr_off_min = float(str(h2["baseline"]).replace("min", "").strip())

        violations_on = int(h3["violations_memory_on"])
        violations_off = int(h3.get("violations_memory_off", 0))
        avoidance_rate = round(float(str(h3["stat"]).replace("%", "").strip()) / 100.0, 4)
    except (KeyError, ValueError, TypeError) as err:
        logger.error(f"Error parsing headline metrics in {headline_file}: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid schema or data format in {headline_file.name}: {err}",
        )

    # 4. Map chart points
    points: List[LearningCurvePoint] = []
    try:
        for idx, item in enumerate(chart_raw, start=1):
            n = int(item.get("incident_num") or item.get("n", idx))
            on_val = float(item.get("memory_on_accuracy") if "memory_on_accuracy" in item else item.get("on", 0.0))
            off_val = float(item.get("memory_off_accuracy") if "memory_off_accuracy" in item else item.get("off", 0.0))
            points.append(
                LearningCurvePoint(
                    n=n,
                    on=on_val,
                    off=off_val,
                    incident_id=item.get("incident_id"),
                    service_name=item.get("service_name"),
                )
            )
    except (ValueError, TypeError) as err:
        logger.error(f"Error mapping chart points in {chart_file}: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Invalid point data format in {chart_file.name}: {err}",
        )

    stats = LearningCurveStats(
        top1_on=top1_on,
        top1_off=top1_off,
        repeated_failed_fixes_on=violations_on,
        repeated_failed_fixes_off=violations_off,
        avg_mttr_on_min=avg_mttr_on_min,
        avg_mttr_off_min=avg_mttr_off_min,
    )

    return LearningCurveMetricsResponse(
        points=points,
        stats=stats,
        sample=False,
        total_incidents_replayed=len(points),
        accuracy_memory_off=top1_off,
        accuracy_memory_on=top1_on,
        avg_mttr_memory_off_min=avg_mttr_off_min,
        avg_mttr_memory_on_min=avg_mttr_on_min,
        negative_fix_avoidance_rate=avoidance_rate,
        benchmark_status="phase3_replay_benchmark",
    )


def get_learning_curve_data() -> LearningCurveMetricsResponse:
    """Dependency provider returning the loaded LearningCurveMetricsResponse."""
    return load_learning_curve_metrics()


@router.get(
    "/learning-curve",
    response_model=LearningCurveMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Replay Benchmark Learning Curve Metrics",
)
async def get_learning_curve_metrics(
    data: LearningCurveMetricsResponse = Depends(get_learning_curve_data),
) -> LearningCurveMetricsResponse:
    """
    Returns provable evaluation benchmark metrics comparing agent triage performance
    with Hindsight memory disabled vs enabled across the 40 held-out historical incidents.
    Loads canonical metrics directly from eval/chart_data.json and eval/headline_metrics.json.
    """
    return data
