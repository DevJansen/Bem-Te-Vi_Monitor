"""REST routes for application settings."""

from __future__ import annotations

import ipaddress
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.domain.models import (
    AppSettingsOut,
    AppSettingsUpdate,
    CalibrationOut,
    CalibrationUpdate,
    EnvironmentConnectionTest,
    EnvironmentSettingsOut,
    EnvironmentSettingsUpdate,
    NotificationTestRequest,
    NotificationTestResponse,
    RoiSettings,
)
from app.infra.database.repository import SettingsRepository
from app.infra.ai.pipeline import get_pipeline_supervisor
from app.services.calibration import get_calibration_service
from app.services.environment_settings import (
    read_environment_settings,
    save_environment_settings,
    test_environment_connection,
)
from app.services.notification_service import get_notification_service
from app.services.notifier import get_telegram_notifier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])
_test_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notify-test")


def _repo() -> SettingsRepository:
    return SettingsRepository(get_settings().db_path)


def _require_local_environment_request(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    try:
        is_local = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_local = False
    if not is_local:
        raise HTTPException(
            status_code=403,
            detail="A configuração de segredos só pode ser acessada localmente",
        )


def _build_out() -> AppSettingsOut:
    settings = get_settings()
    repo = _repo()
    stored = repo.get_all()

    def _bool(key: str, default: bool) -> bool:
        raw = stored.get(key)
        if raw is None:
            return default
        return str(raw).lower() in {"1", "true", "yes", "on"}

    def _float(key: str, default: float) -> float:
        raw = stored.get(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def _notify_mode(store: dict[str, Any]) -> str:
        """Modo de alerta: ``all`` (qualquer visita) ou ``new_species``."""
        raw = store.get("notify_mode")
        return raw if raw in {"all", "new_species"} else "all"

    extra_raw = stored.get("extra_json", "{}")
    try:
        extra = json.loads(extra_raw)
        if not isinstance(extra, dict):
            extra = {}
    except Exception:
        extra = {}

    calibration = get_calibration_service().current()

    return AppSettingsOut(
        telegram_configured=settings.telegram_enabled,
        discord_configured=settings.discord_enabled,
        yolo_model=settings.yolo_model,
        # Espelha a calibração ativa (fonte de verdade: /api/settings/calibration).
        yolo_confidence=calibration.yolo_confidence,
        pre_record_seconds=max(
            3.0,
            _float("pre_record_seconds", settings.pre_record_seconds),
        ),
        post_record_seconds=_float("post_record_seconds", settings.post_record_seconds),
        audio_analysis_enabled=_bool("audio_analysis_enabled", False),
        audio_confidence_threshold=min(
            1.0,
            max(0.70, _float("audio_confidence_threshold", 0.70)),
        ),
        audio_input_device=(stored.get("audio_input_device") or "").strip(),
        notifications_enabled=_bool("notifications_enabled", True),
        notify_mode=_notify_mode(stored),
        min_confidence_notify=_float(
            "min_confidence_notify", settings.yolo_confidence
        ),
        extra=extra,
    )


@router.get("", response_model=AppSettingsOut)
async def get_app_settings() -> AppSettingsOut:
    try:
        return _build_out()
    except Exception as exc:
        logger.exception("get_app_settings failed")
        raise HTTPException(status_code=500, detail="Failed to load settings") from exc


@router.get("/calibration", response_model=CalibrationOut)
async def get_calibration() -> CalibrationOut:
    """Retorna os parâmetros de calibração de sensibilidade ativos."""
    try:
        return get_calibration_service().current()
    except Exception as exc:
        logger.exception("get_calibration failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar a calibração",
        ) from exc


@router.post("/calibration", response_model=CalibrationOut)
async def update_calibration(payload: CalibrationUpdate) -> CalibrationOut:
    """Atualiza a calibração e aplica em tempo de execução (sem reiniciar)."""
    try:
        return get_calibration_service().update(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("update_calibration failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível salvar a calibração",
        ) from exc


# Prefixo das chaves de ROI no repositório de configurações.
_ROI_KEY_PREFIX = "roi_zones"


def _roi_key(camera_id: str | None) -> str:
    """Chave de armazenamento das zonas de interesse (por câmera)."""
    return f"{_ROI_KEY_PREFIX}:{camera_id or 'default'}"


@router.get("/roi", response_model=RoiSettings)
async def get_roi(camera_id: str | None = None) -> RoiSettings:
    """Retorna as zonas de interesse (ROI) salvas para a câmera informada."""
    try:
        stored = _repo().get_json(_roi_key(camera_id), {"zones": []})
        return RoiSettings.model_validate(
            {"camera_id": camera_id, **(stored or {})}
        )
    except Exception as exc:
        logger.exception("get_roi failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar as zonas de interesse",
        ) from exc


@router.post("/roi", response_model=RoiSettings)
async def save_roi(payload: RoiSettings) -> RoiSettings:
    """Salva as zonas de interesse e aplica nos pipelines em execução."""
    try:
        _repo().set_json(
            _roi_key(payload.camera_id),
            {"zones": [zone.model_dump() for zone in payload.zones]},
        )
        # Recarrega as zonas sem reiniciar o backend.
        get_pipeline_supervisor().reload_zones(payload.camera_id)
        return payload
    except Exception as exc:
        logger.exception("save_roi failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível salvar as zonas de interesse",
        ) from exc


@router.get("/env", response_model=EnvironmentSettingsOut)
async def get_environment_settings(request: Request) -> EnvironmentSettingsOut:
    _require_local_environment_request(request)
    try:
        return read_environment_settings()
    except Exception as exc:
        logger.exception("get_environment_settings failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível ler as variáveis de ambiente",
        ) from exc


@router.post("/env", response_model=EnvironmentSettingsOut)
async def save_environment(
    payload: EnvironmentSettingsUpdate,
    request: Request,
) -> EnvironmentSettingsOut:
    _require_local_environment_request(request)
    try:
        return save_environment_settings(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("save_environment failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível salvar as variáveis de ambiente",
        ) from exc


@router.post("/env/test", response_model=NotificationTestResponse)
def test_environment(
    payload: EnvironmentConnectionTest,
    request: Request,
) -> NotificationTestResponse:
    _require_local_environment_request(request)
    try:
        return test_environment_connection(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("test_environment failed integration=%s", payload.integration)
        raise HTTPException(
            status_code=500,
            detail="Não foi possível testar a integração",
        ) from exc


@router.put("", response_model=AppSettingsOut)
async def update_app_settings(payload: AppSettingsUpdate) -> AppSettingsOut:
    try:
        repo = _repo()
        if payload.notifications_enabled is not None:
            repo.set(
                "notifications_enabled",
                "true" if payload.notifications_enabled else "false",
            )
        if payload.min_confidence_notify is not None:
            repo.set("min_confidence_notify", str(payload.min_confidence_notify))
        if payload.notify_mode is not None:
            repo.set("notify_mode", payload.notify_mode.strip().lower())
        if payload.yolo_confidence is not None:
            # Encaminha para a calibração (fonte de verdade) e aplica em runtime.
            get_calibration_service().update(
                CalibrationUpdate(yolo_confidence=payload.yolo_confidence)
            )
        if payload.pre_record_seconds is not None:
            repo.set("pre_record_seconds", str(payload.pre_record_seconds))
        if payload.post_record_seconds is not None:
            repo.set("post_record_seconds", str(payload.post_record_seconds))
        if payload.audio_analysis_enabled is not None:
            repo.set(
                "audio_analysis_enabled",
                "true" if payload.audio_analysis_enabled else "false",
            )
        if payload.audio_confidence_threshold is not None:
            repo.set(
                "audio_confidence_threshold",
                str(payload.audio_confidence_threshold),
            )
        if payload.audio_input_device is not None:
            repo.set("audio_input_device", payload.audio_input_device.strip())
        if payload.extra is not None:
            repo.set_json("extra_json", payload.extra)
        return _build_out()
    except Exception as exc:
        logger.exception("update_app_settings failed")
        raise HTTPException(status_code=500, detail="Failed to update settings") from exc


@router.post("/test-notification", response_model=NotificationTestResponse)
async def test_notification(payload: NotificationTestRequest) -> NotificationTestResponse:
    """Send a one-shot test alert without blocking the video pipeline."""
    channel = (payload.channel or "").strip().lower()
    settings = get_settings()
    notifier = get_notification_service()

    if channel == "telegram":
        if not settings.telegram_enabled:
            raise HTTPException(
                status_code=400,
                detail="Telegram não configurado. Preencha TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env",
            )
        telegram = get_telegram_notifier()
        ok, detail = telegram.test_connection()
        if not ok:
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao testar Telegram: {detail}",
            )
        try:
            future = _test_pool.submit(
                telegram.send_message,
                "AviaWatch — teste de notificação Telegram\nCanal local OK.",
            )
            future.result(timeout=20)
            return NotificationTestResponse(
                ok=True,
                message=f"Mensagem de teste enviada ao Telegram. {detail}",
            )
        except Exception as exc:
            logger.exception("Telegram test failed")
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao enviar teste Telegram: {exc}",
            ) from exc

    if channel == "discord":
        if not settings.discord_enabled:
            raise HTTPException(
                status_code=400,
                detail="Discord não configurado. Preencha DISCORD_WEBHOOK_URL no .env",
            )
        try:
            future = _test_pool.submit(
                notifier._send_discord,
                "AviaWatch — teste de notificação Discord\nCanal local OK.",
                None,
            )
            future.result(timeout=20)
            return NotificationTestResponse(
                ok=True,
                message="Mensagem de teste enviada ao Discord.",
            )
        except Exception as exc:
            logger.exception("Discord test failed")
            raise HTTPException(
                status_code=502,
                detail=f"Falha ao enviar teste Discord: {exc}",
            ) from exc

    raise HTTPException(status_code=400, detail="Canal inválido. Use 'telegram' ou 'discord'.")
