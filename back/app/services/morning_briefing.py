"""Resumo Matinal Automatizado (Morning Briefing).

Compila diariamente, no horário configurado (padrão 07:00), um briefing
inteligente com:
- previsão do tempo atualizada (Open-Meteo) para cada jardim cadastrado;
- predição de visitas do dia gerada pelo Bem-Te-Vi Core (memória de hábitos);
- a foto de destaque ("Momento Raro / Postal") capturada no dia anterior.

O briefing é enviado diretamente via Telegram e/ou Discord configurados.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.infra.database.repository import SettingsRepository, VisitRepository
from app.services.camera_weather import get_camera_weather_service
from app.services.rare_moments import get_rare_moments_service

logger = logging.getLogger(__name__)


class MorningBriefingScheduler(threading.Thread):
    """Agendador diário do Resumo Matinal, seguindo o padrão do TimelapseScheduler."""

    def __init__(
        self,
        hour: int = 7,
        minute: int = 0,
        *,
        on_briefing: Any | None = None,
    ) -> None:
        super().__init__(name="morning-briefing", daemon=True)
        self._hour = max(0, min(23, hour))
        self._minute = max(0, min(59, minute))
        self._stop_event = threading.Event()
        self._on_briefing = on_briefing

    def stop(self) -> None:
        self._stop_event.set()

    def _seconds_until_next_run(self) -> float:
        now = datetime.now()
        target = now.replace(hour=self._hour, minute=self._minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    def run(self) -> None:
        while not self._stop_event.is_set():
            wait = self._seconds_until_next_run()
            self._stop_event.wait(timeout=wait)
            if self._stop_event.is_set():
                break
            try:
                self._compile_and_send()
            except Exception:
                logger.exception("Falha ao compilar/enviar o Resumo Matinal")

    def _compile_and_send(self) -> None:
        settings = get_settings()
        from app.infra.database.repository import CameraRepository

        cameras = CameraRepository(settings.db_path).list_all()
        weather_lines: list[str] = []
        prediction_lines: list[str] = []

        for cam in cameras:
            lat = cam.get("latitude")
            lon = cam.get("longitude")
            tz = cam.get("timezone")
            name = cam.get("name") or cam.get("location_label") or "Jardim"
            if lat is not None and lon is not None:
                snapshot = get_camera_weather_service().current_for(lat, lon, timezone_name=tz)
                if snapshot and snapshot.available:
                    weather_lines.append(
                        f"🌤 {name}: {snapshot.temperature}°C, {snapshot.condition or '—'}, "
                        f"umidade {snapshot.humidity}%"
                    )
                else:
                    weather_lines.append(f"🌤 {name}: clima indisponível")
            else:
                weather_lines.append(f"🌤 {name}: sem coordenadas")

        # Predição de visitas do dia via Bem-Te-Vi Core (behavioral memory).
        try:
            from app.ai.behavioral_memory import get_behavioral_memory_service
            svc = get_behavioral_memory_service()
            # Predict para cada espécie do catálogo.
            from app.infra.database.repository import BirdSpeciesRepository
            species_list = BirdSpeciesRepository(settings.db_path).list_all()
            for sp in species_list[:8]:
                common = sp.get("common_name") or sp.get("name")
                if not common:
                    continue
                try:
                    pred = svc.predict(species=common, horizon_hours=12, limit=1)
                    if not pred:
                        continue
                    # pred pode ser dict com 'probability' ou lista
                    items = pred if isinstance(pred, list) else [pred]
                    for p in items[:1]:
                        prob = p.get("probability") or p.get("score") or 0
                        if prob and prob > 0:
                            prediction_lines.append(
                                f"🔮 {common}: {round(prob * 100)}% de chance de visita"
                            )
                except Exception:
                    logger.debug("Predição falhou para %s", common, exc_info=True)
        except Exception:
            logger.debug("Predição comportamental indisponível para o briefing", exc_info=True)

        # Foto de destaque do dia anterior (Momento Raro / Postal).
        postcard_path = None
        try:
            from datetime import date, timedelta
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            visits = VisitRepository(settings.db_path).list_by_day(yesterday, limit=50)
            if visits:
                # Pega a visita com maior confiança e nitidez.
                best = max(visits, key=lambda v: (v.get("confidence") or 0, v.get("sharpness") or 0))
                postcard_bytes = get_rare_moments_service().build_postcard(best["id"])
                if postcard_bytes:
                    import tempfile
                    from pathlib import Path
                    tmp = Path(tempfile.gettempdir()) / f"briefing_postcard_{yesterday}.jpg"
                    tmp.write_bytes(postcard_bytes)
                    postcard_path = tmp
        except Exception:
            logger.debug("Foto de destaque indisponível para o briefing", exc_info=True)

        # Monta o texto do briefing.
        lines = [
            "🌅 *Resumo Matinal — Bem-Te-Vi Monitor*",
            f"📅 {datetime.now().strftime('%d/%m/%Y')}",
            "",
            "🌤 *Clima nos jardins:*",
        ]
        lines.extend(weather_lines or ["  (sem jardins cadastrados)"])
        lines.append("")
        lines.append("🔮 *Predição de visitas hoje:*")
        lines.extend(prediction_lines or ["  (sem predições disponíveis)"])
        lines.append("")
        lines.append("📸 Foto de destaque do dia anterior em anexo.")
        text = "\n".join(lines)

        # Envia via Telegram e/ou Discord.
        try:
            from app.services.notifier import get_telegram_notifier
            notifier = get_telegram_notifier()
            if notifier.configured:
                if postcard_path:
                    notifier.send_photo(postcard_path, text)
                else:
                    notifier.send_message(text)
        except Exception:
            logger.exception("Falha ao enviar briefing via Telegram")

        try:
            webhook = settings.discord_webhook_url
            if webhook:
                import requests
                requests.post(webhook, json={"content": text[:1900]}, timeout=15)
        except Exception:
            logger.debug("Discord indisponível para o briefing", exc_info=True)

        if self._on_briefing is not None:
            try:
                self._on_briefing(text, postcard_path)
            except Exception:
                logger.debug("Callback de briefing falhou", exc_info=True)


def get_morning_briefing_scheduler() -> MorningBriefingScheduler:
    """Cria o agendador com a hora configurada no banco/settings."""
    try:
        repo = SettingsRepository(get_settings().db_path)
        hour_raw = repo.get("morning_briefing_hour", "7")
        minute_raw = repo.get("morning_briefing_minute", "0")
        hour = int(hour_raw) if hour_raw else 7
        minute = int(minute_raw) if minute_raw else 0
    except Exception:
        hour, minute = 7, 0
    return MorningBriefingScheduler(hour=hour, minute=minute)
