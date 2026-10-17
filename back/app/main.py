"""AviaWatch API — entry point."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.core.security_middleware import (
    LocalAccessGuardMiddleware,
    SecurityHeadersMiddleware,
)
from app.services.log_sanitizer import instalar_sanitizador
from slowapi.errors import RateLimitExceeded

# Ensure `back/` is on sys.path when running as `python -m app.main`
_BACK_DIR = Path(__file__).resolve().parents[1]
if str(_BACK_DIR) not in sys.path:
    sys.path.insert(0, str(_BACK_DIR))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
instalar_sanitizador()
logger = logging.getLogger("aviawatch")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.config import get_settings
    from app.infra.ai.detector import get_bird_detector
    from app.infra.ai.pipeline import get_pipeline_supervisor
    from app.infra.camera.manager import get_camera_manager
    from app.infra.database import close_all_connections, init_database
    from app.infra.media.retention import MediaRetentionWorker
    from app.services.audio_analysis import get_audio_analysis_service
    from app.services.notification_service import get_notification_service
    from app.services.offline_analysis import get_offline_analysis_service
    from app.services.timelapse_service import TimelapseScheduler

    settings = get_settings()
    settings.ensure_directories()

    try:
        init_database(settings.db_path)
    except Exception:
        logger.exception("Database initialization failed")
        raise

    notifier = get_notification_service()
    notifier.start()

    supervisor = get_pipeline_supervisor()
    supervisor.set_visit_handler(notifier.notify_visit)
    audio_analysis = get_audio_analysis_service()

    # Warm YOLO in background thread so API starts quickly
    def _warm_model() -> None:
        try:
            get_bird_detector().load()
        except Exception:
            logger.exception("YOLO warm-up failed")

    import threading

    threading.Thread(target=_warm_model, name="yolo-warmup", daemon=True).start()

    # Pré-aquece o cache de clima em segundo plano, para que o primeiro widget/
    # visita já encontre o valor disponível sem bloquear a thread do pipeline.
    from app.services.weather_service import get_weather_service

    def _warm_weather() -> None:
        try:
            get_weather_service().current()
        except Exception:
            logger.exception("Weather warm-up failed")

    threading.Thread(target=_warm_weather, name="weather-warmup", daemon=True).start()

    try:
        get_camera_manager().load_enabled()
        supervisor.sync_from_db()
        audio_analysis.start()
        logger.info(
            "Bem-Ti-Vi ready — data dir=%s (local only, no cloud sync)",
            settings.app_data_dir,
        )
    except Exception:
        logger.exception("Failed to start camera pipelines")

    retention_worker = MediaRetentionWorker(settings)
    retention_worker.start()
    # Gera o resumo do dia (time-lapse) no fim do dia e recupera dias pendentes.
    timelapse_scheduler = TimelapseScheduler()
    timelapse_scheduler.start()
    app.state.settings = settings
    yield

    logger.info("Shutting down AviaWatch…")
    retention_worker.stop()
    try:
        timelapse_scheduler.stop()
    except Exception:
        logger.exception("Timelapse scheduler shutdown error")
    try:
        audio_analysis.stop()
        audio_analysis.join(timeout=10)
    except Exception:
        logger.exception("Audio analysis shutdown error")
    try:
        supervisor.shutdown()
    except Exception:
        logger.exception("Pipeline shutdown error")
    try:
        get_camera_manager().shutdown()
    except Exception:
        logger.exception("Camera manager shutdown error")
    try:
        notifier.stop()
    except Exception:
        logger.exception("Notification service shutdown error")
    try:
        get_offline_analysis_service().shutdown()
    except Exception:
        logger.exception("Recording analysis shutdown error")
    try:
        close_all_connections()
    except Exception:
        logger.exception("DB close error")


app = FastAPI(
    title="Bem-Ti-Vi",
    description="Sistema local de monitoramento de avifauna por IA",
    version="0.2.0",
    lifespan=lifespan,
)

# Rate limiting (slowapi) — proteção contra brute force em rotas sensíveis.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuração resolvida uma única vez (usada por middlewares e montagens).
from app.core.config import get_settings as _get_settings_for_mount

_settings = _get_settings_for_mount()
_settings.ensure_directories()

# Restringe a API a conexões locais, salvo liberação explícita (ALLOW_REMOTE_ACCESS).
app.add_middleware(
    LocalAccessGuardMiddleware,
    allow_remote=_settings.allow_remote_access,
)
# Valida o cabeçalho Host (proteção contra Host Header Injection).
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_settings.allowed_hosts_list(),
)
# Cabeçalhos de segurança em toda resposta (adicionado por último = outermost).
app.add_middleware(SecurityHeadersMiddleware)

# Static local captures (clips / thumbs) — never proxied externally by the app
app.mount(
    "/captures",
    StaticFiles(directory=str(_settings.captures_dir)),
    name="captures",
)
app.mount(
    "/reference-birds",
    StaticFiles(directory=str(_settings.reference_birds_dir)),
    name="reference-birds",
)

from app.controllers import api_router

app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    """Evita 404 se alguém abrir a porta da API em vez do painel."""
    return """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="0;url=http://127.0.0.1:5173" />
  <title>AviaWatch API</title>
  <style>
    body { font-family: Segoe UI, sans-serif; background:#0a0f0d; color:#e8f5ef;
           display:flex; min-height:100vh; align-items:center; justify-content:center; }
    a { color:#34d399; }
    .box { max-width:28rem; padding:1.5rem; border:1px solid #1a2420; border-radius:12px; background:#111816; }
  </style>
</head>
<body>
  <div class="box">
    <h1>AviaWatch — API</h1>
    <p>Esta é a porta da <strong>API</strong> (8000), não o painel.</p>
    <p>Abra o painel em <a href="http://127.0.0.1:5173">http://127.0.0.1:5173</a></p>
    <p>Docs: <a href="/docs">/docs</a></p>
  </div>
</body>
</html>"""


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aviawatch"}


@app.get("/api/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "aviawatch-api"}


def run() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    # Default loopback keeps the API local; override with HOST=0.0.0.0 if needed
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    run()
