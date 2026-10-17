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
    # Fontes ao vivo externas (proxy seguro no backend; credenciais em memória).
    HLS = "hls"
    HTTP = "http"
    WEBRTC = "webrtc"


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

    ``role`` descreve a função da zona (ex.: ``feeder``/``drinker`` para
    comedouro/bebedouro), permitindo a análise de comportamento (alimentando-se
    x pousada) e a priorização de detecções. ``confidence`` sobrescreve o limiar
    global do YOLO dentro desta zona — útil para deixar o comedouro mais
    permissivo (aves pequenas/camufladas) sem afetar o resto da cena.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "Zona"
    type: RoiType = RoiType.INCLUDE
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)
    # Papel da zona: "feeder", "drinker", "perch", "other".
    role: str = "other"
    # Limiar de confiança específico da zona (None = usa o global).
    confidence: float | None = Field(default=None, ge=0.05, le=1.0)

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
    stream_url: str = Field(
        description="URL/índice do stream ao vivo (USB, RTSP, HLS, HTTP, WebRTC)."
    )
    # Rótulo de localização (ex.: "Bebedouro do vizinho", "Sitio").
    location_label: str | None = Field(default=None, max_length=160)
    # Localização geográfica opcional (câmeras globais/remotas). Permite exibir
    # o clima e o horário locais do jardim e corrigir os gráficos de pico pelo
    # fuso da câmera.
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    # Identificador IANA do fuso (ex.: "America/Costa_Rica").
    timezone: str | None = Field(default=None, max_length=64)
    # País resolvido pelo geocodificador (ex.: "Costa Rica").
    country: str | None = Field(default=None, max_length=80)
    username: str | None = None
    password: str | None = None
    enabled: bool = True
    zones: list[ZoneConfig] = Field(default_factory=list)

    @field_validator("stream_url")
    @classmethod
    def strip_uri(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("stream_url is required")
        return cleaned

    @model_validator(mode="after")
    def _validar_coordenadas(self) -> "CameraCreate":
        """Exige latitude e longitude juntas (ou nenhuma das duas)."""
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "Informe latitude e longitude juntas (ou deixe ambas vazias)."
            )
        return self


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_type: SourceType | None = None
    stream_url: str | None = None
    location_label: str | None = Field(default=None, max_length=160)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    timezone: str | None = Field(default=None, max_length=64)
    country: str | None = Field(default=None, max_length=80)
    username: str | None = None
    password: str | None = None
    enabled: bool | None = None
    zones: list[ZoneConfig] | None = None
    clear_credentials: bool = False
    # Quando verdadeiro, apaga a localização geográfica da câmera.
    clear_location: bool = False

    @model_validator(mode="after")
    def _validar_coordenadas(self) -> "CameraUpdate":
        """Exige latitude e longitude juntas quando uma delas é informada."""
        if not self.clear_location and (
            self.latitude is None
        ) != (self.longitude is None):
            raise ValueError(
                "Informe latitude e longitude juntas (ou use clear_location)."
            )
        return self


class CameraOut(BaseModel):
    id: str
    name: str
    source_type: SourceType
    stream_url: str
    location_label: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    country: str | None = None
    has_credentials: bool = False
    is_active: bool
    zones: list[ZoneConfig] = Field(default_factory=list)
    status: str = "idle"
    # Indica se a câmera está processando quadros em visão noturna (IR/baixa luz).
    night_mode: bool = False
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
    # Visitantes Silvestres / Convidados Especiais (migração 9).
    # "bird" para aves; "mammal"/"other" para quem não é ave (ex.: esquilo).
    visitor_kind: str = "bird"
    # Grupo divertido do visitante (ex.: "esquilo", "felino").
    visitor_group: str | None = None
    # Segmentação por Jardim (migração 10): rótulo amigável do jardim no
    # momento da captura (ex.: "Jardim da Varanda").
    location_label: str | None = None
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
    # Status ecológico regional (avifauna do Sul do Brasil / SC).
    ecological_status: str | None = None
    ecological_status_label: str | None = None
    ecological_badge: str | None = None


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


class NightVisionMode(str, Enum):
    """Modo de visão noturna (infravermelho / baixa luz).

    - ``auto``: só aplica o realce quando o quadro está escuro.
    - ``on``: aplica o realce sempre (câmeras IR que não escurecem o suficiente).
    - ``off``: nunca aplica o realce.
    """

    AUTO = "auto"
    ON = "on"
    OFF = "off"

    @classmethod
    def normalize(cls, value: object) -> "NightVisionMode":
        """Converte o valor recebido (texto do .env, enum, booleano) em modo válido.

        Aceita ``auto``/``on``/``off`` e também ``true``/``false`` (e sinônimos),
        para compatibilidade com a configuração ``NIGHT_VISION_MODE: true/false``.
        Qualquer valor não reconhecido cai no modo automático.
        """
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().lower()
        if text in {"on", "true", "1", "yes", "sim", "sempre", "ligado"}:
            return cls.ON
        if text in {"off", "false", "0", "no", "não", "nao", "desligado"}:
            return cls.OFF
        return cls.AUTO


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
    # Visão noturna: modo de realce para baixa luz / infravermelho.
    night_vision_mode: NightVisionMode = NightVisionMode.AUTO
    # Luminância média (0-255) que separa "claro" de "escuro" no modo automático.
    night_vision_threshold: float = Field(default=60.0, ge=0.0, le=255.0)
    # Expansão opcional das classes detectadas (fauna noturna além de aves).
    night_fauna_enabled: bool = False
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
    # Visão noturna (infravermelho / baixa luz) e fauna noturna.
    night_vision_mode: NightVisionMode | None = None
    night_vision_threshold: float | None = Field(default=None, ge=0.0, le=255.0)
    night_fauna_enabled: bool | None = None


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
    # --- Visitantes Silvestres / Convidados Especiais (Modo Esquilo) ---
    # Contadores lúdicos do painel: quantos "ladrões de sementes" passaram hoje.
    visitors_today: int = 0
    squirrel_visits_today: int = 0
    seeds_stolen_today: int = 0
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


# --- Segmentação por Jardim (Câmaras Remotas/Locais) -------------------------
class GardenTodayOut(BaseModel):
    """Resumo de um jardim (câmera) no dia de hoje."""

    camera_id: str
    garden: str
    camera_name: str | None = None
    visits: int = 0
    species_counts: dict[str, int] = Field(default_factory=dict)
    visits_by_hour: dict[str, int] = Field(default_factory=dict)


class TodayByGardenOut(BaseModel):
    """Visitas de hoje consolidadas e segmentadas por jardim."""

    date: str
    consolidated_visits: int = 0
    consolidated_species_counts: dict[str, int] = Field(default_factory=dict)
    consolidated_visits_by_hour: dict[str, int] = Field(default_factory=dict)
    gardens: list[GardenTodayOut] = Field(default_factory=list)


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
    # Status ecológico regional (avifauna do Sul do Brasil / SC).
    ecological_status: str | None = None
    ecological_status_label: str | None = None
    ecological_badge: str | None = None


class SpeciesSightingOut(BaseModel):
    """Uma avistagem individual da espécie (linha do histórico da ficha)."""

    visit_id: str
    detected_at: str
    confidence: float
    thumbnail_url: str | None = None
    # Recorte tratado pelo Alaris Core (close-up da ave), servido por endpoint.
    crop_url: str | None = None
    temperature: float | None = None
    humidity: float | None = None
    weather_code: str | None = None
    dwell_seconds: float = 0.0


class SpeciesHourStatOut(BaseModel):
    """Visitas da espécie em um horário do dia (histograma de pico)."""

    hour: str
    visits: int
    avg_temperature: float | None = None


class SpeciesWeatherStatOut(BaseModel):
    """Visitas da espécie sob uma condição meteorológica (Open-Meteo)."""

    condition: str
    visits: int
    avg_temperature: float | None = None


class SpeciesConsultOut(BaseModel):
    """Ficha ornitológica profunda devolvida pela IA externa (Gemini/OpenAI).

    Estrutura rica pedida no *prompt* ornitológico: nome científico, família,
    status de conservação, comportamento alimentar, habitat, curiosidades e
    dados biogeográficos.
    """

    scientific_name: str
    common_name: str
    family: str = ""
    order: str = ""
    conservation_status: str = ""
    diet: str = ""
    feeding_behavior: str = ""
    habitat: str = ""
    distribution: str = ""
    biogeography: str = ""
    migration: str = ""
    size_cm: str = ""
    weight_g: str = ""
    lifespan: str = ""
    curiosities: list[str] = Field(default_factory=list)
    notes: str = ""
    # Metadados da consulta (provedor, modelo, imagem usada e cache).
    provider: str | None = None
    model: str | None = None
    image_source: str | None = None
    generated_at: str | None = None
    cached: bool = False


class SpeciesProfileOut(BaseModel):
    """Ficha técnica completa de uma espécie do Catálogo Local (Minhas Aves).

    Reúne o histórico de avistagens, os horários de pico, a temperatura média
    preferida (cruzada com a Open-Meteo), as notas científicas e o status
    ecológico regional — tudo o que o front-end exibe no card/página da espécie.
    """

    id: str
    common_name: str
    scientific_name: str
    description: str
    reference_image_url: str | None = None
    created_at: str
    # Estatísticas de avistagem.
    visits_count: int = 0
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    active_days: int = 0
    average_dwell_seconds: float | None = None
    best_photo_url: str | None = None
    # Conteúdo rico / gamificação.
    rarity: str = "Não observada"
    badges: list[str] = Field(default_factory=list)
    ecological_status: str | None = None
    ecological_status_label: str | None = None
    ecological_badge: str | None = None
    # Observação curada da base regional (habitat/sazonalidade).
    ecological_notes: str | None = None
    peak_hour: str | None = None
    hourly_distribution: list[SpeciesHourStatOut] = Field(default_factory=list)
    # Clima cruzado (Open-Meteo).
    avg_temperature: float | None = None
    min_temperature: float | None = None
    max_temperature: float | None = None
    avg_humidity: float | None = None
    weather_distribution: list[SpeciesWeatherStatOut] = Field(default_factory=list)
    # Histórico recente (mais novo primeiro).
    recent_sightings: list[SpeciesSightingOut] = Field(default_factory=list)
    # Ficha ornitológica da IA externa em cache (quando já consultada).
    ai_consult: SpeciesConsultOut | None = None


class AchievementOut(BaseModel):
    """Medalha/marco do observador, com progresso e estado."""

    id: str
    name: str
    description: str
    icon: str
    target: int = Field(ge=1)
    progress: int = Field(ge=0)
    unlocked: bool
    # Medalha "secreta": só revela nome/descrição depois de desbloqueada.
    secret: bool = False


class WildlifeVisitorStatOut(BaseModel):
    """Contagem de um grupo de Visitantes Especiais (ex.: Esquilos)."""

    group: str
    label: str
    icon: str
    gallery_category: str
    visits: int = Field(ge=0)
    last_seen_at: str | None = None
    # Consumo estimado (brincadeira): sementes/petiscos levados por esse grupo.
    estimated_consumption: int = Field(ge=0)
    unit: str = ""


class WildlifeSummaryOut(BaseModel):
    """Painel dos Visitantes Silvestres / Convidados Especiais (Modo Esquilo)."""

    total_visits: int = Field(ge=0)
    visits_today: int = Field(ge=0)
    # Quantos grupos distintos apareceram hoje.
    visitors_today: int = Field(ge=0)
    squirrel_visits_today: int = Field(ge=0)
    # Estatísticas divertidas do painel.
    seeds_stolen_today: int = Field(ge=0)
    seeds_stolen_total: int = Field(ge=0)
    first_visit_at: str | None = None
    has_visitors: bool = False
    # Desbloqueio da badge secreta "O Ladrão de Sementes".
    squirrel_badge_unlocked: bool = False
    groups: list[WildlifeVisitorStatOut] = Field(default_factory=list)
    generated_at: str


class AnomalyOut(BaseModel):
    """Anomalia acústico-visual (ex.: espécie reaparece após longo intervalo).

    Permite a biólogos acompanhar eventos raros: uma espécie que não era
    registrada há meses reaparecer de repente é um dado relevante de conservação.
    """

    id: str
    # Tipo da anomalia: "species_return" (retorno de espécie ausente).
    kind: str = "species_return"
    created_at: str
    species: str
    scientific_name: str | None = None
    # Dias desde o registro anterior (quando aplicável).
    days_absent: int | None = None
    message: str
    visit_id: str | None = None
    acknowledged: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


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


class OfflineDetectionOut(BaseModel):
    """Uma ave distinta identificada ao longo de um vídeo offline."""

    id: str
    # Instante (em segundos) dentro do vídeo em que a melhor captura ocorreu.
    timestamp_seconds: float = Field(ge=0.0)
    species: str
    confidence: float = Field(ge=0.0, le=1.0)
    # Miniatura do quadro completo e recorte ampliado da ave (URLs servidas
    # pela API local). Podem ser nulos se a gravação da imagem falhar.
    thumbnail_url: str | None = None
    crop_url: str | None = None
    # Visita criada automaticamente na Galeria para esta ave.
    visit_id: str | None = None


class OfflineJobOut(BaseModel):
    """Estado completo de um upload/análise offline (persistente no backend).

    O status é mantido no servidor e sobrevive à desconexão do painel: o
    front-end apenas consulta este recurso por *polling*.
    """

    id: str
    camera_id: str
    camera_name: str | None = None
    filename: str
    status: Literal["queued", "processing", "completed", "error"]
    progress: float = Field(ge=0.0, le=100.0)
    frames_processed: int = Field(ge=0)
    total_frames: int = Field(ge=0)
    # Mensagem amigável do andamento (ex.: "Processando frame 450/1200…").
    progress_message: str = ""
    birds_detected_count: int = Field(ge=0)
    detections: list[OfflineDetectionOut] = Field(default_factory=list)
    # Resumo final (ex.: "Foram detectados 4 pássaros distintos ao longo do vídeo").
    summary: str | None = None
    error: str | None = None
    created_at: str
    finished_at: str | None = None


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
    # Provedor efetivo da IA externa: "google" (Gemini oficial) ou "openai".
    ai_external_provider: str = "openai"
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
    ai_external_provider: str | None = Field(default=None, max_length=32)
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
    ai_external_provider: str | None = Field(default=None, max_length=32)


class CameraWeatherOut(BaseModel):
    """Clima e horário **locais** de uma câmera global/remota.

    Diferente do widget do alimentador local, aqui o jardim pode estar em outro
    país: além do clima, devolvemos a hora local exata da câmera (``local_time``)
    para o painel mostrar, por exemplo, o sol da Costa Rica enquanto é noite no
    Brasil. Quando a câmera não tem coordenadas ou a internet falha, devolve
    ``available=False`` sem quebrar a interface.
    """

    available: bool = False
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    utc_offset_seconds: int | None = None
    # Hora local do jardim (ISO, ex.: "2026-10-16T14:49") e rótulo "HH:MM".
    local_time: str | None = None
    local_time_label: str | None = None
    temperature: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    condition: str = "Sem dados"
    category: str = "Sem dados"
    icon: str = "🌡️"
    weather_code: int | None = None
    # Dia (True) ou noite (False) no jardim, segundo a Open-Meteo.
    is_day: bool | None = None
    fetched_at: str | None = None
    source: str = "open-meteo"


class GeoLocationOut(BaseModel):
    """Localidade candidata do "seletor de cidade inteligente"."""

    name: str
    country: str | None = None
    admin1: str | None = None
    latitude: float
    longitude: float
    timezone: str | None = None
    # Rótulo amigável pronto para exibir (ex.: "San José, San José, Costa Rica").
    label: str


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


class TemperatureRangeInsightOut(BaseModel):
    """Resumo de uma faixa de temperatura (visitas, espécies e horário médio)."""

    label: str
    min_temperature: float | None = None
    max_temperature: float | None = None
    visits: int = Field(ge=0)
    distinct_species: int = Field(ge=0)
    active_days: int = Field(ge=0)
    visits_per_day: float = Field(ge=0.0)
    avg_hour: float | None = None
    avg_hour_label: str | None = None
    avg_temperature: float | None = None
    avg_humidity: float | None = None
    top_species: str | None = None


class WeatherConditionInsightOut(BaseModel):
    """Visitas agrupadas por categoria ampla de clima (com visitas por dia)."""

    condition: str
    icon: str = "🌡️"
    visits: int = Field(ge=0)
    distinct_species: int = Field(ge=0)
    active_days: int = Field(ge=0)
    visits_per_day: float = Field(ge=0.0)
    avg_hour: float | None = None
    avg_hour_label: str | None = None
    avg_temperature: float | None = None
    avg_humidity: float | None = None
    top_species: str | None = None


class TemperaturePeriodInsightOut(BaseModel):
    """Período (mais frio / mais quente) com horário médio de aparecimento."""

    period: str
    label: str
    visits: int = Field(ge=0)
    distinct_species: int = Field(ge=0)
    active_days: int = Field(ge=0)
    visits_per_day: float = Field(ge=0.0)
    avg_hour: float | None = None
    avg_hour_label: str | None = None
    avg_temperature: float | None = None
    avg_humidity: float | None = None
    top_species: str | None = None


class SpeciesWeatherTimingOut(BaseModel):
    """Mudança de horário de uma espécie entre condições frias e quentes."""

    species: str
    scientific_name: str | None = None
    cold_avg_hour: float | None = None
    hot_avg_hour: float | None = None
    cold_visits: int = Field(ge=0)
    hot_visits: int = Field(ge=0)
    minutes_earlier: float | None = None
    # "earlier" (mais cedo no calor), "later" (mais tarde) ou "similar".
    direction: str = "similar"
    summary: str = ""


class InsightCardOut(BaseModel):
    """Card de resumo inteligente pronto para exibição no painel."""

    id: str
    icon: str = "💡"
    title: str
    description: str
    # "positive", "info", "warning" ou "neutral" (orienta a cor do card).
    tone: str = "info"


class WeatherInsightsOut(BaseModel):
    """Insights avançados que cruzam visitas com clima e hábitos."""

    total_visits: int = Field(ge=0)
    visits_with_weather: int = Field(ge=0)
    cold_threshold_celsius: float | None = None
    temperature_ranges: list[TemperatureRangeInsightOut] = Field(
        default_factory=list
    )
    best_temperature_range: TemperatureRangeInsightOut | None = None
    conditions: list[WeatherConditionInsightOut] = Field(default_factory=list)
    rainy: WeatherConditionInsightOut | None = None
    dry: WeatherConditionInsightOut | None = None
    rainy_vs_dry_percent: float | None = None
    periods: list[TemperaturePeriodInsightOut] = Field(default_factory=list)
    species_timing: list[SpeciesWeatherTimingOut] = Field(default_factory=list)
    insights: list[InsightCardOut] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )


# --------------------------------------------------------------------------- #
# Motor de IA (AI Core) — status, telemetria e log cognitivo
# --------------------------------------------------------------------------- #
class AiEngineOut(BaseModel):
    """Estado do modelo/inferência em uso (Edge AI)."""

    state: str
    model: str | None = None
    backend: str | None = None
    device: str | None = None
    imgsz: int | None = None
    confidence: float | None = None
    notes: list[str] = Field(default_factory=list)


class AiThroughputOut(BaseModel):
    """Volume de trabalho do motor (FPS, inferências e detecções)."""

    fps: float = 0.0
    inferences_today: int = 0
    inferences_total: int = 0
    detections_today: int = 0
    detections_total: int = 0
    frames_analyzed: int = 0


class AiPerformanceOut(BaseModel):
    """Latência da inferência (ms)."""

    latency_ms_last: float = 0.0
    latency_ms_avg: float = 0.0
    latency_ms_min: float = 0.0
    latency_ms_max: float = 0.0
    latency_ms_p95: float = 0.0
    samples: int = 0


class AiResourcesOut(BaseModel):
    """Uso de recursos do processo/sistema (nulos se indisponível)."""

    cpu_percent: float | None = None
    memory_mb: float | None = None
    memory_percent: float | None = None
    system_cpu_percent: float | None = None


class AiStatusOut(BaseModel):
    """Retrato completo do motor de IA para o painel "AI Core"."""

    signature: str = "Alaris Core v1.0"
    engine: AiEngineOut
    throughput: AiThroughputOut
    performance: AiPerformanceOut
    resources: AiResourcesOut
    cameras_enabled: int = 0
    cameras_online: int = 0
    uptime_seconds: float = 0.0
    started_at: float | None = None
    generated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )


class AiLogOut(BaseModel):
    """Um "pensamento" da IA no log cognitivo em tempo real."""

    id: int
    timestamp: float
    hora: str
    # info | analise | sucesso | atencao | alerta
    level: str = "info"
    source: str | None = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class AiLogsOut(BaseModel):
    """Resposta incremental do log cognitivo (para polling do painel)."""

    entries: list[AiLogOut] = Field(default_factory=list)
    last_id: int = 0
    generated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )


class StreamStatsOut(BaseModel):
    """Estado em tempo real de um stream (Alaris Core distribuído)."""

    camera_id: str
    name: str = ""
    location_label: str | None = None
    source_type: str | None = None
    is_active: bool = True
    # idle | connecting | online | reconnecting | error | stopped
    status: str = "idle"
    fps: float = 0.0
    backend: str | None = None
    active_birds: int = 0
    # Espécies distintas rastreadas neste instante (cards de status do painel).
    active_species: list[str] = Field(default_factory=list)
    individuals_peak: int = 0
    inferences: int = 0
    last_error: str | None = None
