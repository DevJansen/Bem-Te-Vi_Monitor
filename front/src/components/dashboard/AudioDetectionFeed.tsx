import { useCallback } from "react";
import { AlertCircle, AudioLines, Music2, RefreshCw } from "lucide-react";
import { fetchAudioAnalysisStatus, fetchAudioDetections, getErrorMessage } from "@/services/api";
import type { AudioAnalysisStatus, AudioDetection } from "@/types";
import { usePolling } from "@/hooks/usePolling";
import { formatDateTime, formatPercent } from "@/utils/format";

type FeedData = {
  status: AudioAnalysisStatus;
  detections: AudioDetection[];
};

async function loadAudioFeed(): Promise<FeedData> {
  try {
    const [status, detections] = await Promise.all([
      fetchAudioAnalysisStatus(),
      fetchAudioDetections(),
    ]);
    return { status, detections };
  } catch (error) {
    throw new Error(
      getErrorMessage(error, "Não foi possível carregar as detecções sonoras."),
    );
  }
}

const statusLabels: Record<AudioAnalysisStatus["status"], string> = {
  disabled: "Desativada",
  starting: "Iniciando",
  monitoring: "Monitorando",
  no_cameras: "Sem câmeras compatíveis",
  error: "Indisponível",
};

export function AudioDetectionFeed() {
  const query = usePolling(loadAudioFeed, 8_000);
  const refresh = useCallback(() => void query.refresh(), [query.refresh]);
  const feed = query.data;

  return (
    <section className="rounded-xl border border-dark-700 bg-dark-800">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-dark-700 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded-lg bg-violet-500/10 p-2 text-violet-300">
            <AudioLines className="h-4 w-4" />
          </span>
          <div>
            <h2 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
              Detecção Sonora / Bioacústica
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Identificação de cantos com BirdNET
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {feed ? (
            <span
              className={`rounded-full border px-2.5 py-1 text-[10px] font-medium ${
                feed.status.status === "monitoring"
                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
                  : feed.status.status === "error"
                    ? "border-red-500/25 bg-red-500/10 text-red-300"
                    : "border-dark-700 bg-dark-900 text-[var(--color-text-muted)]"
              }`}
            >
              {statusLabels[feed.status.status]}
            </span>
          ) : null}
          <button
            type="button"
            onClick={refresh}
            disabled={query.loading}
            aria-label="Atualizar detecções sonoras"
            className="rounded-md p-1.5 text-[var(--color-text-muted)] hover:text-violet-300 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${query.loading ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      <div className="p-4">
        {feed?.status.status === "monitoring" ? (
          <p className="mb-3 text-xs text-[var(--color-text-muted)]">
            {feed.status.message}
          </p>
        ) : null}
        {query.error ? (
          <p
            role="alert"
            className="flex items-center gap-2 text-sm text-red-300"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            {query.error}
          </p>
        ) : query.loading && !feed ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            Carregando detecções sonoras…
          </p>
        ) : feed?.status.status === "error" ? (
          <p role="status" className="text-sm text-amber-200">
            {feed.status.message}
          </p>
        ) : feed?.status.status === "no_cameras" ||
          feed?.status.status === "disabled" ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            {feed.status.message}
          </p>
        ) : feed && feed.detections.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            {feed.status.status === "starting"
              ? feed.status.message
              : "Nenhum canto identificado ainda. As detecções recentes aparecerão aqui."}
          </p>
        ) : feed ? (
          <ul className="divide-y divide-dark-700">
            {feed.detections.slice(0, 8).map((detection) => (
              <li
                key={detection.id}
                className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3 first:pt-0 last:pb-0"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="rounded-lg bg-violet-500/10 p-2 text-violet-300">
                    <Music2 className="h-4 w-4" aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                      {detection.species}
                    </p>
                    <p className="truncate text-xs text-[var(--color-text-muted)]">
                      {detection.camera_name} · {formatDateTime(detection.detected_at)}
                      {detection.linked_visit_id ? " · visita visual associada" : ""}
                    </p>
                  </div>
                </div>
                <span className="shrink-0 rounded-full border border-violet-400/20 bg-violet-400/10 px-2.5 py-1 text-xs font-semibold text-violet-200">
                  {formatPercent(detection.confidence)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
