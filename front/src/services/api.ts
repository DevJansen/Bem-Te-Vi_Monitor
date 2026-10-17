import axios, { type AxiosError } from "axios";
import type {
  Achievement,
  AiLogsResponse,
  AiStatusSnapshot,
  Anomaly,
  AppSettings,
  StreamStats,
  AppSettingsUpdate,
  AnalyticsSummary,
  AudioAnalysisStatus,
  AudioDetection,
  AudioInputDevices,
  BirdSpecies,
  BirdSpeciesCreatePayload,
  BirdVisit,
  Calibration,
  CalibrationUpdate,
  Camera,
  CameraCreatePayload,
  CameraUpdatePayload,
  CameraWeather,
  CurrentWeather,
  EnvironmentIntegration,
  EnvironmentSettings,
  EnvironmentSettingsUpdate,
  GeoLocation,
  HealthResponse,
  HistoryDeletionResult,
  HourlyDistribution,
  LifeListSpecies,
  Metrics,
  NotificationChannel,
  OfflineJob,
  RoiSettings,
  RoiZone,
  SpeciesAiConsult,
  SpeciesProfile,
  Timelapse,
  TimelapseGenerateResult,
  TodayByGarden,
  WeatherCorrelation,
  WeatherInsights,
  WildlifeSummary,
  CollectorLevel,
  BioacousticsCross,
  BioacousticsSummary,
  Zone,
} from "@/types";

/** Cliente Axios apontando para a API FastAPI local (proxy Vite → :8000). */
export const api = axios.create({
  baseURL: "/api",
  timeout: 20_000,
  headers: {
    "Content-Type": "application/json",
  },
});

export function getErrorMessage(error: unknown, fallback = "Erro inesperado"): string {
  if (axios.isAxiosError(error)) {
    const ax = error as AxiosError<{
      detail?: string | Array<{ msg?: string; loc?: unknown }>;
    }>;
    const detail = ax.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (first?.msg) return first.msg;
    }
    if (ax.code === "ERR_NETWORK") {
      return "Não foi possível conectar à API. Confirme se o backend está em http://127.0.0.1:8000";
    }
    if (ax.message) return ax.message;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

export async function fetchApiHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/health");
  return data;
}

/* ——— Câmeras ——— */

export async function listCameras(): Promise<Camera[]> {
  const { data } = await api.get<Camera[]>("/cameras");
  return data;
}

export async function getCamera(id: string): Promise<Camera> {
  const { data } = await api.get<Camera>(`/cameras/${id}`);
  return data;
}

export async function createCamera(payload: CameraCreatePayload): Promise<Camera> {
  const { data } = await api.post<Camera>("/cameras", payload);
  return data;
}

export async function updateCamera(
  id: string,
  payload: CameraUpdatePayload,
): Promise<Camera> {
  const { data } = await api.put<Camera>(`/cameras/${id}`, payload);
  return data;
}

export async function getCameraZones(id: string): Promise<Zone[]> {
  const { data } = await api.get<{ zones: Zone[] }>(`/cameras/${id}/zones`);
  return data.zones;
}

/**
 * Clima e horário **locais** do jardim de uma câmera global/remota.
 *
 * Devolve `available: false` quando a câmera não tem coordenadas cadastradas ou
 * quando não há internet — o painel apenas oculta o widget nesse caso.
 */
export async function getCameraWeather(id: string): Promise<CameraWeather> {
  const { data } = await api.get<CameraWeather>(
    `/cameras/${encodeURIComponent(id)}/weather`,
  );
  return data;
}

/**
 * Seletor de cidade inteligente: resolve um nome de cidade/país em coordenadas
 * e fuso horário (IANA) via Open-Meteo. Devolve `[]` quando nada é encontrado.
 */
export async function geocodeLocation(query: string): Promise<GeoLocation[]> {
  const { data } = await api.get<GeoLocation[]>("/weather/geocode", {
    params: { q: query },
  });
  return data;
}

export async function saveCameraZones(id: string, zones: Zone[]): Promise<Zone[]> {
  const { data } = await api.put<{ zones: Zone[] }>(`/cameras/${id}/zones`, {
    zones,
  });
  return data.zones;
}

/* ——— Zonas de interesse (ROI) ——— */

/** Busca as zonas de interesse (ROI) salvas para a câmera. */
export async function fetchRoi(cameraId: string): Promise<RoiZone[]> {
  const { data } = await api.get<RoiSettings>("/settings/roi", {
    params: { camera_id: cameraId },
  });
  return data.zones ?? [];
}

/** Salva as zonas de interesse (ROI) da câmera. */
export async function saveRoi(
  cameraId: string,
  zones: RoiZone[],
): Promise<RoiZone[]> {
  const { data } = await api.post<RoiSettings>("/settings/roi", {
    camera_id: cameraId,
    zones,
  });
  return data.zones ?? [];
}

export async function deleteCamera(id: string): Promise<void> {
  await api.delete(`/cameras/${id}`);
}

/* ——— Multi-Câmera / Streams (Central de Câmeras) ——— */

/** Estado em tempo real de cada stream (Alaris Core distribuído). */
export async function fetchStreams(): Promise<StreamStats[]> {
  const { data } = await api.get<StreamStats[]>("/streams");
  return data;
}

/**
 * URL do proxy seguro de vídeo. O front-end NUNCA usa a URL real da câmera:
 * o backend descriptografa as credenciais em memória e retransmite os quadros.
 */
export function streamProxyUrl(cameraId: string): string {
  return `/api/streams/proxy/${encodeURIComponent(cameraId)}`;
}

export async function uploadOfflineVideo(
  file: File,
  cameraId: string,
  onUploadProgress: (percent: number) => void,
): Promise<OfflineJob> {
  const form = new FormData();
  form.append("file", file);
  form.append("camera_id", cameraId);
  form.append("recorded_at", new Date(file.lastModified || Date.now()).toISOString());
  const { data } = await api.post<OfflineJob>("/offline/upload", form, {
    timeout: 0,
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (event.total) {
        onUploadProgress(Math.round((event.loaded / event.total) * 100));
      }
    },
  });
  return data;
}

/** Estado de todos os jobs de análise offline (em andamento e concluídos). */
export async function fetchOfflineJobs(): Promise<OfflineJob[]> {
  const { data } = await api.get<OfflineJob[]>("/offline/jobs");
  return data;
}

export async function fetchOfflineJob(id: string): Promise<OfflineJob> {
  const { data } = await api.get<OfflineJob>(
    `/offline/jobs/${encodeURIComponent(id)}`,
  );
  return data;
}

export async function deleteOfflineJob(id: string): Promise<void> {
  await api.delete(`/offline/jobs/${encodeURIComponent(id)}`);
}

/** Limpa do histórico todos os jobs já finalizados. Retorna quantos saíram. */
export async function clearFinishedOfflineJobs(): Promise<number> {
  const { data } = await api.post<{ removed: number }>("/offline/jobs/clear");
  return data.removed;
}

/* ——— Visitas ——— */

export async function listVisits(params?: {
  limit?: number;
  offset?: number;
  camera_id?: string;
  species?: string;
}): Promise<BirdVisit[]> {
  const { data } = await api.get<BirdVisit[]>("/visits", { params });
  return data;
}

export async function deleteVisit(id: string): Promise<void> {
  await api.delete(`/events/${encodeURIComponent(id)}`);
}

export async function deleteOlderVisits(
  olderThanDays: number,
): Promise<HistoryDeletionResult> {
  const { data } = await api.delete<HistoryDeletionResult>("/events", {
    params: { older_than_days: olderThanDays },
  });
  return data;
}

export async function deleteAllVisits(): Promise<HistoryDeletionResult> {
  const { data } = await api.delete<HistoryDeletionResult>("/events/all", {
    data: { confirmation: "EXCLUIR TUDO" },
  });
  return data;
}

export async function getVisit(id: string): Promise<BirdVisit> {
  const { data } = await api.get<BirdVisit>(`/visits/${id}`);
  return data;
}

export async function identifyVisitExternal(
  id: string,
  options?: { addToCatalog?: boolean },
): Promise<BirdVisit> {
  const { data } = await api.post<BirdVisit>(
    `/visits/${encodeURIComponent(id)}/identify-external`,
    undefined,
    options?.addToCatalog
      ? { params: { add_to_catalog: true } }
      : undefined,
  );
  return data;
}

export async function assignVisitSpecies(
  visitId: string,
  speciesId: string | null,
): Promise<BirdVisit> {
  const { data } = await api.put<BirdVisit>(
    `/visits/${encodeURIComponent(visitId)}/assign-species`,
    { species_id: speciesId },
  );
  return data;
}

/**
 * Consulta detalhada da espécie na IA externa (Google Gemini / compatível).
 *
 * O backend monta um *prompt* ornitológico rico e devolve a ficha formatada
 * (família, conservação, dieta, habitat, curiosidades, biogeografia). O
 * resultado fica em cache nos metadados da visita; `refresh` força nova consulta.
 */
export async function askVisitAi(
  visitId: string,
  refresh = false,
): Promise<SpeciesAiConsult> {
  const { data } = await api.post<SpeciesAiConsult>(
    `/visits/${encodeURIComponent(visitId)}/ask-ai`,
    undefined,
    { params: refresh ? { refresh: true } : undefined, timeout: 60_000 },
  );
  return data;
}

/* ——— Catálogo local de espécies ——— */

export async function listSpecies(): Promise<BirdSpecies[]> {
  const { data } = await api.get<BirdSpecies[]>("/species");
  return data;
}

export async function createSpecies(
  payload: BirdSpeciesCreatePayload,
): Promise<BirdSpecies> {
  const form = new FormData();
  form.append("common_name", payload.common_name);
  form.append("scientific_name", payload.scientific_name);
  form.append("description", payload.description);
  if (payload.reference_image) {
    form.append("reference_image", payload.reference_image);
  }
  const { data } = await api.post<BirdSpecies>("/species", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function deleteSpecies(id: string): Promise<void> {
  await api.delete(`/species/${encodeURIComponent(id)}`);
}

/**
 * Ficha técnica completa de uma espécie (histórico, horários de pico,
 * temperatura média preferida, notas científicas e status ecológico).
 */
export async function fetchSpeciesProfile(
  speciesId: string,
): Promise<SpeciesProfile> {
  const { data } = await api.get<SpeciesProfile>(
    `/species/${encodeURIComponent(speciesId)}/profile`,
  );
  return data;
}

/**
 * Consulta ornitológica profunda da **espécie** (Minhas Aves / Álbum).
 *
 * Usa os nomes e a foto de referência tratada da espécie. O resultado fica em
 * cache no cadastro; `refresh` força uma nova consulta à IA externa.
 */
export async function askSpeciesAi(
  speciesId: string,
  refresh = false,
): Promise<SpeciesAiConsult> {
  const { data } = await api.post<SpeciesAiConsult>(
    `/species/${encodeURIComponent(speciesId)}/ask-ai`,
    undefined,
    { params: refresh ? { refresh: true } : undefined, timeout: 60_000 },
  );
  return data;
}

/* ——— Log de anomalias acústico-visuais ——— */

export async function listAnomalies(options?: {
  limit?: number;
  onlyPending?: boolean;
}): Promise<Anomaly[]> {
  const { data } = await api.get<Anomaly[]>("/anomalies", {
    params: {
      limit: options?.limit ?? 50,
      only_pending: options?.onlyPending ?? false,
    },
  });
  return data;
}

export async function fetchAnomaliesPendingCount(): Promise<number> {
  const { data } = await api.get<{ pending: number }>("/anomalies/pending-count");
  return data.pending;
}

export async function acknowledgeAnomaly(id: string): Promise<Anomaly> {
  const { data } = await api.post<Anomaly>(
    `/anomalies/${encodeURIComponent(id)}/acknowledge`,
  );
  return data;
}

/* ——— Motor de IA (AI Core) ——— */

/** Estado atual do motor de IA, recursos e métricas de desempenho. */
export async function fetchAiStatus(): Promise<AiStatusSnapshot> {
  const { data } = await api.get<AiStatusSnapshot>("/ai/status");
  return data;
}

/**
 * Log cognitivo da IA (os "pensamentos" em tempo real).
 *
 * Com `sinceId`, devolve apenas os eventos mais novos que ele — ideal para o
 * polling incremental do painel.
 */
export async function fetchAiLogs(
  options?: { limit?: number; sinceId?: number },
): Promise<AiLogsResponse> {
  const { data } = await api.get<AiLogsResponse>("/ai/logs", {
    params: {
      limit: options?.limit ?? 60,
      since_id: options?.sinceId,
    },
  });
  return data;
}

/* ——— Métricas / Settings ——— */

export async function fetchMetrics(): Promise<Metrics> {
  const { data } = await api.get<Metrics>("/stats");
  return data;
}

export async function fetchAnalyticsSummary(): Promise<AnalyticsSummary> {
  const { data } = await api.get<AnalyticsSummary>("/analytics/summary");
  return data;
}

export async function fetchHourlyDistribution(): Promise<HourlyDistribution[]> {
  const { data } = await api.get<HourlyDistribution[]>(
    "/analytics/hourly-distribution",
  );
  return data;
}

export async function fetchLifeList(): Promise<LifeListSpecies[]> {
  const { data } = await api.get<LifeListSpecies[]>("/analytics/lifelist");
  return data;
}

/** Medalhas/marcos conquistados pelo observador. */
export async function fetchAchievements(): Promise<Achievement[]> {
  const { data } = await api.get<Achievement[]>("/analytics/achievements");
  return data;
}

/** Resumo dos Visitantes Silvestres / Convidados Especiais (Modo Esquilo). */
export async function fetchWildlifeSummary(): Promise<WildlifeSummary> {
  const { data } = await api.get<WildlifeSummary>("/wildlife/summary");
  return data;
}

/** Visitas de hoje consolidadas e segmentadas por jardim (câmera). */
export async function fetchTodayByGarden(): Promise<TodayByGarden> {
  const { data } = await api.get<TodayByGarden>("/analytics/today");
  return data;
}

/** Nível do Coletor baseado na quantidade de espécies descobertas. */
export async function fetchCollectorLevel(): Promise<CollectorLevel> {
  const { data } = await api.get<CollectorLevel>("/analytics/collector-level");
  return data;
}

/** Cruzamento bioacústico áudio × visual de uma câmera. */
export async function fetchBioacousticsCross(
  cameraId: string,
  janelaMinutos = 30,
): Promise<BioacousticsCross[]> {
  const { data } = await api.get<BioacousticsCross[]>(
    `/bioacoustics/cross/${cameraId}`,
    { params: { janela_minutos: janelaMinutos } },
  );
  return data;
}

/** Resumo bioacústico: espécies ouvidas vs. vistas. */
export async function fetchBioacousticsSummary(
  cameraId: string,
): Promise<BioacousticsSummary> {
  const { data } = await api.get<BioacousticsSummary>(
    `/bioacoustics/summary/${cameraId}`,
  );
  return data;
}

/** URL do stream de áudio ao vivo da câmera (player do painel). */
export function cameraAudioUrl(cameraId: string): string {
  return `/api/bioacoustics/audio/${cameraId}`;
}

/** URL de download do Laudo Ornitológico em PDF. */
export function laudoPdfUrl(): string {
  return "/api/analytics/report/pdf";
}
export async function fetchTodayVisits(
  limit = 50,
  visitorKind?: "bird" | "special" | "mammal" | "other",
): Promise<BirdVisit[]> {
  const { data } = await api.get<BirdVisit[]>("/visits/today", {
    params: { limit, visitor_kind: visitorKind },
  });
  return data;
}

/** Clima atual do local do alimentador (widget do painel). */
export async function fetchCurrentWeather(): Promise<CurrentWeather> {
  const { data } = await api.get<CurrentWeather>("/weather/current");
  return data;
}

/** Cruzamento entre frequência de visitas e condições do tempo. */
export async function fetchWeatherCorrelation(): Promise<WeatherCorrelation> {
  const { data } = await api.get<WeatherCorrelation>(
    "/analytics/weather-correlation",
  );
  return data;
}

/** Insights avançados cruzando clima e hábitos das aves. */
export async function fetchWeatherInsights(): Promise<WeatherInsights> {
  const { data } = await api.get<WeatherInsights>(
    "/analytics/weather-insights",
  );
  return data;
}

/* ——— Resumos do dia (time-lapse) ——— */

/** Lista os resumos do dia (time-lapses) já gerados, do mais recente ao mais antigo. */
export async function fetchTimelapses(): Promise<Timelapse[]> {
  const { data } = await api.get<Timelapse[]>("/analytics/timelapses");
  return data;
}

/**
 * Gera sob demanda o resumo de um dia (padrão: hoje).
 *
 * `force` regera um resumo já existente. O timeout é desativado porque a
 * montagem com FFmpeg pode demorar vários segundos.
 */
export async function generateTimelapse(
  day?: string,
  force = false,
): Promise<TimelapseGenerateResult> {
  const { data } = await api.post<TimelapseGenerateResult>(
    "/analytics/timelapses/generate",
    { day: day ?? null, force },
    { timeout: 0 },
  );
  return data;
}

/** Remove um resumo do dia pelo nome do arquivo. */
export async function deleteTimelapse(filename: string): Promise<void> {
  await api.delete(`/analytics/timelapses/${encodeURIComponent(filename)}`);
}

export async function fetchAudioDetections(
  limit = 30,
): Promise<AudioDetection[]> {
  const { data } = await api.get<AudioDetection[]>("/audio-detections", {
    params: { limit },
  });
  return data;
}

export async function fetchAudioAnalysisStatus(): Promise<AudioAnalysisStatus> {
  const { data } = await api.get<AudioAnalysisStatus>(
    "/audio-detections/status",
  );
  return data;
}

/** Lista os dispositivos de entrada de áudio disponíveis no sistema. */
export async function fetchAudioInputDevices(): Promise<AudioInputDevices> {
  const { data } = await api.get<AudioInputDevices>("/audio-detections/devices");
  return data;
}

export async function fetchSettings(): Promise<AppSettings> {
  const { data } = await api.get<AppSettings>("/settings");
  return data;
}

export async function updateSettings(payload: AppSettingsUpdate): Promise<AppSettings> {
  const { data } = await api.put<AppSettings>("/settings", payload);
  return data;
}

/* ——— Calibração de sensibilidade ——— */

export async function fetchCalibration(): Promise<Calibration> {
  const { data } = await api.get<Calibration>("/settings/calibration");
  return data;
}

export async function updateCalibration(
  payload: CalibrationUpdate,
): Promise<Calibration> {
  const { data } = await api.post<Calibration>("/settings/calibration", payload);
  return data;
}

export async function testNotification(
  channel: NotificationChannel,
): Promise<{ ok: boolean; message: string }> {
  const { data } = await api.post<{ ok: boolean; message: string }>(
    "/settings/test-notification",
    { channel },
  );
  return data;
}

export async function fetchEnvironmentSettings(): Promise<EnvironmentSettings> {
  const { data } = await api.get<EnvironmentSettings>("/settings/env");
  return data;
}

export async function saveEnvironmentSettings(
  payload: EnvironmentSettingsUpdate,
): Promise<EnvironmentSettings> {
  const { data } = await api.post<EnvironmentSettings>("/settings/env", payload);
  return data;
}

export async function testEnvironmentConnection(
  integration: EnvironmentIntegration,
  credentials: EnvironmentSettingsUpdate,
): Promise<{ ok: boolean; message: string }> {
  const { data } = await api.post<{ ok: boolean; message: string }>(
    "/settings/env/test",
    { integration, ...credentials },
  );
  return data;
}

/* ——— Mídia / stream ——— */

export function videoFeedUrl(cameraId: string, boxes = true): string {
  return `/api/video-feed/${encodeURIComponent(cameraId)}?boxes=${boxes}`;
}

export function snapshotUrl(cameraId: string, boxes = true): string {
  return `/api/video-feed/${encodeURIComponent(cameraId)}/snapshot?boxes=${boxes}&t=${Date.now()}`;
}

export function resolveMediaUrl(pathOrUrl: string | null | undefined): string | null {
  if (!pathOrUrl) return null;
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  if (pathOrUrl.startsWith("/")) return pathOrUrl;
  return `/captures/${pathOrUrl.replace(/^captures\//, "")}`;
}

/**
 * URL do recorte (close-up) da ave tratado pelo Alaris Core.
 *
 * Os recortes ficam em `app-data/crops` (irmã da pasta estática `captures`),
 * por isso são servidos pelo endpoint dedicado `/api/visits/{id}/crop` — e não
 * por `/captures/crops/...`.
 */
export function visitCropUrl(visitId: string): string {
  return `/api/visits/${encodeURIComponent(visitId)}/crop`;
}
