"""Rota do clima atual do local do alimentador (integração Open-Meteo)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.domain.models import CurrentWeatherOut
from app.services.weather_service import get_weather_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/current", response_model=CurrentWeatherOut)
def get_current_weather() -> CurrentWeatherOut:
    """Devolve o clima atual (temperatura, umidade, condição e vento).

    É resiliente a falhas de internet: quando não há conexão nem cache, devolve
    ``available=False`` em vez de erro, para que o widget do painel apenas se
    oculte sem quebrar a interface.
    """
    try:
        snapshot = get_weather_service().current()
    except Exception as exc:  # pragma: no cover - defensivo
        logger.exception("get_current_weather failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível consultar o clima atual.",
        ) from exc

    if snapshot is None:
        return CurrentWeatherOut(available=False)

    return CurrentWeatherOut(
        available=snapshot.available,
        temperature=snapshot.temperature,
        humidity=snapshot.humidity,
        wind_speed=snapshot.wind_speed,
        condition=snapshot.condition,
        category=snapshot.category,
        icon=snapshot.icon,
        weather_code=snapshot.code,
        fetched_at=snapshot.fetched_at,
        source=snapshot.source,
    )
