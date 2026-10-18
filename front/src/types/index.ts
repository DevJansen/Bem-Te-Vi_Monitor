/** Tipos do domínio Bem-Ti-Vi (alinhados à API FastAPI local). */

export type CameraId = string;

export type CameraStatus =
  | "idle"
  | "connecting"
  | "online"
  | "reconnecting"
  | "error"
  | "stopped"
  | "disabled";

export type SourceType = "usb" | "rtsp" | "onvif" | "hls" | "http" | "webrtc";

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
  stream_url: string;
  location_label: string | null;
  /** Coordenadas do jardim (câmeras globais/remotas), quando cadastradas. */
  latitude?: number | null;
  longitude?: number | null;
  /** Fuso horário IANA da câmera (ex.: "America/Costa_Rica"). */
  timezone?: string | null;
  country?: string | null;
  has_credentials: boolean;
  is_active: boolean;
  /** Alaris Core (IA visual - YOLOv8 + gravação) ativo nesta câmera. */
  ai_enabled?: boolean;
  /** Monitoramento contínuo de áudio com BirdNET ativo nesta câmera. */
  audio_enabled?: boolean;
  zones: Zone[];
  status: CameraStatus | string;
  /** Indica se a câmera está processando quadros em visão noturna (IR/baixa luz). */
  night_mode?: boolean;
  created_at: string;
  updated_at: string;
};

export type CameraCreatePayload = {
  name: string;
  source_type: SourceType;
  stream_url: string;
  location_label?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  timezone?: string | null;
  country?: string | null;
  username?: string | null;
  password?: string | null;
  enabled?: boolean;
  ai_enabled?: boolean;
  audio_enabled?: boolean;
  zones?: Zone[];
};

export type CameraUpdatePayload = {
  name?: string;
  source_type?: SourceType;
  stream_url?: string;
  location_label?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  timezone?: string | null;
  country?: string | null;
  username?: string | null;
  password?: string | null;
  enabled?: boolean;
  ai_enabled?: boolean;
  audio_enabled?: boolean;
  zones?: Zone[];
  clear_credentials?: boolean;
  /** Apaga a localização geográfica da câmera. */
  clear_location?: boolean;
};

/** Clima e horário **locais** de uma câmera global/remota (Open-Meteo). */
export type CameraWeather = {
  available: boolean;
  latitude: number | null;
  longitude: number | null;
  timezone: string | null;
  utc_offset_seconds: number | null;
  local_time: string | null;
  local_time_label: string | null;
  temperature: number | null;
  humidity: number | null;
  wind_speed: number | null;
  condition: string;
  category: string;
  icon: string;
  weather_code: number | null;
  is_day: boolean | null;
  fetched_at: string | null;
  source: string;
};

/** Localidade candidata do "seletor de cidade inteligente". */
export type GeoLocation = {
  name: string;
  country: string | null;
  admin1: string | null;
  latitude: number;
  longitude: number;
  timezone: string | null;
  label: string;
};

/** Estado em tempo real de um stream (Alaris Core distribuído). */
export type StreamStats = {
  camera_id: string;
  name: string;
  location_label: string | null;
  source_type: string | null;
  is_active: boolean;
  status: string;
  fps: number;
  backend: string | null;
  active_birds: number;
  /** Espécies distintas rastreadas neste instante (cards de status do Alaris). */
  active_species: string[];
  individuals_peak: number;
  inferences: number;
  last_error: string | null;
};

export type OfflineJobStatus = "queued" | "processing" | "completed" | "error";

/** Uma ave distinta identificada ao longo de um vídeo importado. */
export type OfflineDetection = {
  id: string;
  timestamp_seconds: number;
  species: string;
  confidence: number;
  thumbnail_url: string | null;
  crop_url: string | null;
  visit_id: string | null;
};

/** Estado completo de um upload/análise offline (persistido no backend). */
export type OfflineJob = {
  id: string;
  camera_id: CameraId;
  camera_name: string | null;
  filename: string;
  status: OfflineJobStatus;
  progress: number;
  frames_processed: number;
  total_frames: number;
  progress_message: string;
  birds_detected_count: number;
  detections: OfflineDetection[];
  summary: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
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
  /** "bird" para aves; "mammal"/"other" para Visitantes Especiais (esquilos…). */
  visitor_kind: string;
  /** Grupo divertido do visitante (ex.: "esquilo"). */
  visitor_group: string | null;
  /** Segmentação por Jardim: rótulo amigável do jardim no momento da captura. */
  location_label: string | null;
  /** Condições do tempo no momento da visita (Open-Meteo). */
  temperature: number | null;
  humidity: number | null;
  weather_code: string | null;
  wind_speed: number | null;
  metadata: {
    crop_path?: string | null;
    identification_status?: string;
    /** Se a captura ocorreu com o realce de visão noturna ativo. */
    night_mode?: boolean;
    /** Se a foto oficial passou pelo pipeline de melhoria (CLAHE + ruído). */
    enhanced?: boolean;
    /** Duração aproximada do clipe (s): pré + pós-evento. */
    clip_seconds?: number;
    /** Notas do quadro escolhido (nitidez, confiança e enquadramento). */
    best_frame_score?: number;
    best_frame_sharpness?: number;
    best_frame_area_ratio?: number;
    best_frame_confidence?: number;
    /** Falso quando todos os quadros eram desfoque (fallback). */
    best_frame_sharpness_ok?: boolean;
    /** Contagem de indivíduos/bandos da janela da visita. */
    individuals_total?: number;
    individuals_peak?: number;
    individuals_by_species?: Record<string, number>;
    individuals_by_class?: Record<string, number>;
    /** Frase do bando no pico (ex.: "3 Cambacicas e 2 Saíras"). */
    individuals_summary?: string;
    /** Comportamento predominante: "feeding" | "perching" | "moving". */
    behavior?: string;
    behavior_label?: string;
    behavior_icon?: string;
    behavior_zone?: string | null;
    /** Ajuste de sensibilidade aplicado pela IA conforme clima/horário. */
    context_adjustment?: {
      confidence: number;
      tta: boolean;
      adaptive_contrast: boolean;
      reasons: string[];
    };
    /** Backend de inferência em uso (tensorrt | onnx | pytorch). */
    inference_backend?: string;
    /** Status ecológico regional (avifauna do Sul do Brasil / SC). */
    ecological?: {
      status: string;
      label: string;
      badge: string;
      icon: string;
    };
    external_identification?: {
      scientific_name: string;
      common_name: string;
      /** Imagem tratada usada na identificação: "recorte" ou "thumbnail". */
      image_source?: string;
    };
    /** Análise enriquecida gerada pela IA ("laudo" da visita + anotação). */
    ai_analysis?: {
      /** Motor de IA que gerou a análise (assinatura Alaris). */
      engine?: string;
      species?: string | null;
      scientific_name?: string | null;
      individuals_peak?: number | null;
      ecological_status?: string | null;
      ecological_label?: string | null;
      ecological_badge?: string | null;
      behavior?: string | null;
      behavior_label?: string | null;
      confidence?: number | null;
      sharpness?: number | null;
      temperature?: number | null;
      weather?: string | null;
      /** Anotação ornitológica em pt-BR escrita automaticamente pela IA. */
      annotation: string;
    };
    /** Ficha ornitológica profunda em cache (consulta da IA externa). */
    ai_consult?: SpeciesAiConsult;
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
  /** Status ecológico regional (avifauna do Sul do Brasil / SC). */
  ecological_status?: string | null;
  ecological_status_label?: string | null;
  ecological_badge?: string | null;
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
  // --- Visitantes Especiais / Convidados do Jardim (Modo Esquilo) ---
  visitors_today: number;
  squirrel_visits_today: number;
  seeds_stolen_today: number;
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

export type GardenToday = {
  camera_id: string;
  garden: string;
  camera_name: string | null;
  visits: number;
  species_counts: Record<string, number>;
  visits_by_hour: Record<string, number>;
};

export type TodayByGarden = {
  date: string;
  consolidated_visits: number;
  consolidated_species_counts: Record<string, number>;
  consolidated_visits_by_hour: Record<string, number>;
  gardens: GardenToday[];
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
  /** Status ecológico regional (avifauna do Sul do Brasil / SC). */
  ecological_status?: string | null;
  ecological_status_label?: string | null;
  ecological_badge?: string | null;
};

/** Uma avistagem individual dentro da ficha da espécie (histórico recente). */
export type SpeciesSighting = {
  visit_id: string;
  detected_at: string;
  confidence: number;
  thumbnail_url: string | null;
  /** Recorte tratado pelo Alaris Core (close-up da ave). */
  crop_url: string | null;
  temperature: number | null;
  humidity: number | null;
  weather_code: string | null;
  dwell_seconds: number;
};

/** Visitas da espécie em um horário do dia (histograma de pico). */
export type SpeciesHourStat = {
  hour: string;
  visits: number;
  avg_temperature: number | null;
};

/** Visitas da espécie sob uma condição meteorológica (Open-Meteo). */
export type SpeciesWeatherStat = {
  condition: string;
  visits: number;
  avg_temperature: number | null;
};

/** Ficha técnica completa de uma espécie (Minhas Aves / Álbum de Conquistas). */
export type SpeciesProfile = {
  id: string;
  common_name: string;
  scientific_name: string;
  description: string;
  reference_image_url: string | null;
  created_at: string;
  visits_count: number;
  first_seen_at: string | null;
  last_seen_at: string | null;
  active_days: number;
  average_dwell_seconds: number | null;
  best_photo_url: string | null;
  rarity: RarityTier;
  badges: string[];
  ecological_status: string | null;
  ecological_status_label: string | null;
  ecological_badge: string | null;
  /** Observação curada da base regional (habitat/sazonalidade). */
  ecological_notes: string | null;
  peak_hour: string | null;
  hourly_distribution: SpeciesHourStat[];
  avg_temperature: number | null;
  min_temperature: number | null;
  max_temperature: number | null;
  avg_humidity: number | null;
  weather_distribution: SpeciesWeatherStat[];
  recent_sightings: SpeciesSighting[];
  /** Ficha ornitológica da IA externa em cache (quando já consultada). */
  ai_consult?: SpeciesAiConsult | null;
};

/** Ficha ornitológica profunda retornada pela IA externa (Gemini/OpenAI). */
export type SpeciesAiConsult = {
  scientific_name: string;
  common_name: string;
  family: string;
  order: string;
  conservation_status: string;
  diet: string;
  feeding_behavior: string;
  habitat: string;
  distribution: string;
  biogeography: string;
  migration: string;
  size_cm: string;
  weight_g: string;
  lifespan: string;
  curiosities: string[];
  notes: string;
  provider: string | null;
  model: string | null;
  image_source: string | null;
  generated_at: string | null;
  cached: boolean;
};

/** Anomalia acústico-visual (ex.: espécie que reaparece após meses ausente). */
export type Anomaly = {
  id: string;
  kind: string;
  created_at: string;
  species: string;
  scientific_name: string | null;
  days_absent: number | null;
  message: string;
  visit_id: string | null;
  acknowledged: boolean;
  details: Record<string, unknown>;
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
  /** Medalha secreta: só revela nome/descrição após desbloqueada. */
  secret: boolean;
};

export type CollectorLevel = {
  level: number;
  title: string;
  species_count: number;
  next_threshold: number | null;
  next_title: string | null;
  progress_to_next: number;
};

export type BioacousticsCross = {
  id: string;
  detected_at: string;
  camera_id: string;
  location_label: string | null;
  especie_audio: string;
  especie_visual: string | null;
  especies: string[];
  confianca_audio: number;
  confianca_visual: number | null;
  confianca_combinada: number;
  linked_visit_id: string | null;
  thumbnail_path: string | null;
};

export type BioacousticsSummary = {
  camera_id: string;
  total_deteccoes_audio: number;
  especies_ouvida: string[];
  especies_vista: string[];
  especies_confirmadas: string[];
  especies_so_audio: string[];
};

export type WildlifeVisitorStat = {
  group: string;
  label: string;
  icon: string;
  gallery_category: string;
  visits: number;
  last_seen_at: string | null;
  /** Consumo estimado (brincadeira): sementes/petiscos levados. */
  estimated_consumption: number;
  unit: string;
};

export type WildlifeSummary = {
  total_visits: number;
  visits_today: number;
  visitors_today: number;
  squirrel_visits_today: number;
  seeds_stolen_today: number;
  seeds_stolen_total: number;
  first_visit_at: string | null;
  has_visitors: boolean;
  squirrel_badge_unlocked: boolean;
  groups: WildlifeVisitorStat[];
  generated_at: string;
};

/** Resumo do dia (time-lapse) gerado a partir dos clipes das visitas. */
export type Timelapse = {
  filename: string;
  /** Dia de referência no formato `YYYY-MM-DD`. */
  day: string;
  /** URL de streaming pronta para o player. */
  url: string;
  size_bytes: number;
  duration_seconds: number | null;
  clips_count: number;
  speed: number;
  generated_at: string | null;
};

/** Resultado da geração sob demanda de um resumo do dia. */
export type TimelapseGenerateResult = {
  status: "generated" | "exists" | "empty" | "unavailable";
  message: string;
  timelapse: Timelapse | null;
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

/** Modo da visão noturna (infravermelho / baixa luz). */
export type NightVisionMode = "auto" | "on" | "off";

export type Calibration = {
  yolo_confidence: number;
  object_persistence_time: number;
  motion_sensitivity: number;
  /** Modo de realce para quadros escuros / infravermelho. */
  night_vision_mode: NightVisionMode;
  /** Luminância média (0-255) que separa "claro" de "escuro" no modo automático. */
  night_vision_threshold: number;
  /** Expansão opcional das classes detectadas (fauna noturna além de aves). */
  night_fauna_enabled: boolean;
  profile: CalibrationProfile;
  recommended_profile: CalibrationProfile;
};

export type CalibrationUpdate = {
  profile?: CalibrationProfile;
  yolo_confidence?: number;
  object_persistence_time?: number;
  motion_sensitivity?: number;
  night_vision_mode?: NightVisionMode;
  night_vision_threshold?: number;
  night_fauna_enabled?: boolean;
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
  /** Provedor efetivo: "google" (Gemini oficial) ou "openai" (compatível). */
  ai_external_provider: string;
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
  ai_external_provider?: string;
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

/** Resumo de uma faixa de temperatura (visitas, espécies e horário médio). */
export type TemperatureRangeInsight = {
  label: string;
  min_temperature: number | null;
  max_temperature: number | null;
  visits: number;
  distinct_species: number;
  active_days: number;
  visits_per_day: number;
  avg_hour: number | null;
  avg_hour_label: string | null;
  avg_temperature: number | null;
  avg_humidity: number | null;
  top_species: string | null;
};

/** Visitas agrupadas por categoria ampla de clima (com visitas por dia). */
export type WeatherConditionInsight = {
  condition: string;
  icon: string;
  visits: number;
  distinct_species: number;
  active_days: number;
  visits_per_day: number;
  avg_hour: number | null;
  avg_hour_label: string | null;
  avg_temperature: number | null;
  avg_humidity: number | null;
  top_species: string | null;
};

/** Período (mais frio / mais quente) com horário médio de aparecimento. */
export type TemperaturePeriodInsight = {
  period: string;
  label: string;
  visits: number;
  distinct_species: number;
  active_days: number;
  visits_per_day: number;
  avg_hour: number | null;
  avg_hour_label: string | null;
  avg_temperature: number | null;
  avg_humidity: number | null;
  top_species: string | null;
};

/** Mudança de horário de uma espécie entre condições frias e quentes. */
export type SpeciesWeatherTiming = {
  species: string;
  scientific_name: string | null;
  cold_avg_hour: number | null;
  hot_avg_hour: number | null;
  cold_visits: number;
  hot_visits: number;
  minutes_earlier: number | null;
  direction: "earlier" | "later" | "similar" | string;
  summary: string;
};

/** Card de resumo inteligente exibido no painel de insights. */
export type InsightCard = {
  id: string;
  icon: string;
  title: string;
  description: string;
  tone: "positive" | "info" | "warning" | "neutral" | string;
};

/** Insights avançados que cruzam visitas com clima e hábitos. */
export type WeatherInsights = {
  total_visits: number;
  visits_with_weather: number;
  cold_threshold_celsius: number | null;
  temperature_ranges: TemperatureRangeInsight[];
  best_temperature_range: TemperatureRangeInsight | null;
  conditions: WeatherConditionInsight[];
  rainy: WeatherConditionInsight | null;
  dry: WeatherConditionInsight | null;
  rainy_vs_dry_percent: number | null;
  periods: TemperaturePeriodInsight[];
  species_timing: SpeciesWeatherTiming[];
  insights: InsightCard[];
  generated_at: string;
};

/* ——— Motor de IA (AI Core) ——— */

/** Estado do modelo/inferência em uso (Edge AI). */
export type AiEngine = {
  state: string;
  model: string | null;
  backend: string | null;
  device: string | null;
  imgsz: number | null;
  confidence: number | null;
  notes: string[];
};

/** Volume de trabalho do motor (FPS, inferências e detecções). */
export type AiThroughput = {
  fps: number;
  inferences_today: number;
  inferences_total: number;
  detections_today: number;
  detections_total: number;
  frames_analyzed: number;
};

/** Latência da inferência (ms). */
export type AiPerformance = {
  latency_ms_last: number;
  latency_ms_avg: number;
  latency_ms_min: number;
  latency_ms_max: number;
  latency_ms_p95: number;
  samples: number;
};

/** Uso de recursos do processo/sistema (nulos se indisponível). */
export type AiResources = {
  cpu_percent: number | null;
  memory_mb: number | null;
  memory_percent: number | null;
  system_cpu_percent: number | null;
};

/** Retrato completo do motor de IA (endpoint GET /api/ai/status). */
export type AiStatusSnapshot = {
  signature?: string;
  engine: AiEngine;
  throughput: AiThroughput;
  performance: AiPerformance;
  resources: AiResources;
  cameras_enabled: number;
  cameras_online: number;
  uptime_seconds: number;
  started_at: number | null;
  generated_at: string;
};

/** Nível de um "pensamento" da IA (orienta a cor no painel). */
export type AiLogLevel = "info" | "analise" | "sucesso" | "atencao" | "alerta";

/** Um "pensamento" da IA no log cognitivo em tempo real. */
export type AiLogEntry = {
  id: number;
  timestamp: number;
  hora: string;
  level: AiLogLevel | string;
  source: string | null;
  message: string;
  data: Record<string, unknown>;
};

/** Resposta incremental do log cognitivo (polling do painel). */
export type AiLogsResponse = {
  entries: AiLogEntry[];
  last_id: number;
  generated_at: string;
};
