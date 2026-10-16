/** Tipos do domínio AviaWatch (alinhados à API FastAPI local). */

export type CameraId = string;

export type SourceType = "usb" | "rtsp" | "onvif";

export type CameraStatus =
  | "idle"
  | "connecting"
  | "online"
  | "reconnecting"
  | "error"
  | "stopped"
  | "disabled";

export type AppTab =
  | "dashboard"
  | "cameras"
  | "gallery"
  | "species"
  | "analytics"
  | "settings";

export type ZonePoint = {
  x: number;
  y: number;
};

export type ZoneMode = "include" | "exclude";

export type Zone = {
  id: string;
  name: string;
  points: ZonePoint[];
  mode: ZoneMode;
  min_dwell_seconds: number;
  cooldown_seconds: number;
  absence_tolerance_seconds: number;
  enabled: boolean;
};

/**
 * Tipo de zona de interesse (ROI):
 * - `include`: monitorar — só registra visitas dentro do retângulo.
 * - `exclude`: ignorar — descarta detecções dentro do retângulo.
 */
export type RoiType = "include" | "exclude";

/** Retângulo de interesse com coordenadas normalizadas (0..1). */
export type RoiZone = {
  id: string;
  name: string;
  type: RoiType;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

/** Conjunto de zonas de interesse de uma câmera. */
export type RoiSettings = {
  camera_id?: string | null;
  zones: RoiZone[];
};

export type Camera = {
  id: CameraId;
  name: string;
  source_type: SourceType;
  source_uri: string;
  has_credentials: boolean;
  enabled: boolean;
  zones: Zone[];
  status: CameraStatus | string;
  created_at: string;
  updated_at: string;
};

export type CameraCreatePayload = {
  name: string;
  source_type: SourceType;
  source_uri: string;
  username?: string | null;
  password?: string | null;
  enabled?: boolean;
  zones?: Zone[];
};

export type CameraUpdatePayload = {
  name?: string;
  source_type?: SourceType;
  source_uri?: string;
  username?: string | null;
  password?: string | null;
  enabled?: boolean;
  zones?: Zone[];
  clear_credentials?: boolean;
};

export type RecordingAnalysisStatus =
  | "queued"
  | "processing"
  | "completed"
  | "failed";

export type RecordingAnalysis = {
  id: string;
  camera_id: CameraId;
  filename: string;
  status: RecordingAnalysisStatus;
  progress: number;
  visits_created: number;
  error: string | null;
};

export type BirdVisit = {
  id: string;
  camera_id: CameraId;
  camera_name: string | null;
  species: string;
  confidence: number;
  detected_at: string;
  dwell_seconds: number;
  clip_path: string | null;
  thumbnail_path: string | null;
  clip_url: string | null;
  thumbnail_url: string | null;
  bbox: number[] | null;
  zone_id: string | null;
  species_id: string | null;
  assigned_species_common_name: string | null;
  assigned_species_scientific_name: string | null;
  /** Condições do tempo no momento da visita (Open-Meteo). */
  temperature: number | null;
  humidity: number | null;
  weather_code: string | null;
  wind_speed: number | null;
  metadata: {
    crop_path?: string | null;
    identification_status?: string;
    external_identification?: {
      scientific_name: string;
      common_name: string;
    };
    [key: string]: unknown;
  };
};

export type BirdSpecies = {
  id: string;
  common_name: string;
  scientific_name: string;
  description: string;
  reference_image_path: string | null;
  reference_image_url: string | null;
  created_at: string;
};

export type BirdSpeciesCreatePayload = {
  common_name: string;
  scientific_name: string;
  description: string;
  reference_image?: File | null;
};

export type HistoryDeletionResult = {
  deleted_records: number;
  deleted_media_files: number;
  failed_records: string[];
  failed_media_files: string[];
};

export type Metrics = {
  total_visits: number;
  visits_today: number;
  active_cameras: number;
  total_cameras: number;
  species_counts: Record<string, number>;
  visits_by_hour: Record<string, number>;
  last_visit_at: string | null;
  generated_at: string;
};

export type AnalyticsSummary = {
  visits_today: number;
  visits_last_7_days: number;
  total_visits: number;
  most_frequent_species: string | null;
  most_frequent_species_count: number;
  average_duration_seconds: number;
  peak_hour: string | null;
};

export type HourlyDistribution = {
  hour: string;
  visits: number;
};

export type LifeListSpecies = {
  id: string;
  common_name: string;
  scientific_name: string;
  description: string;
  is_unlocked: boolean;
  first_seen_at: string | null;
  featured_photo_url: string | null;
  reference_image_url: string | null;
  sightings_count: number;
  /** Campos gamificados do álbum de figurinhas. */
  visits_count: number;
  rarity: RarityTier;
  best_photo_url: string | null;
  badges: string[];
};

/** Raridade da espécie no álbum, conforme o nº de avistagens. */
export type RarityTier = "Comum" | "Incomum" | "Rara" | "Não observada";

/** Medalha/marco conquistado pelo observador. */
export type Achievement = {
  id: string;
  name: string;
  description: string;
  icon: string;
  target: number;
  progress: number;
  unlocked: boolean;
};

export type AppSettings = {
  telegram_configured: boolean;
  discord_configured: boolean;
  yolo_model: string;
  yolo_confidence: number;
  pre_record_seconds: number;
  post_record_seconds: number;
  audio_analysis_enabled: boolean;
  audio_confidence_threshold: number;
  audio_input_device: string;
  notifications_enabled: boolean;
  notify_mode: string;
  min_confidence_notify: number;
  extra: Record<string, unknown>;
};

export type AppSettingsUpdate = {
  notifications_enabled?: boolean;
  notify_mode?: string;
  min_confidence_notify?: number;
  yolo_confidence?: number;
  pre_record_seconds?: number;
  post_record_seconds?: number;
  audio_analysis_enabled?: boolean;
  audio_confidence_threshold?: number;
  audio_input_device?: string;
  extra?: Record<string, unknown>;
};

export type CalibrationProfile = "stationary" | "fast_motion" | "custom";

export type Calibration = {
  yolo_confidence: number;
  object_persistence_time: number;
  motion_sensitivity: number;
  profile: CalibrationProfile;
  recommended_profile: CalibrationProfile;
};

export type CalibrationUpdate = {
  profile?: CalibrationProfile;
  yolo_confidence?: number;
  object_persistence_time?: number;
  motion_sensitivity?: number;
};

export type AudioDetection = {
  id: string;
  event_type: "AUDIO_DETECTION";
  camera_id: string;
  camera_name: string;
  detected_at: string;
  species: string;
  scientific_name: string;
  confidence: number;
  linked_visit_id: string | null;
  /** Condições do tempo no momento da detecção sonora (Open-Meteo). */
  temperature: number | null;
  humidity: number | null;
  weather_code: string | null;
  wind_speed: number | null;
};

export type AudioAnalysisStatus = {
  enabled: boolean;
  status: "disabled" | "starting" | "monitoring" | "no_cameras" | "error";
  message: string;
  monitored_cameras: number;
};

/** Dispositivo de entrada de áudio disponível no sistema. */
export type AudioInputDevice = {
  name: string;
  identifier: string | null;
};

/** Lista de dispositivos de áudio para o seletor das configurações. */
export type AudioInputDevices = {
  platform: string;
  devices: AudioInputDevice[];
  selected: string;
};

export type HealthResponse = {
  status: string;
  service: string;
};

export type AiStatus = "online" | "degraded" | "offline" | "loading";

export type NotificationChannel = "telegram" | "discord";

export type EnvironmentIntegration = "telegram" | "discord" | "ai_external";

export type EnvironmentSettings = {
  telegram_bot_token: string | null;
  telegram_chat_id: string | null;
  discord_webhook_url: string | null;
  ai_external_api_key: string | null;
  ai_external_base_url: string;
  ai_external_model: string;
  telegram_bot_token_configured: boolean;
  telegram_chat_id_configured: boolean;
  discord_webhook_url_configured: boolean;
  ai_external_api_key_configured: boolean;
  telegram_configured: boolean;
  discord_configured: boolean;
  ai_external_configured: boolean;
};

export type EnvironmentSettingsUpdate = {
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  discord_webhook_url?: string;
  ai_external_api_key?: string;
  ai_external_base_url?: string;
  ai_external_model?: string;
  clear_telegram?: boolean;
  clear_discord?: boolean;
  clear_ai_external?: boolean;
};

/** Clima atual do local do alimentador (integração Open-Meteo). */
export type CurrentWeather = {
  available: boolean;
  temperature: number | null;
  humidity: number | null;
  wind_speed: number | null;
  condition: string;
  category: string;
  icon: string;
  weather_code: number | null;
  fetched_at: string | null;
  source: string;
};

/** Visitas agrupadas por condição/categoria meteorológica. */
export type WeatherConditionStat = {
  condition: string;
  visits: number;
  avg_temperature: number | null;
  avg_humidity: number | null;
  avg_wind_speed: number | null;
};

/** Horário de pico e temperatura média das visitas nesse horário. */
export type WeatherHourStat = {
  hour: string;
  visits: number;
  avg_temperature: number | null;
};

/** Cruzamento entre frequência de visitas e condições do tempo. */
export type WeatherCorrelation = {
  total_visits: number;
  visits_with_weather: number;
  avg_temperature_on_visits: number | null;
  min_temperature_on_visits: number | null;
  max_temperature_on_visits: number | null;
  by_condition: WeatherConditionStat[];
  by_category: WeatherConditionStat[];
  peak_hours: WeatherHourStat[];
};
