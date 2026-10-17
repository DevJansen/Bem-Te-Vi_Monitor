"""Rota do clima atual do local do alimentador (integração Open-Meteo)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.domain.models import CurrentWeatherOut, GeoLocationOut
from app.services.camera_weather import geocode_location
from app.services.weather_service import get_weather_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/geocode", response_model=list[GeoLocationOut])
def geocode_city(
    q: str = Query(
        min_length=2,
        max_length=120,
        description="Cidade/país para localizar (ex.: 'San José, Costa Rica').",
    ),
) -> list[GeoLocationOut]:
    """Seletor de cidade inteligente: nome → coordenadas + fuso horário (IANA).

    Alimenta o cadastro de câmeras globais/remotas. Nunca falha por ausência de
    resultados: devolve uma lista vazia quando nada é encontrado.
    """
    try:
        resultados = geocode_location(q)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.exception("geocode_city failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível buscar a localidade.",
        ) from exc

    return [
        GeoLocationOut(
            name=item.name,
            country=item.country,
            admin1=item.admin1,
            latitude=item.latitude,
            longitude=item.longitude,
            timezone=item.timezone,
            label=item.label,
        )
        for item in resultados
    ]


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
