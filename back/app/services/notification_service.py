"""Notificações assíncronas por Telegram/Discord — nunca bloqueiam o pipeline."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any

import requests

from app.core.config import Settings, get_settings
from app.domain.models import VisitOut
from app.services.notifier import get_telegram_notifier

logger = logging.getLogger(__name__)

# Rótulos usados quando o modelo não identifica a espécie de fato. Nesses casos
# não faz sentido considerar "espécie nova" no modo de alerta por novas espécies.
_GENERIC_SPECIES_LABELS = {
    "bird",
    "passaro",
    "passaros",
    "passaro desconhecido",
    "pássaro desconhecido",
    "ave",
    "aves",
    "ave (genérica)",
    "ave (generica)",
    "unidentified",
    "unknown",
    "desconhecida",
    "desconhecido",
}


def _format_detected_at(value: str) -> str:
    """Converte o ISO-8601 (UTC) da visita num horário local legível.

    Nunca lança exceção: se o valor não for uma data válida, devolve o
    texto original para não quebrar o envio do alerta.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%d/%m/%Y %H:%M")


class NotificationService:
    """
    Worker de notificações "fire-and-forget".

    As threads de vídeo apenas enfileiram a visita; um worker em segundo plano
    envia as requisições HTTP. Falhas são registradas no log e nunca propagadas
    para quem chamou.
    """

    def __init__(self, settings: Settings | None = None, max_queue: int = 200) -> None:
        self.settings = settings or get_settings()
        self._queue: Queue[VisitOut | None] = Queue(maxsize=max_queue)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notify")
        self._worker = threading.Thread(
            target=self._run, name="notification-worker", daemon=True
        )
        self._stopped = threading.Event()
        self._started = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._stopped.clear()
            self._worker.start()
            self._started = True
            logger.info(
                "Notification service started (telegram=%s discord=%s)",
                self.settings.telegram_enabled,
                self.settings.discord_enabled,
            )

    def stop(self, timeout: float = 5.0) -> None:
        self._stopped.set()
        try:
            self._queue.put_nowait(None)
        except Full:
            pass
        if self._worker.is_alive():
            self._worker.join(timeout=timeout)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def notify_visit(self, visit: VisitOut) -> None:
        """Enfileira a visita sem bloquear; descarta em silêncio se a fila encher.

        Antes de enfileirar, decide se a visita merece alerta respeitando as
        preferências do painel: notificações ligadas, confiança mínima e o modo
        escolhido (qualquer visita ou apenas novas espécies).
        """
        if not self.settings.telegram_enabled and not self.settings.discord_enabled:
            return
        if not self._should_notify(visit):
            return
        try:
            self._queue.put_nowait(visit)
        except Full:
            logger.warning("Notification queue full — dropping visit %s", visit.id)
        except Exception:
            logger.exception("Failed to enqueue notification")

    def _should_notify(self, visit: VisitOut) -> bool:
        """Decide se a visita deve gerar alerta, respeitando as preferências."""
        # Visitantes Especiais (esquilos, gatos…) não geram alertas de aves: são
        # registrados no painel "Convidados do Jardim", mas nunca disparam
        # Telegram/Discord/Webhook como se fossem uma ave.
        if (visit.visitor_kind or "bird") != "bird":
            return False
        if not self._notify_enabled():
            return False
        if visit.confidence < self._min_confidence_notify():
            return False
        if self._notify_mode() == "new_species" and not self._is_new_species(visit):
            return False
        # Regras personalizadas de alerta (Smart Alerts): avaliam condições
        # configuradas pelo observador antes de disparar a notificação.
        try:
            from app.services.smart_alerts import evaluate_rules
            # Monta um dict de evento com dados extras para as regras.
            event = {
                "is_new_species": self._is_new_species(visit),
                "ecological_status": getattr(visit, "ecological_status", None),
                "individual_id": getattr(visit, "individual_id", None),
            }
            if not evaluate_rules(visit, event):
                logger.debug("Smart Alerts suprimiu notificação para visita %s", visit.id)
                return False
        except Exception:
            logger.debug("Falha ao avaliar Smart Alerts; notificação segue normal", exc_info=True)
        return True

    def _settings_repo(self):
        """Repositório de configurações, criado sob demanda.

        O import é tardio de propósito: ``app.infra.database.repository`` importa
        ``app.services.weather_service`` e o pacote ``app.services`` importa este
        módulo — importar no topo criaria um ciclo de importação.
        """
        from app.infra.database.repository import SettingsRepository

        return SettingsRepository(self.settings.db_path)

    def _species_repo(self):
        """Repositório do catálogo de espécies, criado sob demanda (ver acima)."""
        from app.infra.database.repository import BirdSpeciesRepository

        return BirdSpeciesRepository(self.settings.db_path)

    def _notify_enabled(self) -> bool:
        raw = self._settings_repo().get("notifications_enabled", "true")
        return str(raw).lower() in {"1", "true", "yes", "on"}

    def _notify_mode(self) -> str:
        """Modo de notificação: ``all`` (qualquer visita) ou ``new_species``."""
        raw = self._settings_repo().get("notify_mode")
        return raw if raw in {"all", "new_species"} else "all"

    def _min_confidence_notify(self) -> float:
        """Confiança mínima para alertar (padrão: a calibração do YOLO)."""
        raw = self._settings_repo().get("min_confidence_notify")
        if raw is not None:
            try:
                return float(raw)
            except ValueError:
                pass
        return self.settings.yolo_confidence

    def _is_new_species(self, visit: VisitOut) -> bool:
        """Indica se a espécie da visita ainda não consta no catálogo local.

        Considera nome comum, nome científico e o rótulo da detecção,
        normalizados (minúsculas, sem espaços extras). Detecções genéricas
        (ex.: "bird"/"ave genérica") não contam como espécie nova, pois o
        modelo não identificou a espécie de fato.
        """
        labels = self._visit_species_labels(visit)
        if not labels:
            return False
        known_names = self._known_species_names()
        if not known_names:
            # Catálogo vazio: qualquer espécie identificada é "nova".
            return True
        return not any(name in known_names for name in labels)

    @staticmethod
    def _visit_species_labels(visit: VisitOut) -> set[str]:
        """Nomes de espécie úteis da visita, sem rótulos genéricos."""
        raw = {
            visit.assigned_species_common_name,
            visit.assigned_species_scientific_name,
            visit.species,
        }
        labels = {(value or "").strip().lower() for value in raw}
        return {
            label
            for label in labels
            if label and label not in _GENERIC_SPECIES_LABELS
        }

    def _known_species_names(self) -> set[str]:
        """Nomes já cadastrados no catálogo local (minúsculas)."""
        try:
            rows = self._species_repo().list_all()
        except Exception:
            logger.exception("Failed to read species catalog")
            return set()
        names: set[str] = set()
        for row in rows:
            for key in ("common_name", "scientific_name"):
                value = (row.get(key) or "").strip().lower()
                if value:
                    names.add(value)
        return names

    def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if item is None:
                break
            try:
                self._executor.submit(self._dispatch, item)
            except Exception:
                logger.exception("Failed to submit notification task")

    def _dispatch(self, visit: VisitOut) -> None:
        text = self._format_message(visit)
        image_path = self._resolve_local_image(visit)

        if self.settings.telegram_enabled:
            try:
                self._send_telegram(text, image_path)
            except Exception:
                logger.exception("Telegram notification failed for visit %s", visit.id)

        if self.settings.discord_enabled:
            try:
                self._send_discord(text, image_path)
            except Exception:
                logger.exception("Discord notification failed for visit %s", visit.id)

    @staticmethod
    def _format_message(visit: VisitOut) -> str:
        """Monta a mensagem de alerta com espécie, horário e contexto da visita."""
        camera = visit.camera_name or visit.camera_id
        # Prioriza o nome comum atribuído pelo usuário; senão, o rótulo da IA.
        species = visit.assigned_species_common_name or visit.species
        scientific = visit.assigned_species_scientific_name
        if scientific and scientific.strip().lower() not in species.strip().lower():
            species = f"{species} ({scientific})"
        return (
            "🐦 Bem-Te-Vi — visita detectada\n"
            f"Espécie: {species}\n"
            f"Confiança: {visit.confidence:.0%}\n"
            f"Câmera: {camera}\n"
            f"Permanência: {visit.dwell_seconds:.1f}s\n"
            f"Quando: {_format_detected_at(visit.detected_at)}"
        )

    def _resolve_local_image(self, visit: VisitOut) -> Path | None:
        rel = visit.thumbnail_path or visit.clip_path
        if not rel:
            return None
        # Apenas arquivos locais dentro de captures — nunca buscar URLs remotas.
        path = self.settings.captures_dir / rel.replace("\\", "/").lstrip("/")
        if path.exists() and path.is_file():
            return path
        # thumbnail_path pode vir apenas com o nome, ex.: "thumbs/...".
        alt = self.settings.captures_dir / Path(rel).name
        if alt.exists():
            return alt
        return None

    def _send_telegram(self, text: str, image_path: Path | None) -> None:
        notifier = get_telegram_notifier()
        if image_path and image_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            notifier.send_photo(image_path, text)
        else:
            notifier.send_message(text)

    def _send_discord(self, text: str, image_path: Path | None) -> None:
        webhook = self.settings.discord_webhook_url
        timeout = 15
        payload: dict[str, Any] = {"content": text[:1900]}

        if image_path and image_path.exists():
            with image_path.open("rb") as fh:
                response = requests.post(
                    webhook,
                    data={"content": payload["content"]},
                    files={"file": (image_path.name, fh)},
                    timeout=timeout,
                )
        else:
            response = requests.post(webhook, json=payload, timeout=timeout)

        if response.status_code >= 400:
            logger.error(
                "Discord webhook error %s: %s",
                response.status_code,
                response.text[:300],
            )


_notification_service: NotificationService | None = None
_notify_lock = threading.Lock()


def get_notification_service() -> NotificationService:
    global _notification_service
    with _notify_lock:
        if _notification_service is None:
            _notification_service = NotificationService()
        return _notification_service
