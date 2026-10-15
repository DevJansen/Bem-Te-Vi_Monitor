"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)
DEFAULT_APP_DATA_DIR = BASE_DIR / "app-data"


class Settings(BaseModel):
    app_name: str = "AviaWatch"
    port: int = Field(default=8000)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    ai_external_api_key: str = ""
    ai_external_model: str = "gpt-4o-mini"
    app_data_dir: Path = DEFAULT_APP_DATA_DIR
    yolo_model: str = "yolov8n.pt"
    # Sensibilidade da detecção: quanto menor o limiar, mais aves são detectadas
    # (inclusive à distância e com pouca luz), ao custo de mais falsos positivos.
    # 0.30 é o padrão recomendado para câmeras de comedouro/ninho.
    yolo_confidence: float = Field(default=0.30, ge=0.05, le=1.0)
    # Tempo de permanência imóvel (segundos): por quanto tempo o rastreio mantém
    # a visita ativa mesmo se a ave ficar totalmente imóvel se alimentando.
    object_persistence_time: float = Field(default=5.0, ge=0.0, le=30.0)
    # Sensibilidade de detecção de movimento inicial (0 a 1). Valores maiores
    # detectam movimentos mais sutis (ave chegando ao comedouro).
    motion_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    # Classe do dataset COCO para "bird". Mantida em 14 como padrão.
    yolo_bird_class_id: int = Field(default=14, ge=0)
    pre_record_seconds: float = Field(default=3.0, ge=3.0, le=30.0)
    post_record_seconds: float = 2.0
    camera_reconnect_delay_sec: float = 3.0
    media_retention_days: int = Field(default=30, ge=1)
    # Localização do alimentador (latitude/longitude), usada pela integração
    # meteorológica com a Open-Meteo. Padrão: São Paulo/SP.
    latitude: float = Field(default=-23.5505, ge=-90.0, le=90.0)
    longitude: float = Field(default=-46.6333, ge=-180.0, le=180.0)
    # Intervalo (minutos) de atualização do cache local de clima. Evita
    # requisições excessivas à API pública da Open-Meteo.
    weather_cache_minutes: int = Field(default=30, ge=5, le=1440)

    @property
    def db_path(self) -> Path:
        return self.app_data_dir / "aviawatch.db"

    @property
    def captures_dir(self) -> Path:
        return self.app_data_dir / "captures"

    @property
    def clips_dir(self) -> Path:
        return self.captures_dir / "clips"

    @property
    def thumbs_dir(self) -> Path:
        return self.captures_dir / "thumbs"

    @property
    def crops_dir(self) -> Path:
        return self.app_data_dir / "crops"

    @property
    def reference_birds_dir(self) -> Path:
        return self.app_data_dir / "reference_birds"

    @property
    def secrets_dir(self) -> Path:
        return self.app_data_dir / "secrets"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_webhook_url)

    def ensure_directories(self) -> None:
        for path in (
            self.app_data_dir,
            self.captures_dir,
            self.clips_dir,
            self.thumbs_dir,
            self.crops_dir,
            self.reference_birds_dir,
            self.secrets_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Settings":
        app_data = os.getenv("APP_DATA_DIR")
        return cls(
            port=int(os.getenv("PORT", "8000")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
            ai_external_api_key=os.getenv("AI_EXTERNAL_API_KEY", ""),
            ai_external_model=os.getenv("AI_EXTERNAL_MODEL", "gpt-4o-mini"),
            app_data_dir=Path(app_data) if app_data else DEFAULT_APP_DATA_DIR,
            yolo_model=os.getenv("YOLO_MODEL", "yolov8n.pt"),
            yolo_confidence=min(
                1.0,
                max(0.05, float(os.getenv("YOLO_CONFIDENCE", "0.30"))),
            ),
            object_persistence_time=min(
                30.0,
                max(
                    0.0,
                    float(
                        os.getenv(
                            "OBJECT_PERSISTENCE_TIME",
                            os.getenv("YOLO_TRACK_RETENTION_SECONDS", "5.0"),
                        )
                    ),
                ),
            ),
            motion_sensitivity=min(
                1.0,
                max(0.0, float(os.getenv("MOTION_SENSITIVITY", "0.5"))),
            ),
            yolo_bird_class_id=max(0, int(os.getenv("YOLO_BIRD_CLASS_ID", "14"))),
            pre_record_seconds=max(
                3.0,
                float(os.getenv("PRE_RECORD_SECONDS", "3.0")),
            ),
            post_record_seconds=float(os.getenv("POST_RECORD_SECONDS", "2.0")),
            camera_reconnect_delay_sec=float(
                os.getenv("CAMERA_RECONNECT_DELAY_SEC", "3.0")
            ),
            media_retention_days=int(os.getenv("MEDIA_RETENTION_DAYS", "30")),
            latitude=min(
                90.0, max(-90.0, float(os.getenv("LATITUDE", "-23.5505")))
            ),
            longitude=min(
                180.0, max(-180.0, float(os.getenv("LONGITUDE", "-46.6333")))
            ),
            weather_cache_minutes=max(
                5, int(os.getenv("WEATHER_CACHE_MINUTES", "30"))
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.ensure_directories()
    return settings
