"""Async Telegram / Discord notifications — never block the video pipeline."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any

import requests

from app.core.config import Settings, get_settings
from app.domain.models import VisitOut

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Fire-and-forget notification worker.

    Video threads only enqueue a payload; a background worker sends HTTP
    requests. Failures are logged and never raised to callers.
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
        """Non-blocking enqueue. Drops silently if queue is full."""
        if not self.settings.telegram_enabled and not self.settings.discord_enabled:
            return
        try:
            self._queue.put_nowait(visit)
        except Full:
            logger.warning("Notification queue full — dropping visit %s", visit.id)
        except Exception:
            logger.exception("Failed to enqueue notification")

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
        camera = visit.camera_name or visit.camera_id
        return (
            f"AviaWatch — visita detectada\n"
            f"Espécie: {visit.species}\n"
            f"Confiança: {visit.confidence:.0%}\n"
            f"Câmera: {camera}\n"
            f"Zona: {visit.zone_id or '-'}\n"
            f"Permanência: {visit.dwell_seconds:.1f}s\n"
            f"Quando: {visit.detected_at}"
        )

    def _resolve_local_image(self, visit: VisitOut) -> Path | None:
        rel = visit.thumbnail_path or visit.clip_path
        if not rel:
            return None
        # Only local files under captures — never fetch remote URLs
        path = self.settings.captures_dir / rel.replace("\\", "/").lstrip("/")
        if path.exists() and path.is_file():
            return path
        # thumbnail_path may already be relative like "thumbs/..."
        alt = self.settings.captures_dir / Path(rel).name
        if alt.exists():
            return alt
        return None

    def _send_telegram(self, text: str, image_path: Path | None) -> None:
        token = self.settings.telegram_bot_token
        chat_id = self.settings.telegram_chat_id
        timeout = 15

        if image_path and image_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            with image_path.open("rb") as fh:
                response = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": text[:1024]},
                    files={"photo": fh},
                    timeout=timeout,
                )
        else:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            response = requests.post(
                url,
                json={"chat_id": chat_id, "text": text},
                timeout=timeout,
            )

        if response.status_code >= 400:
            logger.error(
                "Telegram API error %s: %s",
                response.status_code,
                response.text[:300],
            )

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
