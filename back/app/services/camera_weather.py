"""Clima e horário locais de câmeras globais/remotas (Open-Meteo).

Enquanto o ``weather_service`` cuida apenas do **alimentador local** configurado
no ``.env``, este módulo atende **qualquer** câmera com coordenadas: cada jardim
espalhado pelo mundo tem o seu próprio clima e o seu próprio relógio.

Três responsabilidades, todas baseadas em APIs públicas e gratuitas da Open-Meteo
(sem chave de API):

* :func:`geocode_location` — resolve um nome de cidade/país em coordenadas e no
  fuso horário IANA (o "seletor de cidade inteligente" do cadastro de câmeras);
* :class:`CameraWeatherService` — busca temperatura, condição do tempo, vento,
  se é dia/noite e a **hora local exata** do jardim, com cache por localização e
  tolerância total a falhas de internet;
* :func:`local_time_fields` — converte um instante UTC para (hora, data) no fuso
  da câmera. É o que permite ao **Alaris Core** corrigir os gráficos de horário
  de pico de câmeras em fusos diferentes (evita "visitas de madrugada" no Brasil
  quando, na verdade, eram 10h da manhã no jardim remoto).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from app.core.config import get_settings
from app.services.weather_service import weather_category, wmo_icon, wmo_label

logger = logging.getLogger(__name__)

# Geocodificação (nome → coordenadas/fuso) e previsão (clima + hora local).
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,is_day"
)
# Limite defensivo para o tamanho do cache de localizações (LRU simples).
_MAX_CACHE_ENTRIES = 128


@dataclass(frozen=True)
class GeoLocation:
    """Localidade resolvida pelo geocodificador da Open-Meteo."""

    name: str
    country: str | None
    admin1: str | None
    latitude: float
    longitude: float
    timezone: str | None

    @property
    def label(self) -> str:
        """Rótulo amigável: "Cidade, Estado, País" (partes vazias omitidas)."""
        partes = [self.name, self.admin1, self.country]
        return ", ".join(parte for parte in partes if parte)


@dataclass(frozen=True)
class CameraWeatherSnapshot:
    """Instantâneo do clima **e do relógio local** de uma câmera remota."""

    temperature: float | None
    humidity: float | None
    code: int | None
    condition: str
    category: str
    icon: str
    wind_speed: float | None
    # Se é dia (True) ou noite (False) no jardim, segundo a Open-Meteo.
    is_day: bool | None
    timezone: str | None
    utc_offset_seconds: int | None
    # Hora local do jardim (ISO, como devolvida pela Open-Meteo) e rótulo "HH:MM".
    local_time: str | None
    local_time_label: str | None
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


def geocode_location(query: str, *, count: int = 5) -> list[GeoLocation]:
    """Resolve um nome de cidade/país em coordenadas e fuso horário (IANA).

    Usa a API pública de geocodificação da Open-Meteo. Nunca levanta exceção:
    devolve ``[]`` quando a busca não encontra nada ou a internet falha.
    """
    texto = (query or "").strip()
    if len(texto) < 2:
        return []
    params = {
        "name": texto,
        "count": max(1, min(int(count), 10)),
        "language": "pt",
        "format": "json",
    }
    try:
        response = requests.get(GEOCODING_URL, params=params, timeout=(3, 6))
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Falha ao geocodificar %r: %s", texto, exc)
        return []

    resultados: list[GeoLocation] = []
    for item in payload.get("results") or []:
        latitude = _as_float(item.get("latitude"))
        longitude = _as_float(item.get("longitude"))
        if latitude is None or longitude is None:
            continue
        resultados.append(
            GeoLocation(
                name=str(item.get("name") or texto),
                country=item.get("country"),
                admin1=item.get("admin1"),
                latitude=latitude,
                longitude=longitude,
                timezone=item.get("timezone"),
            )
        )
    return resultados


class CameraWeatherService:
    """Cliente Open-Meteo por localização, com cache e tolerância a falhas.

    O cache é indexado por coordenadas arredondadas (≈11 m de resolução), o que
    evita repetir requisições para câmeras no mesmo jardim. Cada entrada guarda o
    seu próprio instante de captura, então o TTL é avaliado por localização.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # chave → (instantâneo, instante monotônico da captura)
        self._cache: dict[str, tuple[CameraWeatherSnapshot, float]] = {}
        # Garante uma única requisição HTTP simultânea (evita "estampede").
        self._fetch_lock = threading.Lock()

    def current_for(
        self,
        latitude: float,
        longitude: float,
        *,
        timezone_name: str | None = None,
        force: bool = False,
    ) -> CameraWeatherSnapshot | None:
        """Devolve clima + hora local da coordenada, usando o cache quando válido.

        Nunca levanta exceção. Em falha de conexão devolve o último valor
        conhecido (possivelmente expirado) ou ``None``.
        """
        key = self._cache_key(latitude, longitude)
        settings = get_settings()
        ttl_seconds = max(60.0, float(settings.weather_cache_minutes) * 60.0)
        now = time.monotonic()

        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and not force:
                snapshot, stored_at = cached
                if (now - stored_at) < ttl_seconds:
                    return snapshot

        # Se outro thread já está buscando, devolve o cache (mesmo expirado).
        if not self._fetch_lock.acquire(blocking=False):
            with self._lock:
                cached = self._cache.get(key)
                return cached[0] if cached else None

        try:
            fetched = self._fetch(latitude, longitude, timezone_name)
        finally:
            self._fetch_lock.release()

        if fetched is None:
            with self._lock:
                cached = self._cache.get(key)
                return cached[0] if cached else None

        with self._lock:
            self._cache[key] = (fetched, time.monotonic())
            if len(self._cache) > _MAX_CACHE_ENTRIES:
                # Descarta a entrada mais antiga (LRU aproximado por captura).
                mais_antiga = min(
                    self._cache, key=lambda k: self._cache[k][1]
                )
                self._cache.pop(mais_antiga, None)
        return fetched

    def _fetch(
        self,
        latitude: float,
        longitude: float,
        timezone_name: str | None,
    ) -> CameraWeatherSnapshot | None:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "current": CURRENT_FIELDS,
            "wind_speed_unit": "kmh",
            # "auto" faz a Open-Meteo resolver o fuso a partir das coordenadas e
            # devolver ``current.time`` já no horário local do jardim.
            "timezone": timezone_name or "auto",
        }
        try:
            response = requests.get(FORECAST_URL, params=params, timeout=(3, 6))
            response.raise_for_status()
            payload = response.json()
            current = payload["current"]
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "Falha ao consultar a Open-Meteo da câmera (%.3f, %.3f): %s",
                latitude,
                longitude,
                exc,
            )
            return None

        code = _as_int(current.get("weather_code"))
        is_day_raw = current.get("is_day")
        tz_name = payload.get("timezone") or timezone_name
        utc_offset = _as_int(payload.get("utc_offset_seconds"))
        # Hora local **exata** do jardim: calculada agora (relógio do servidor +
        # fuso da câmera), e não o carimbo de 15 min do modelo da Open-Meteo.
        local_dt = _local_now(tz_name, utc_offset)
        local_time_raw = current.get("time")
        return CameraWeatherSnapshot(
            temperature=_as_float(current.get("temperature_2m")),
            humidity=_as_float(current.get("relative_humidity_2m")),
            code=code,
            condition=wmo_label(code),
            category=weather_category(code),
            icon=wmo_icon(code),
            wind_speed=_as_float(current.get("wind_speed_10m")),
            is_day=bool(_as_int(is_day_raw)) if is_day_raw is not None else None,
            timezone=tz_name,
            utc_offset_seconds=utc_offset,
            local_time=(
                local_dt.isoformat()
                if local_dt is not None
                else (str(local_time_raw) if local_time_raw else None)
            ),
            local_time_label=(
                local_dt.strftime("%H:%M")
                if local_dt is not None
                else _hhmm(local_time_raw)
            ),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            source="open-meteo",
            available=code is not None,
        )

    @staticmethod
    def _cache_key(latitude: float, longitude: float) -> str:
        return f"{round(float(latitude), 4)},{round(float(longitude), 4)}"


def local_time_fields(
    detected_at_utc: str,
    timezone_name: str | None,
) -> tuple[int | None, str | None]:
    """Converte um instante UTC em (hora local, data local) no fuso da câmera.

    Usado pelo Alaris Core para gravar ``local_hour``/``local_date`` em cada
    visita. Devolve ``(None, None)`` quando não há fuso válido — nesse caso a
    análise cai para o UTC (comportamento anterior), sem quebrar nada.
    """
    if not timezone_name:
        return None, None
    try:
        tzinfo = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return None, None
    try:
        instante = datetime.fromisoformat(
            str(detected_at_utc).strip().replace("Z", "+00:00")
        )
    except (ValueError, TypeError):
        return None, None
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    try:
        local = instante.astimezone(tzinfo)
    except (ValueError, OSError):
        return None, None
    return local.hour, local.date().isoformat()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hhmm(value: Any) -> str | None:
    """Extrai "HH:MM" de um instante ISO local (ex.: "2026-10-16T14:49")."""
    if not value:
        return None
    texto = str(value)
    if "T" in texto and len(texto) >= 16:
        return texto[11:16]
    return None


def _local_now(tz_name: str | None, offset_seconds: int | None) -> datetime | None:
    """Relógio local do jardim: usa o fuso IANA e, na falta, o offset informado."""
    agora = datetime.now(timezone.utc)
    if tz_name:
        try:
            return agora.astimezone(ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
            pass
    if offset_seconds is not None:
        return agora.astimezone(timezone(timedelta(seconds=offset_seconds)))
    return None


_service: CameraWeatherService | None = None
_service_lock = threading.Lock()


def get_camera_weather_service() -> CameraWeatherService:
    """Devolve a instância única (singleton) do serviço de clima por câmera."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = CameraWeatherService()
    return _service
