"""Habit analytics and bird life-list routes."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.domain.models import (
    AchievementOut,
    AnalyticsSummaryOut,
    HourlyDistributionOut,
    LifeListSpeciesOut,
    TimelapseGenerateRequest,
    TimelapseGenerateResult,
    TimelapseOut,
    TodayByGardenOut,
    WeatherCorrelationOut,
    WeatherInsightsOut,
)
from app.infra.database.analytics_repository import AnalyticsRepository
from app.services.timelapse_service import get_timelapse_service
from app.services.weather_insights import build_weather_insights

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


@router.get("/today", response_model=TodayByGardenOut)
def get_analytics_today() -> TodayByGardenOut:
    """Visitas de hoje consolidadas e segmentadas por jardim (câmera)."""
    try:
        return TodayByGardenOut(**_repository().today_by_garden())
    except Exception as exc:
        logger.exception("get_analytics_today failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular as visitas de hoje por jardim.",
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


@router.get("/achievements", response_model=list[AchievementOut])
def get_achievements() -> list[AchievementOut]:
    """Medalhas/marcos conquistados pelo observador."""
    try:
        return [
            AchievementOut(**row) for row in _repository().achievements()
        ]
    except Exception as exc:
        logger.exception("get_achievements failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar as conquistas.",
        ) from exc


@router.get("/weather-correlation", response_model=WeatherCorrelationOut)
def get_weather_correlation() -> WeatherCorrelationOut:
    """Cruza a frequência de visitas com as condições do tempo."""
    try:
        return WeatherCorrelationOut(**_repository().weather_correlation())
    except Exception as exc:
        logger.exception("get_weather_correlation failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular a correlação climática.",
        ) from exc


@router.get("/weather-insights", response_model=WeatherInsightsOut)
def get_weather_insights() -> WeatherInsightsOut:
    """Insights avançados cruzando clima e hábitos das aves.

    Combina temperatura, umidade e condição do tempo com o horário e a espécie
    de cada visita para produzir faixas de temperatura, chuva x tempo seco,
    horário médio no frio x no calor e cards de resumo inteligente.
    """
    repository = _repository()
    try:
        rows = repository.weather_visit_rows()
        total = repository.total_visits()
        return WeatherInsightsOut(
            **build_weather_insights(rows, total_visits=total)
        )
    except Exception as exc:
        logger.exception("get_weather_insights failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular os insights de clima.",
        ) from exc


@router.get("/timelapses", response_model=list[TimelapseOut])
def list_timelapses() -> list[TimelapseOut]:
    """Resumos do dia (time-lapses) já gerados, do mais recente ao mais antigo."""
    try:
        return [
            TimelapseOut(**item) for item in get_timelapse_service().list()
        ]
    except Exception as exc:
        logger.exception("list_timelapses failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível listar os resumos do dia.",
        ) from exc


@router.post("/timelapses/generate", response_model=TimelapseGenerateResult)
def generate_timelapse(
    payload: TimelapseGenerateRequest,
) -> TimelapseGenerateResult:
    """Gera (sob demanda) o resumo de um dia a partir dos clipes gravados.

    Quando ``day`` não é informado, usa o dia atual. O campo ``force`` permite
    regerar um resumo que já existe.
    """
    if payload.day:
        try:
            day: date | None = date.fromisoformat(payload.day)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Data inválida. Use o formato AAAA-MM-DD.",
            ) from exc
    else:
        day = None

    try:
        result = get_timelapse_service().generate(day, force=payload.force)
    except Exception as exc:
        logger.exception("generate_timelapse failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível gerar o resumo do dia.",
        ) from exc

    timelapse = result.get("timelapse")
    return TimelapseGenerateResult(
        status=result["status"],
        message=result["message"],
        timelapse=TimelapseOut(**timelapse) if timelapse else None,
    )


@router.delete("/timelapses/{filename}")
def delete_timelapse(filename: str) -> dict[str, bool]:
    """Remove um resumo do dia pelo nome do arquivo."""
    try:
        removed = get_timelapse_service().delete(filename)
    except Exception as exc:
        logger.exception("delete_timelapse failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível remover o resumo do dia.",
        ) from exc
    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Resumo do dia não encontrado.",
        )
    return {"ok": True}
