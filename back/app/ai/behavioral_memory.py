"""Memória comportamental preditiva por espécie.

O Bem-Te-Vi observa o jardim há tempo suficiente para aprender **quando** cada
ave costuma aparecer. Este módulo transforma o histórico de visitas em perfis
comportamentais que cruzam:

* **horário local** da visita (respeitando o fuso da câmera — migração 8);
* **temperatura e umidade** registradas pela Open-Meteo no momento da visita;
* **condição meteorológica** (sol, nuvens, chuva…);
* **sazonalidade** (mês do ano / estação).

Com o perfil em mãos e o clima **atual**, o módulo estima a probabilidade de
cada espécie ter um pico de atividade nas próximas horas. O card do painel
mostra, por exemplo:

    Probabilidade de pico de Beija-Flores nas próximas 2 horas: 85% —
    condizente com a umidade e o histórico de temperatura.

O cálculo roda em segundo plano (`BehavioralMemoryWorker`) e o resultado é
cacheado em ``app_settings``. Assim, o painel responde instantaneamente e o
histórico sobrevive a reinicializações do aplicativo.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.infra.database.connection import db_session
from app.infra.database.repository import SettingsRepository
from app.services.weather_service import get_weather_service

logger = logging.getLogger(__name__)

# Chave do cache persistente dos perfis (formato versionado).
_PROFILES_KEY = "behavioral_memory_profiles_v1"

# Rótulos genéricos que não representam uma espécie (não geram previsão).
_GENERIC_SPECIES = {
    "bird",
    "passaro",
    "passaros",
    "passaro desconhecido",
    "pássaro desconhecido",
    "ave",
    "aves",
    "ave (genérica)",
    "ave (generica)",
    "ave nao identificada",
    "ave não identificada",
    "não identificada",
    "nao identificada",
    "unidentified",
    "unknown",
    "desconhecida",
    "desconhecido",
}

# Pesos do modelo de score (somam 1.0).
_WEIGHT_HOUR = 0.40
_WEIGHT_TEMPERATURE = 0.20
_WEIGHT_HUMIDITY = 0.13
_WEIGHT_WEATHER = 0.15
_WEIGHT_SEASON = 0.12

# Estações do hemisfério sul (Brasil), usadas no texto explicativo.
_SEASONS = {
    12: "Verão",
    1: "Verão",
    2: "Verão",
    3: "Outono",
    4: "Outono",
    5: "Outono",
    6: "Inverno",
    7: "Inverno",
    8: "Inverno",
    9: "Primavera",
    10: "Primavera",
    11: "Primavera",
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _gaussian_match(value: float | None, mean: float | None, sigma: float) -> float:
    """Similaridade gaussiana entre o valor atual e a média histórica."""
    if value is None or mean is None or sigma <= 0:
        return 0.55  # neutro: sem dados suficientes para opinar
    delta = (float(value) - float(mean)) / sigma
    return _clamp(math.exp(-0.5 * delta * delta))


def _hour_label(hour: int) -> str:
    return f"{int(hour) % 24:02d}h"


def _is_generic(name: str | None) -> bool:
    cleaned = (name or "").strip()
    return not cleaned or cleaned.casefold() in _GENERIC_SPECIES


def _season_for_month(month: int) -> str:
    return _SEASONS.get(int(month), "—")


class BehavioralMemoryService:
    """Constrói perfis por espécie e calcula previsões de pico."""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.db_path = settings.db_path
        self.settings_repo = SettingsRepository(self.db_path)
        self._lock = threading.Lock()
        self._profiles: dict[str, dict[str, Any]] = {}
        self._generated_at: str | None = None
        self._history_days: int = int(settings.behavioral_history_days)
        self._loaded_from_cache = False

    # ------------------------------------------------------------------ #
    # Construção dos perfis
    # ------------------------------------------------------------------ #
    def _build_profiles(self, days: int) -> tuple[dict[str, dict[str, Any]], int]:
        since = (
            datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
        ).isoformat()
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    v.species,
                    v.species_id,
                    COALESCE(bs.common_name, v.species) AS common_name,
                    bs.scientific_name,
                    COALESCE(
                        v.local_hour,
                        CAST(substr(v.detected_at, 12, 2) AS INTEGER)
                    ) AS local_hour,
                    COALESCE(v.local_date, substr(v.detected_at, 1, 10))
                        AS local_date,
                    v.temperature,
                    v.humidity,
                    v.weather_code,
                    v.detected_at
                FROM visits v
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                WHERE v.visitor_kind = 'bird'
                  AND v.detected_at >= ?
                ORDER BY v.detected_at ASC
                """,
                (since,),
            ).fetchall()

        profiles: dict[str, dict[str, Any]] = {}
        for row in rows:
            common = str(row["common_name"] or row["species"] or "").strip()
            if _is_generic(common):
                continue
            key = common.casefold()
            profile = profiles.get(key)
            if profile is None:
                profile = {
                    "species": common,
                    "scientific_name": row["scientific_name"],
                    "visits": 0,
                    "hours": [0] * 24,
                    "months": [0] * 12,
                    "temperature_sum": 0.0,
                    "temperature_sq_sum": 0.0,
                    "temperature_count": 0,
                    "humidity_sum": 0.0,
                    "humidity_sq_sum": 0.0,
                    "humidity_count": 0,
                    "weather": {},
                    "active_days": 0,
                    "_days": set(),
                    "first_seen_at": row["detected_at"],
                    "last_seen_at": row["detected_at"],
                }
                profiles[key] = profile

            profile["visits"] += 1
            try:
                hour = int(row["local_hour"])
            except (TypeError, ValueError):
                hour = 0
            profile["hours"][hour % 24] += 1

            # Mês a partir da data local (YYYY-MM-DD), com fallback para UTC.
            month = 0
            day_text = str(row["local_date"] or "")
            if len(day_text) >= 7:
                try:
                    month = int(day_text[5:7])
                except ValueError:
                    month = 0
            if month <= 0:
                month = datetime.now(timezone.utc).month
            profile["months"][(month - 1) % 12] += 1

            temperature = row["temperature"]
            if temperature is not None:
                try:
                    value = float(temperature)
                    profile["temperature_sum"] += value
                    profile["temperature_sq_sum"] += value * value
                    profile["temperature_count"] += 1
                except (TypeError, ValueError):
                    pass

            humidity = row["humidity"]
            if humidity is not None:
                try:
                    value = float(humidity)
                    profile["humidity_sum"] += value
                    profile["humidity_sq_sum"] += value * value
                    profile["humidity_count"] += 1
                except (TypeError, ValueError):
                    pass

            weather = (row["weather_code"] or "").strip()
            if weather:
                weather_counts = profile["weather"]
                weather_counts[weather] = weather_counts.get(weather, 0) + 1

            profile["_days"].add(day_text)
            profile["first_seen_at"] = min(
                str(profile["first_seen_at"]), str(row["detected_at"])
            )
            profile["last_seen_at"] = max(
                str(profile["last_seen_at"]), str(row["detected_at"])
            )

        # Finaliza médias/desvios e remove estruturas auxiliares não serializáveis.
        for profile in profiles.values():
            days_set = profile.pop("_days", set())
            profile["active_days"] = len(days_set)
            for prefix in ("temperature", "humidity"):
                count = int(profile[f"{prefix}_count"])
                total = float(profile[f"{prefix}_sum"])
                if count > 0:
                    mean = total / count
                    variance = max(
                        0.0,
                        float(profile[f"{prefix}_sq_sum"]) / count - mean * mean,
                    )
                    profile[f"{prefix}_mean"] = round(mean, 2)
                    profile[f"{prefix}_std"] = round(math.sqrt(variance), 2)
                else:
                    profile[f"{prefix}_mean"] = None
                    profile[f"{prefix}_std"] = None
        return profiles, len(rows)

    def refresh(self) -> dict[str, Any]:
        """Recalcula os perfis a partir do histórico e persiste no SQLite."""
        days = int(self.settings.behavioral_history_days)
        try:
            profiles, scanned = self._build_profiles(days)
        except Exception:
            logger.exception("Falha ao construir a memória comportamental")
            profiles, scanned = {}, 0

        generated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._profiles = profiles
            self._generated_at = generated_at
            self._history_days = days
            self._loaded_from_cache = True

        payload = {
            "generated_at": generated_at,
            "history_days": days,
            "scanned": scanned,
            "profiles": profiles,
        }
        try:
            self.settings_repo.set_json(_PROFILES_KEY, payload)
        except Exception:
            logger.exception("Falha ao persistir a memória comportamental")

        logger.info(
            "Memória comportamental atualizada: %s visitas, %s espécies",
            scanned,
            len(profiles),
        )
        return {
            "generated_at": generated_at,
            "history_days": days,
            "scanned": scanned,
            "species": len(profiles),
        }

    def _ensure_loaded(self) -> None:
        """Carrega o cache persistido na primeira consulta (após reiniciar)."""
        with self._lock:
            if self._loaded_from_cache:
                return
        payload: Any = None
        try:
            payload = self.settings_repo.get_json(_PROFILES_KEY)
        except Exception:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("profiles"), dict):
            with self._lock:
                self._profiles = payload["profiles"]
                self._generated_at = payload.get("generated_at")
                self._history_days = int(
                    payload.get("history_days")
                    or self.settings.behavioral_history_days
                )
                self._loaded_from_cache = True
        else:
            self.refresh()

    def profiles(self) -> dict[str, dict[str, Any]]:
        self._ensure_loaded()
        with self._lock:
            return self._profiles

    # ------------------------------------------------------------------ #
    # Previsão
    # ------------------------------------------------------------------ #
    def _current_weather(self) -> dict[str, Any]:
        try:
            snapshot = get_weather_service().current()
        except Exception:
            snapshot = None
        if snapshot is None or not getattr(snapshot, "available", False):
            return {
                "available": False,
                "temperature": None,
                "humidity": None,
                "condition": "Sem dados",
                "icon": "🌡️",
            }
        return {
            "available": True,
            "temperature": snapshot.temperature,
            "humidity": snapshot.humidity,
            "condition": snapshot.condition,
            "icon": snapshot.icon,
        }

    def _score_profile(
        self,
        profile: dict[str, Any],
        *,
        window_hours: list[int],
        current_weather: dict[str, Any],
        month: int,
    ) -> dict[str, Any]:
        visits = max(1, int(profile.get("visits") or 0))
        hours: list[int] = list(profile.get("hours") or [0] * 24)
        window_visits = sum(hours[hour % 24] for hour in window_hours)
        expected_share = len(window_hours) / 24.0
        observed_share = window_visits / visits
        # Recompensa concentração: um pico real supera em muito a Fração
        # esperada se as visitas fossem uniformes ao longo do dia.
        hour_score = _clamp(observed_share / max(expected_share * 2.0, 1e-6))

        temperature_score = _gaussian_match(
            current_weather.get("temperature"),
            profile.get("temperature_mean"),
            sigma=max(4.0, float(profile.get("temperature_std") or 0.0) * 1.3),
        )
        humidity_score = _gaussian_match(
            current_weather.get("humidity"),
            profile.get("humidity_mean"),
            sigma=max(12.0, float(profile.get("humidity_std") or 0.0) * 1.3),
        )

        weather_counts: dict[str, int] = dict(profile.get("weather") or {})
        condition = str(current_weather.get("condition") or "")
        if current_weather.get("available") and condition and weather_counts:
            # Preferência relativa pela condição atual (normalizada pelo
            # clima mais frequente da espécie), com suavização de Laplace.
            matches = int(weather_counts.get(condition, 0))
            peak = max(weather_counts.values())
            weather_score = _clamp(((matches + 1) / visits) / max(
                (peak + 1) / visits, 1e-6
            ))
        else:
            weather_score = 0.55

        months: list[int] = list(profile.get("months") or [0] * 12)
        month_visits = months[(max(1, month) - 1) % 12]
        month_share = month_visits / visits
        expected_month = 1.0 / 12.0
        season_score = _clamp(month_share / max(expected_month * 2.0, 1e-6))

        score = (
            _WEIGHT_HOUR * hour_score
            + _WEIGHT_TEMPERATURE * temperature_score
            + _WEIGHT_HUMIDITY * humidity_score
            + _WEIGHT_WEATHER * weather_score
            + _WEIGHT_SEASON * season_score
        )
        # Calibração logística: scores ~0,5 → ~50%; ~0,75 → ~80%.
        probability = 1.0 / (1.0 + math.exp(-5.5 * (score - 0.48)))
        # Espécies com pouco histórico são "encolhidas" para perto de 50%,
        # evitando previsões categóricas baseadas em 2 ou 3 visitas.
        confidence_factor = _clamp(visits / 20.0, 0.35, 1.0)
        probability = 0.5 + (probability - 0.5) * confidence_factor
        probability_pct = int(round(_clamp(probability) * 100))

        # Horário de pico dentro da janela prevista.
        peak_hour: int | None = None
        peak_count = 0
        for hour in window_hours:
            count = hours[hour % 24]
            if count > peak_count:
                peak_count = count
                peak_hour = hour % 24
        if peak_hour is None and any(hours):
            peak_hour = max(range(24), key=lambda idx: hours[idx])

        window_label = f"{_hour_label(window_hours[0])}–{_hour_label(window_hours[-1] + 1)}"

        factors: list[dict[str, Any]] = [
            {
                "key": "horario",
                "label": "Horário",
                "score": int(round(hour_score * 100)),
                "detail": (
                    f"{window_visits} de {visits} visitas ({observed_share * 100:.0f}%) "
                    f"ocorrem nesta janela do dia."
                ),
            },
            {
                "key": "temperatura",
                "label": "Temperatura",
                "score": int(round(temperature_score * 100)),
                "detail": self._temperature_detail(profile, current_weather),
            },
            {
                "key": "umidade",
                "label": "Umidade",
                "score": int(round(humidity_score * 100)),
                "detail": self._humidity_detail(profile, current_weather),
            },
            {
                "key": "clima",
                "label": "Clima",
                "score": int(round(weather_score * 100)),
                "detail": self._weather_detail(profile, current_weather),
            },
            {
                "key": "sazonalidade",
                "label": "Sazonalidade",
                "score": int(round(season_score * 100)),
                "detail": (
                    f"{month_visits} visitas em {_SEASON_MONTH_NAMES[(month - 1) % 12]} "
                    f"({_season_for_month(month)})."
                ),
            },
        ]

        strong = [
            factor["label"].lower()
            for factor in factors
            if factor["score"] >= 65
        ]
        if strong:
            condizente = self._join_pt(strong[:3])
        elif current_weather.get("available"):
            condizente = "o histórico local de horário e clima"
        else:
            condizente = "o histórico local de horário"

        species = str(profile.get("species") or "Ave")
        horizon = len(window_hours)
        headline = (
            f"Probabilidade de pico de {species} nas próximas {horizon} "
            f"{'hora' if horizon == 1 else 'horas'}: {probability_pct}% — "
            f"condizente com {condizente}."
        )
        detail = self._detail_text(
            profile,
            probability_pct=probability_pct,
            window_label=window_label,
            peak_hour=peak_hour,
            current_weather=current_weather,
            month=month,
        )

        confidence = (
            "alta"
            if visits >= 30 and int(profile.get("temperature_count") or 0) >= 8
            else "média"
            if visits >= 10
            else "estimativa"
        )

        return {
            "species": species,
            "scientific_name": profile.get("scientific_name"),
            "probability": probability_pct,
            "horizon_hours": horizon,
            "window_label": window_label,
            "expected_peak_hour": _hour_label(peak_hour) if peak_hour is not None else None,
            "headline": headline,
            "detail": detail,
            "tone": (
                "positive"
                if probability_pct >= 75
                else "info"
                if probability_pct >= 50
                else "neutral"
            ),
            "icon": "🐦",
            "confidence": confidence,
            "visits_analyzed": visits,
            "factors": factors,
        }

    @staticmethod
    def _join_pt(items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return f"{', '.join(items[:-1])} e {items[-1]}"

    @staticmethod
    def _temperature_detail(
        profile: dict[str, Any], current_weather: dict[str, Any]
    ) -> str:
        mean = profile.get("temperature_mean")
        current = current_weather.get("temperature")
        if mean is None:
            return "Ainda não há temperatura registrada para esta espécie."
        if current is None:
            return f"Média histórica de {mean:.0f} °C (clima atual indisponível)."
        return (
            f"Atual {current:.0f} °C · média histórica da espécie "
            f"{mean:.0f} °C."
        )

    @staticmethod
    def _humidity_detail(
        profile: dict[str, Any], current_weather: dict[str, Any]
    ) -> str:
        mean = profile.get("humidity_mean")
        current = current_weather.get("humidity")
        if mean is None:
            return "Ainda não há umidade registrada para esta espécie."
        if current is None:
            return f"Umidade média histórica de {mean:.0f}%."
        return (
            f"Atual {current:.0f}% · média histórica da espécie {mean:.0f}%."
        )

    @staticmethod
    def _weather_detail(
        profile: dict[str, Any], current_weather: dict[str, Any]
    ) -> str:
        weather = dict(profile.get("weather") or {})
        condition = current_weather.get("condition") or "Sem dados"
        if not weather:
            return f"Clima atual: {condition}."
        top = max(weather.items(), key=lambda item: item[1])[0]
        return f"Clima atual: {condition} · condição mais comum: {top}."

    def _detail_text(
        self,
        profile: dict[str, Any],
        *,
        probability_pct: int,
        window_label: str,
        peak_hour: int | None,
        current_weather: dict[str, Any],
        month: int,
    ) -> str:
        visits = int(profile.get("visits") or 0)
        days = int(profile.get("active_days") or 0)
        parts = [
            f"Baseado em {visits} visitas em {days} dia(s) de observação.",
            f"Janela prevista: {window_label}.",
        ]
        if peak_hour is not None:
            parts.append(f"Pico histórico mais provável: {_hour_label(peak_hour)}.")
        if current_weather.get("available"):
            parts.append(
                f"Agora: {current_weather.get('condition')} · "
                f"{current_weather.get('temperature')} °C · "
                f"{current_weather.get('humidity')}% de umidade."
            )
        parts.append(
            f"Estação: {_season_for_month(month)}. Confiança da previsão: "
            f"{'alta' if probability_pct >= 70 else 'moderada' if probability_pct >= 50 else 'baixa'}."
        )
        return " ".join(parts)

    def predict(
        self,
        *,
        species: str | None = None,
        horizon_hours: int | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Prevê picos de atividade para as próximas horas.

        Sem ``species`` devolve um ranking (mais provável primeiro). Com
        ``species`` devolve apenas aquela espécie (útil para cards dedicados).
        """
        self._ensure_loaded()
        horizon = int(
            horizon_hours or self.settings.behavioral_prediction_hours
        )
        horizon = max(1, min(horizon, 12))
        limit = max(1, min(int(limit), 24))

        profiles = self.profiles()
        now = datetime.now().astimezone()
        window_hours = [(now.hour + offset) % 24 for offset in range(horizon)]
        current_weather = self._current_weather()

        predictions: list[dict[str, Any]] = []
        for profile in profiles.values():
            if int(profile.get("visits") or 0) < 2:
                continue
            if species and str(profile.get("species") or "").casefold() != species.casefold():
                continue
            predictions.append(
                self._score_profile(
                    profile,
                    window_hours=window_hours,
                    current_weather=current_weather,
                    month=now.month,
                )
            )

        predictions.sort(
            key=lambda item: (item["probability"], item["visits_analyzed"]),
            reverse=True,
        )
        if species:
            highlighted = predictions[0] if predictions else None
        else:
            highlighted = predictions[0] if predictions else None
            predictions = predictions[:limit]

        with self._lock:
            generated_at = self._generated_at
        notes = ""
        if not predictions:
            notes = (
                "Ainda não há histórico suficiente para prever picos. "
                "As previsões aparecem após algumas visitas identificadas."
            )

        return {
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "horizon_hours": horizon,
            "history_days": self._history_days,
            "current_weather": current_weather,
            "predictions": predictions,
            "highlight": highlighted,
            "notes": notes,
        }

    def status(self) -> dict[str, Any]:
        """Resumo da memória (usado pelo painel e pelo endpoint de refresh)."""
        profiles = self.profiles()
        with self._lock:
            generated_at = self._generated_at
            history_days = self._history_days
        return {
            "generated_at": generated_at,
            "history_days": history_days,
            "species": len(profiles),
            "visits": sum(int(p.get("visits") or 0) for p in profiles.values()),
        }


class BehavioralMemoryWorker:
    """Atualiza a memória comportamental periodicamente, em segundo plano."""

    def __init__(self, initial_delay: float = 25.0) -> None:
        # Compartilha o singleton com os endpoints: o worker atualiza o mesmo
        # cache que o painel consulta (sem cópias divergentes em memória).
        self.service = get_behavioral_memory_service()
        self.initial_delay = max(0.0, float(initial_delay))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="behavioral-memory",
            daemon=True,
        )
        self._thread.start()

    def _loop(self) -> None:
        if self._stop.wait(self.initial_delay):
            return
        interval = max(60.0, float(self.service.settings.behavioral_refresh_minutes) * 60.0)
        while not self._stop.is_set():
            try:
                self.service.refresh()
            except Exception:
                logger.exception("Falha na atualização da memória comportamental")
            if self._stop.wait(interval):
                return

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)
        self._thread = None


_SEASON_MONTH_NAMES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

_service: BehavioralMemoryService | None = None
_service_lock = threading.Lock()


def get_behavioral_memory_service() -> BehavioralMemoryService:
    """Instância única (singleton) da memória comportamental."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = BehavioralMemoryService()
    return _service


__all__ = [
    "BehavioralMemoryService",
    "BehavioralMemoryWorker",
    "get_behavioral_memory_service",
]
