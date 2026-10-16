"""Domain models and API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceType(str, Enum):
    USB = "usb"
    RTSP = "rtsp"
    ONVIF = "onvif"


class ZoneMode(str, Enum):
    INCLUDE = "include"
    EXCLUDE = "exclude"


class Point(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class ZoneConfig(BaseModel):
    id: str
    name: str = "zone"
    points: list[Point] = Field(min_length=3)
    mode: ZoneMode = ZoneMode.INCLUDE
    min_dwell_seconds: float = Field(default=2.0, ge=0.0)
    cooldown_seconds: float = Field(default=30.0, ge=0.0)
    absence_tolerance_seconds: float = Field(default=1.0, ge=0.0)
    enabled: bool = True


class CameraZones(BaseModel):
    zones: list[ZoneConfig] = Field(default_factory=list)


class RoiType(str, Enum):
    """Tipo de zona de interesse.

    - INCLUDE: monitorar — só registra visitas dentro do retângulo.
    - EXCLUDE: ignorar — descarta detecções dentro do retângulo (ex.: galhos,
      tráfego, reflexos).
    """

    INCLUDE = "include"
    EXCLUDE = "exclude"


class RoiZone(BaseModel):
    """Retângulo de interesse com coordenadas normalizadas (0..1).

    ``(x1, y1)`` é o canto superior esquerdo e ``(x2, y2)`` o canto inferior
    direito, sempre em relação ao quadro inteiro (largura/altura = 1.0).
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "Zona"
    type: RoiType = RoiType.INCLUDE
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordenar_cantos(self) -> "RoiZone":
        """Garante ``x1 <= x2`` e ``y1 <= y2``, mesmo se vierem invertidos."""
        if self.x1 > self.x2:
            self.x1, self.x2 = self.x2, self.x1
        if self.y1 > self.y2:
            self.y1, self.y2 = self.y2, self.y1
        return self

    def contains(self, x: float, y: float) -> bool:
        """Indica se o ponto normalizado ``(x, y)`` está dentro do retângulo."""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class RoiSettings(BaseModel):
    """Zonas de interesse (ROI) de uma câmera."""

    camera_id: str | None = None
    zones: list[RoiZone] = Field(default_factory=list)


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: SourceType
    source_uri: str = Field(
        description="USB index (e.g. '0') or RTSP/ONVIF host/URL",
    )
    username: str | None = None
    password: str | None = None
    enabled: bool = True
    zones: list[ZoneConfig] = Field(default_factory=list)

    @field_validator("source_uri")
    @classmethod
    def strip_uri(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("source_uri is required")
        return cleaned


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_type: SourceType | None = None
    source_uri: str | None = None
    username: str | None = None
    password: str | None = None
    enabled: bool | None = None
    zones: list[ZoneConfig] | None = None
    clear_credentials: bool = False


class CameraOut(BaseModel):
    id: str
    name: str
    source_type: SourceType
    source_uri: str
    has_credentials: bool = False
    enabled: bool
    zones: list[ZoneConfig] = Field(default_factory=list)
    status: str = "idle"
    created_at: str
    updated_at: str


class VisitOut(BaseModel):
    id: str
    camera_id: str
    camera_name: str | None = None
    species: str
    confidence: float
    detected_at: str
    dwell_seconds: float
    clip_path: str | None = None
    thumbnail_path: str | None = None
    clip_url: str | None = None
    thumbnail_url: str | None = None
    bbox: list[float] | None = None
    zone_id: str | None = None
    species_id: str | None = None
    assigned_species_common_name: str | None = None
    assigned_species_scientific_name: str | None = None
    # Condições meteorológicas no momento da visita (integração Open-Meteo).
    temperature: float | None = None
    humidity: float | None = None
    weather_code: str | None = None
    wind_speed: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BirdSpeciesOut(BaseModel):
    id: str
    common_name: str
    scientific_name: str
    description: str
    reference_image_path: str | None = None
    reference_image_url: str | None = None
    created_at: str


class VisitSpeciesAssignment(BaseModel):
    species_id: str | None


class AppSettingsOut(BaseModel):
    telegram_configured: bool
    discord_configured: bool
    yolo_model: str
    # Espelho somente-leitura da calibração atual (ver /api/settings/calibration).
    yolo_confidence: float
    pre_record_seconds: float
    post_record_seconds: float
    audio_analysis_enabled: bool = False
    audio_confidence_threshold: float = Field(default=0.70, ge=0.70, le=1.0)
    # Dispositivo de entrada de áudio (microfone USB/webcam). Vazio = primeiro
    # dispositivo disponível no sistema.
    audio_input_device: str = ""
    notifications_enabled: bool = True
    # Modo de alerta: "all" (qualquer visita) ou "new_species" (só espécies novas).
    notify_mode: str = "all"
    min_confidence_notify: float = 0.35
    extra: dict[str, Any] = Field(default_factory=dict)


class AppSettingsUpdate(BaseModel):
    notifications_enabled: bool | None = None
    notify_mode: str | None = Field(default=None, pattern="^(all|new_species)$")
    min_confidence_notify: float | None = Field(default=None, ge=0.0, le=1.0)
    # Mantido por compatibilidade: encaminhado para a calibração.
    yolo_confidence: float | None = Field(default=None, ge=0.05, le=1.0)
    pre_record_seconds: float | None = Field(default=None, ge=3.0, le=30.0)
    post_record_seconds: float | None = Field(default=None, ge=0.0, le=30.0)
    audio_analysis_enabled: bool | None = None
    audio_confidence_threshold: float | None = Field(
        default=None, ge=0.70, le=1.0
    )
    audio_input_device: str | None = None
    extra: dict[str, Any] | None = None


class AudioInputDeviceOut(BaseModel):
    """Dispositivo de entrada de áudio disponível no sistema."""

    name: str
    identifier: str | None = None


class AudioInputDevicesOut(BaseModel):
    """Lista de dispositivos de áudio, para o seletor das configurações."""

    platform: str
    devices: list[AudioInputDeviceOut] = Field(default_factory=list)
    selected: str = ""


class CalibrationProfile(str, Enum):
    """Perfis prontos de calibração, pensados para usuários não técnicos."""

    STATIONARY = "stationary"  # Passarinhos Parados / Alimentador
    FAST_MOTION = "fast_motion"  # Alta Movimentação / Voo Rápido
    CUSTOM = "custom"  # Ajustado manualmente nos sliders


class CalibrationOut(BaseModel):
    """Parâmetros de calibração ativos, aplicados em tempo de execução."""

    # Limiar de certeza da IA (menor = mais sensível).
    yolo_confidence: float = Field(ge=0.05, le=1.0)
    # Tempo máximo (s) que o rastreio mantém a visita mesmo com a ave imóvel.
    object_persistence_time: float = Field(ge=0.0, le=30.0)
    # Sensibilidade de detecção de movimento inicial (0 a 1).
    motion_sensitivity: float = Field(ge=0.0, le=1.0)
    # Perfil atualmente selecionado.
    profile: CalibrationProfile = CalibrationProfile.CUSTOM
    # Perfil sugerido como ponto de partida para o usuário.
    recommended_profile: CalibrationProfile = CalibrationProfile.STATIONARY


class CalibrationUpdate(BaseModel):
    """Atualização parcial da calibração."""

    profile: CalibrationProfile | None = None
    yolo_confidence: float | None = Field(default=None, ge=0.05, le=1.0)
    object_persistence_time: float | None = Field(default=None, ge=0.0, le=30.0)
    motion_sensitivity: float | None = Field(default=None, ge=0.0, le=1.0)


class AudioDetectionOut(BaseModel):
    id: str
    event_type: Literal["AUDIO_DETECTION"] = "AUDIO_DETECTION"
    camera_id: str
    camera_name: str
    detected_at: str
    species: str
    scientific_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    linked_visit_id: str | None = None
    # Condições meteorológicas no momento da detecção sonora.
    temperature: float | None = None
    humidity: float | None = None
    weather_code: str | None = None
    wind_speed: float | None = None


class AudioAnalysisStatusOut(BaseModel):
    enabled: bool
    status: Literal["disabled", "starting", "monitoring", "no_cameras", "error"]
    message: str
    monitored_cameras: int = Field(ge=0)


class StatsOut(BaseModel):
    total_visits: int
    visits_today: int
    active_cameras: int
    total_cameras: int
    species_counts: dict[str, int] = Field(default_factory=dict)
    visits_by_hour: dict[str, int] = Field(default_factory=dict)
    last_visit_at: str | None = None
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class AnalyticsSummaryOut(BaseModel):
    visits_today: int
    visits_last_7_days: int
    total_visits: int
    most_frequent_species: str | None
    most_frequent_species_count: int
    average_duration_seconds: float
    peak_hour: str | None


class HourlyDistributionOut(BaseModel):
    hour: str
    visits: int


class LifeListSpeciesOut(BaseModel):
    id: str
    common_name: str
    scientific_name: str
    description: str
    is_unlocked: bool
    first_seen_at: str | None
    featured_photo_url: str | None
    reference_image_url: str | None
    sightings_count: int
    # Campos gamificados do álbum de figurinhas.
    visits_count: int = 0
    # Raridade: "Comum" | "Incomum" | "Rara" | "Não observada".
    rarity: str = "Não observada"
    best_photo_url: str | None = None
    badges: list[str] = Field(default_factory=list)


class AchievementOut(BaseModel):
    """Medalha/marco do observador, com progresso e estado."""

    id: str
    name: str
    description: str
    icon: str
    target: int = Field(ge=1)
    progress: int = Field(ge=0)
    unlocked: bool


class NotificationTestRequest(BaseModel):
    channel: str = Field(description="telegram | discord")


class NotificationTestResponse(BaseModel):
    ok: bool
    message: str


class TimelapseOut(BaseModel):
    """Resumo do dia (time-lapse) disponível na galeria."""

    filename: str
    # Dia de referência no formato `YYYY-MM-DD`.
    day: str
    # URL de streaming pronta para o player (`/api/videos/timelapse/...`).
    url: str
    size_bytes: int = Field(ge=0)
    duration_seconds: float | None = None
    clips_count: int = Field(ge=0)
    speed: float = Field(ge=1.0)
    generated_at: str | None = None


class TimelapseGenerateRequest(BaseModel):
    """Pedido de geração sob demanda do resumo de um dia."""

    # Dia no formato `YYYY-MM-DD`; quando ausente, usa o dia atual (UTC).
    day: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    # `True` regenera mesmo que o resumo já exista.
    force: bool = False


class TimelapseGenerateResult(BaseModel):
    """Resultado da geração sob demanda (usado pela interface)."""

    status: Literal["generated", "exists", "empty", "unavailable"]
    message: str
    timelapse: TimelapseOut | None = None


class RecordingAnalysisOut(BaseModel):
    id: str
    camera_id: str
    filename: str
    status: Literal["queued", "processing", "completed", "failed"]
    progress: float = Field(ge=0.0, le=100.0)
    visits_created: int = Field(ge=0)
    error: str | None = None


class HistoryDeletionOut(BaseModel):
    deleted_records: int = Field(ge=0)
    deleted_media_files: int = Field(ge=0)
    failed_records: list[str] = Field(default_factory=list)
    failed_media_files: list[str] = Field(default_factory=list)


class ConfirmHistoryReset(BaseModel):
    confirmation: Literal["EXCLUIR TUDO"]


class EnvironmentSettingsOut(BaseModel):
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None
    ai_external_api_key: str | None = None
    # Provedor de IA compatível com a OpenAI (não são segredos).
    ai_external_base_url: str = "https://api.openai.com/v1"
    ai_external_model: str = "gpt-4o-mini"
    telegram_bot_token_configured: bool
    telegram_chat_id_configured: bool
    discord_webhook_url_configured: bool
    ai_external_api_key_configured: bool
    telegram_configured: bool
    discord_configured: bool
    ai_external_configured: bool


class EnvironmentSettingsUpdate(BaseModel):
    telegram_bot_token: str | None = Field(default=None, max_length=512)
    telegram_chat_id: str | None = Field(default=None, max_length=128)
    discord_webhook_url: str | None = Field(default=None, max_length=2048)
    ai_external_api_key: str | None = Field(default=None, max_length=512)
    ai_external_base_url: str | None = Field(default=None, max_length=2048)
    ai_external_model: str | None = Field(default=None, max_length=128)
    clear_telegram: bool = False
    clear_discord: bool = False
    clear_ai_external: bool = False


class EnvironmentConnectionTest(BaseModel):
    integration: Literal["telegram", "discord", "ai_external"]
    telegram_bot_token: str | None = Field(default=None, max_length=512)
    telegram_chat_id: str | None = Field(default=None, max_length=128)
    discord_webhook_url: str | None = Field(default=None, max_length=2048)
    ai_external_api_key: str | None = Field(default=None, max_length=512)
    ai_external_base_url: str | None = Field(default=None, max_length=2048)
    ai_external_model: str | None = Field(default=None, max_length=128)


class CurrentWeatherOut(BaseModel):
    """Clima atual do local do alimentador (widget do painel)."""

    available: bool = False
    temperature: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    # Rótulo legível em pt-BR (ex.: "Ensolarado", "Chuva leve").
    condition: str = "Sem dados"
    # Categoria ampla usada na correlação (ex.: "Ensolarado", "Chuva").
    category: str = "Sem dados"
    icon: str = "🌡️"
    weather_code: int | None = None
    fetched_at: str | None = None
    source: str = "open-meteo"


class WeatherConditionStatOut(BaseModel):
    """Agrupamento de visitas por condição/categoria meteorológica."""

    condition: str
    visits: int = Field(ge=0)
    avg_temperature: float | None = None
    avg_humidity: float | None = None
    avg_wind_speed: float | None = None


class WeatherHourStatOut(BaseModel):
    """Horário de pico e temperatura média das visitas nesse horário."""

    hour: str
    visits: int = Field(ge=0)
    avg_temperature: float | None = None


class WeatherCorrelationOut(BaseModel):
    """Cruzamento entre frequência de visitas e condições do tempo."""

    total_visits: int = Field(ge=0)
    visits_with_weather: int = Field(ge=0)
    avg_temperature_on_visits: float | None = None
    min_temperature_on_visits: float | None = None
    max_temperature_on_visits: float | None = None
    by_condition: list[WeatherConditionStatOut] = Field(default_factory=list)
    by_category: list[WeatherConditionStatOut] = Field(default_factory=list)
    peak_hours: list[WeatherHourStatOut] = Field(default_factory=list)
