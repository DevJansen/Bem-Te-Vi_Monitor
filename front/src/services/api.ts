import axios, { type AxiosError } from "axios";
import type {
  AppSettings,
  AppSettingsUpdate,
  AnalyticsSummary,
  AudioAnalysisStatus,
  AudioDetection,
  BirdSpecies,
  BirdSpeciesCreatePayload,
  BirdVisit,
  Camera,
  CameraCreatePayload,
  CameraUpdatePayload,
  EnvironmentIntegration,
  EnvironmentSettings,
  EnvironmentSettingsUpdate,
  HealthResponse,
  HistoryDeletionResult,
  HourlyDistribution,
  LifeListSpecies,
  Metrics,
  NotificationChannel,
  RecordingAnalysis,
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

export async function saveCameraZones(id: string, zones: Zone[]): Promise<Zone[]> {
  const { data } = await api.put<{ zones: Zone[] }>(`/cameras/${id}/zones`, {
    zones,
  });
  return data.zones;
}

export async function deleteCamera(id: string): Promise<void> {
  await api.delete(`/cameras/${id}`);
}

export async function importRecording(
  file: File,
  cameraId: string,
  onUploadProgress: (percent: number) => void,
): Promise<RecordingAnalysis> {
  const form = new FormData();
  form.append("file", file);
  form.append("camera_id", cameraId);
  form.append("recorded_at", new Date(file.lastModified || Date.now()).toISOString());
  const { data } = await api.post<RecordingAnalysis>("/recordings/import", form, {
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

export async function fetchRecordingAnalysis(id: string): Promise<RecordingAnalysis> {
  const { data } = await api.get<RecordingAnalysis>(`/recordings/${id}`);
  return data;
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

export async function identifyVisitExternal(id: string): Promise<BirdVisit> {
  const { data } = await api.post<BirdVisit>(
    `/visits/${id}/identify-external`,
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

export async function fetchSettings(): Promise<AppSettings> {
  const { data } = await api.get<AppSettings>("/settings");
  return data;
}

export async function updateSettings(payload: AppSettingsUpdate): Promise<AppSettings> {
  const { data } = await api.put<AppSettings>("/settings", payload);
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
