"""Habit analytics and bird life-list routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.domain.models import (
    AnalyticsSummaryOut,
    HourlyDistributionOut,
    LifeListSpeciesOut,
)
from app.infra.database.analytics_repository import AnalyticsRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _repository() -> AnalyticsRepository:
    return AnalyticsRepository(get_settings().db_path)


@router.get("/summary", response_model=AnalyticsSummaryOut)
def get_analytics_summary() -> AnalyticsSummaryOut:
    try:
        return AnalyticsSummaryOut(**_repository().summary())
    except Exception as exc:
        logger.exception("get_analytics_summary failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular as estatísticas.",
        ) from exc


@router.get(
    "/hourly-distribution",
    response_model=list[HourlyDistributionOut],
)
def get_hourly_distribution() -> list[HourlyDistributionOut]:
    try:
        return [
            HourlyDistributionOut(**row)
            for row in _repository().hourly_distribution()
        ]
    except Exception as exc:
        logger.exception("get_hourly_distribution failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar a distribuição por horário.",
        ) from exc


@router.get("/lifelist", response_model=list[LifeListSpeciesOut])
def get_lifelist() -> list[LifeListSpeciesOut]:
    try:
        return [
            LifeListSpeciesOut(**row)
            for row in _repository().lifelist()
        ]
    except Exception as exc:
        logger.exception("get_lifelist failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar o álbum de espécies.",
        ) from exc
