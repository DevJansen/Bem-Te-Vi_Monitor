"""Previsão horária da Open-Meteo para os jardins do Bem-Te-Vi.

O ``weather_service`` (alimentador local) e o ``camera_weather`` (câmeras
globais) cuidam do **agora**. Este módulo olha para frente: devolve as próximas
horas de cada jardim — chuva, probabilidade, vento e temperatura — para o
Alaris Core antecipar a atividade das aves.

Como as demais integrações meteorológicas do projeto:

* usa apenas APIs públicas e gratuitas da Open-Meteo (sem chave);
* mantém cache em memória por coordenada (evita requisições repetidas);
* é tolerante a falhas: sem internet devolve ``None`` e o painel apenas oculta
  a previsão, sem interromper a captura.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from app.core.config import get_settings
from app.services.weather_service import (
    CATEGORY_RAIN,
    CATEGORY_STORM,
    weather_category,
    wmo_icon,
    wmo_label,
)

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_FIELDS = (
    "temperature_2m,precipitation,precipitation_probability,"
    "weather_code,wind_speed_10m"
)
_MAX_CACHE_ENTRIES = 96


@dataclass(frozen=True)
class HourForecast:
    """Uma hora da previsão, já convertida para tipos simples."""

    time: str
    temperature: float | None
    precipitation: float
    probability: int
    code: int | None
    wind_speed: float | None


@dataclass(frozen=True)
class ForecastWindow:
    """Janela de previsão pronta para a interface e para os insights."""

    available: bool
    rain_expected: bool
    # Quantas horas faltam para a primeira chuva (0 = já chovendo agora).
    rain_in_hours: int | None
    peak_probability: int
    precipitation_mm: float
    condition: str
    icon: str
    category: str
    min_temperature: float | None
    max_temperature: float | None
    max_wind_kmh: float | None
    hours: tuple[HourForecast, ...]
    fetched_at: str
    # Condições observadas agora (vêm na mesma chamada, sem custo extra).
    current_temperature: float | None = None
    current_humidity: float | None = None
    current_wind_speed: float | None = None
    current_code: int | None = None
    current_is_day: bool | None = None
    source: str = "open-meteo"

    @property
    def current_payload(self) -> dict[str, Any]:
        """Formato pronto para o card de alimentação (``current`` aninhado)."""
        return {
            "temperature": self.current_temperature,
            "humidity": self.current_humidity,
            "wind_speed": self.current_wind_speed,
            "condition": wmo_label(self.current_code),
            "icon": wmo_icon(self.current_code),
            "is_day": self.current_is_day,
            "local_time_label": None,
        }


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _is_rainy(code: int | None, precipitation: float, probability: int) -> bool:
    """Considera "chuva" códigos WMO de chuva/tempestade ou sinais objetivos."""
    category = weather_category(code)
    if category in (CATEGORY_RAIN, CATEGORY_STORM):
        return True
    return precipitation >= 0.4 or probability >= 55


class WeatherForecastService:
    """Cliente da previsão horária com cache por localização."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[ForecastWindow, float]] = {}
        # Um lock por localização: jardins diferentes podem buscar em paralelo
        # sem "estampede" de requisições para a mesma coordenada.
        self._fetch_locks: dict[str, threading.Lock] = {}

    def next_hours(
        self,
        latitude: float,
        longitude: float,
        *,
        timezone_name: str | None = None,
        hours: int = 12,
        force: bool = False,
    ) -> ForecastWindow | None:
        """Próximas ``hours`` horas do jardim (ou ``None`` se a rede falhar).

        Nunca levanta exceção para o chamador: em falha devolve a última
        previsão conhecida (mesmo expirada), se existir.
        """
        hours = max(3, min(int(hours), 24))
        key = f"{round(float(latitude), 4)},{round(float(longitude), 4)}:{hours}"
        settings = get_settings()
        ttl_seconds = max(300.0, float(settings.weather_cache_minutes) * 60.0)
        now = time.monotonic()

        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and not force:
                window, stored_at = cached
                if (now - stored_at) < ttl_seconds:
                    return window

        with self._lock:
            key_lock = self._fetch_locks.setdefault(key, threading.Lock())
        if not key_lock.acquire(blocking=False):
            with self._lock:
                cached = self._cache.get(key)
                return cached[0] if cached else None

        try:
            fetched = self._fetch(latitude, longitude, timezone_name, hours)
        finally:
            key_lock.release()

        if fetched is None:
            with self._lock:
                cached = self._cache.get(key)
                return cached[0] if cached else None

        with self._lock:
            self._cache[key] = (fetched, time.monotonic())
            if len(self._cache) > _MAX_CACHE_ENTRIES:
                oldest = min(self._cache, key=lambda k: self._cache[k][1])
                self._cache.pop(oldest, None)
        return fetched

    def _fetch(
        self,
        latitude: float,
        longitude: float,
        timezone_name: str | None,
        hours: int,
    ) -> ForecastWindow | None:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": HOURLY_FIELDS,
            "current": (
                "temperature_2m,relative_humidity_2m,weather_code,"
                "wind_speed_10m,is_day"
            ),
            "forecast_hours": hours,
            "wind_speed_unit": "kmh",
            "timezone": timezone_name or "auto",
        }
        try:
            response = requests.get(FORECAST_URL, params=params, timeout=(3, 8))
            response.raise_for_status()
            payload = response.json()
            hourly = payload.get("hourly") or {}
            times = hourly.get("time") or []
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning(
                "Falha ao consultar a previsão da Open-Meteo (%.3f, %.3f): %s",
                latitude,
                longitude,
                exc,
            )
            return None

        current_raw = payload.get("current") or {}
        current_code = _as_int(current_raw.get("weather_code"))
        current_is_day_raw = current_raw.get("is_day")
        current_is_day = (
            bool(_as_int(current_is_day_raw))
            if current_is_day_raw is not None
            else None
        )
        current_fields = {
            "current_temperature": _as_float(current_raw.get("temperature_2m")),
            "current_humidity": _as_float(current_raw.get("relative_humidity_2m")),
            "current_wind_speed": _as_float(current_raw.get("wind_speed_10m")),
            "current_code": current_code,
            "current_is_day": current_is_day,
        }

        if not times:
            return ForecastWindow(
                available=False,
                rain_expected=False,
                rain_in_hours=None,
                peak_probability=0,
                precipitation_mm=0.0,
                condition="Sem dados",
                icon="🌡️",
                category="Sem dados",
                min_temperature=None,
                max_temperature=None,
                max_wind_kmh=None,
                hours=(),
                fetched_at=datetime.now(timezone.utc).isoformat(),
                **current_fields,
            )

        temperatures = hourly.get("temperature_2m") or []
        precipitations = hourly.get("precipitation") or []
        probabilities = hourly.get("precipitation_probability") or []
        codes = hourly.get("weather_code") or []
        winds = hourly.get("wind_speed_10m") or []
        current_time = str((payload.get("current") or {}).get("time") or "")

        # ``forecast_hours`` já começa na hora atual; o fallback abaixo cobre
        # versões da API que devolvem o dia inteiro.
        start = 0
        if current_time:
            prefix = current_time[:13]
            for index, value in enumerate(times):
                if str(value)[:13] >= prefix:
                    start = index
                    break

        window: list[HourForecast] = []
        for offset in range(start, min(len(times), start + hours)):
            window.append(
                HourForecast(
                    time=str(times[offset]),
                    temperature=_as_float(
                        temperatures[offset] if offset < len(temperatures) else None
                    ),
                    precipitation=_as_float(
                        precipitations[offset] if offset < len(precipitations) else 0.0
                    )
                    or 0.0,
                    probability=_as_int(
                        probabilities[offset] if offset < len(probabilities) else 0
                    )
                    or 0,
                    code=_as_int(codes[offset] if offset < len(codes) else None),
                    wind_speed=_as_float(
                        winds[offset] if offset < len(winds) else None
                    ),
                )
            )

        if not window:
            return None

        rain_index: int | None = None
        for index, hour in enumerate(window):
            if _is_rainy(hour.code, hour.precipitation, hour.probability):
                rain_index = index
                break

        near = window[:6]
        peak_probability = max((hour.probability for hour in near), default=0)
        precip_total = round(sum(hour.precipitation for hour in window), 1)
        temps = [hour.temperature for hour in window if hour.temperature is not None]
        winds = [hour.wind_speed for hour in window if hour.wind_speed is not None]

        reference = window[rain_index] if rain_index is not None else window[0]
        condition = wmo_label(reference.code)
        category = weather_category(reference.code)

        return ForecastWindow(
            available=True,
            rain_expected=rain_index is not None,
            rain_in_hours=rain_index,
            peak_probability=peak_probability,
            precipitation_mm=precip_total,
            condition=condition,
            icon=wmo_icon(reference.code),
            category=category,
            min_temperature=min(temps) if temps else None,
            max_temperature=max(temps) if temps else None,
            max_wind_kmh=max(winds) if winds else None,
            hours=tuple(window),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            **current_fields,
        )


_service: WeatherForecastService | None = None
_service_lock = threading.Lock()


def get_weather_forecast_service() -> WeatherForecastService:
    """Instância única (processo) do serviço de previsão."""
    global _service
    with _service_lock:
        if _service is None:
            _service = WeatherForecastService()
        return _service
