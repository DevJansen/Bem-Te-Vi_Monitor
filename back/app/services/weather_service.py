"""Integração meteorológica com a API pública Open-Meteo.

A Open-Meteo é gratuita e não exige chave de API. Este serviço:

* consulta o clima atual na latitude/longitude configuradas no ``.env``;
* mantém um cache local em memória (padrão: 30 minutos) para evitar
  requisições excessivas;
* é resiliente a falhas de internet: nunca levanta exceção para o chamador,
  devolvendo o último instantâneo conhecido (mesmo expirado) ou ``None``.

O módulo também converte os códigos WMO da Open-Meteo em rótulos, ícones e
categorias amplas em Português do Brasil, usados pela persistência das visitas
e pelo endpoint de correlação climática.
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

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
)

# Códigos WMO (padrão usado pela Open-Meteo) → rótulo curto em pt-BR.
_WMO_LABELS: dict[int, str] = {
    0: "Ensolarado",
    1: "Predomínio de sol",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Nevoeiro",
    48: "Nevoeiro com geada",
    51: "Chuvisco leve",
    53: "Chuvisco",
    55: "Chuvisco forte",
    56: "Chuvisco congelante",
    57: "Chuvisco congelante forte",
    61: "Chuva leve",
    63: "Chuva",
    65: "Chuva forte",
    66: "Chuva congelante",
    67: "Chuva congelante forte",
    71: "Neve leve",
    73: "Neve",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Pancadas de chuva",
    81: "Pancadas de chuva moderadas",
    82: "Pancadas de chuva fortes",
    85: "Pancadas de neve",
    86: "Pancadas de neve fortes",
    95: "Tempestade",
    96: "Tempestade com granizo",
    99: "Tempestade com granizo forte",
}

# Emoji correspondente a cada código WMO (usado como ícone no front-end).
_WMO_ICONS: dict[int, str] = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌦️",
    55: "🌦️",
    56: "🌧️",
    57: "🌧️",
    61: "🌧️",
    63: "🌧️",
    65: "🌧️",
    66: "🌧️",
    67: "🌧️",
    71: "🌨️",
    73: "🌨️",
    75: "❄️",
    77: "❄️",
    80: "🌦️",
    81: "🌧️",
    82: "⛈️",
    85: "🌨️",
    86: "🌨️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}

# Categorias amplas usadas para agrupar visitas na correlação climática.
CATEGORY_SUNNY = "Ensolarado"
CATEGORY_CLOUDY = "Nublado"
CATEGORY_RAIN = "Chuva"
CATEGORY_SNOW = "Neve"
CATEGORY_STORM = "Tempestade"
CATEGORY_FOG = "Nevoeiro"
CATEGORY_OTHER = "Outros"
CATEGORY_UNKNOWN = "Sem dados"


def weather_category(code: int | None) -> str:
    """Agrupa um código WMO em uma categoria ampla em pt-BR."""
    if code is None:
        return CATEGORY_UNKNOWN
    if code in (0, 1):
        return CATEGORY_SUNNY
    if code in (2, 3):
        return CATEGORY_CLOUDY
    if code in (45, 48):
        return CATEGORY_FOG
    if 51 <= code <= 67 or 80 <= code <= 82:
        return CATEGORY_RAIN
    if 71 <= code <= 77 or code in (85, 86):
        return CATEGORY_SNOW
    if 95 <= code <= 99:
        return CATEGORY_STORM
    return CATEGORY_OTHER


def wmo_label(code: int | None) -> str:
    """Rótulo legível em pt-BR para um código WMO (ex.: 61 → "Chuva leve")."""
    if code is None:
        return "Sem dados"
    return _WMO_LABELS.get(code, "Condição desconhecida")


def wmo_icon(code: int | None) -> str:
    """Emoji do céu para um código WMO (ex.: 0 → ☀️)."""
    if code is None:
        return "🌡️"
    return _WMO_ICONS.get(code, "🌡️")


# Categoria a partir do rótulo persistido (o rótulo é o que vai para o SQLite).
_LABEL_CATEGORY: dict[str, str] = {
    label: weather_category(code) for code, label in _WMO_LABELS.items()
}


def category_for_label(label: str | None) -> str:
    """Devolve a categoria ampla a partir do rótulo persistido na visita."""
    if not label:
        return CATEGORY_UNKNOWN
    return _LABEL_CATEGORY.get(label, CATEGORY_OTHER)


@dataclass(frozen=True)
class WeatherSnapshot:
    """Instantâneo do clima atual do local do alimentador."""

    temperature: float | None
    humidity: float | None
    # Código WMO bruto (ex.: 61) — útil para depuração e ícone.
    code: int | None
    # Rótulo legível em pt-BR persistido na coluna ``weather_code`` das visitas.
    condition: str
    category: str
    icon: str
    wind_speed: float | None
    fetched_at: str
    source: str
    available: bool

    def as_storage_fields(self) -> dict[str, float | str | None]:
        """Campos prontos para gravar junto a uma visita/detecção."""
        return {
            "temperature": self.temperature,
            "humidity": self.humidity,
            "weather_code": self.condition,
            "wind_speed": self.wind_speed,
        }


class WeatherService:
    """Cliente Open-Meteo com cache local e tolerância a falhas."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: WeatherSnapshot | None = None
        self._stored_monotonic: float = 0.0
        # Garante que apenas um thread faça a requisição HTTP por vez.
        self._fetch_lock = threading.Lock()

    def current(self, *, force: bool = False) -> WeatherSnapshot | None:
        """Devolve o clima atual, usando o cache quando ainda estiver válido.

        Nunca levanta exceção. Em caso de falha de conexão devolve o último
        valor conhecido (possivelmente expirado) ou ``None``.
        """
        settings = get_settings()
        ttl_seconds = max(60.0, float(settings.weather_cache_minutes) * 60.0)
        now = time.monotonic()

        with self._lock:
            cached = self._snapshot
            is_fresh = (
                cached is not None
                and (now - self._stored_monotonic) < ttl_seconds
            )
            if is_fresh and not force:
                return cached

        # Evita "estampede": se outro thread já está buscando, devolve o que
        # houver em cache sem bloquear o chamador (ex.: thread do pipeline).
        if not self._fetch_lock.acquire(blocking=False):
            with self._lock:
                return self._snapshot

        try:
            fetched = self._fetch(settings)
        finally:
            self._fetch_lock.release()

        if fetched is None:
            # Falha de conexão: mantém o último instantâneo conhecido.
            with self._lock:
                return self._snapshot

        with self._lock:
            self._snapshot = fetched
            self._stored_monotonic = time.monotonic()
        return fetched

    def _fetch(self, settings: Any) -> WeatherSnapshot | None:
        params = {
            "latitude": settings.latitude,
            "longitude": settings.longitude,
            "current": CURRENT_FIELDS,
            "wind_speed_unit": "kmh",
            "timezone": "auto",
        }
        try:
            response = requests.get(OPEN_METEO_URL, params=params, timeout=(3, 6))
            response.raise_for_status()
            payload = response.json()
            current = payload["current"]
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            logger.warning("Falha ao consultar a Open-Meteo: %s", exc)
            return None

        code_value = current.get("weather_code")
        try:
            code = int(code_value) if code_value is not None else None
        except (TypeError, ValueError):
            code = None

        condition = wmo_label(code)
        return WeatherSnapshot(
            temperature=_as_float(current.get("temperature_2m")),
            humidity=_as_float(current.get("relative_humidity_2m")),
            code=code,
            condition=condition,
            category=weather_category(code),
            icon=wmo_icon(code),
            wind_speed=_as_float(current.get("wind_speed_10m")),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            source="open-meteo",
            available=code is not None,
        )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_service: WeatherService | None = None
_service_lock = threading.Lock()


def get_weather_service() -> WeatherService:
    """Devolve a instância única (singleton) do serviço de clima."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = WeatherService()
    return _service


def current_weather_for_storage() -> dict[str, float | str | None]:
    """Campos de clima atuais prontos para gravar em uma visita/detecção.

    Devolve ``{}`` quando o clima está indisponível, permitindo que os campos
    fiquem nulos sem interromper o registro da visita.
    """
    snapshot = get_weather_service().current()
    if snapshot is None or not snapshot.available:
        return {}
    return snapshot.as_storage_fields()
