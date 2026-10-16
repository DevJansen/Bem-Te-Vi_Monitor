import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Film,
  Images,
  LoaderCircle,
  Trash2,
  X,
} from "lucide-react";
import type { OfflineJob } from "@/types";
import { resolveMediaUrl } from "@/services/api";
import { formatDateTime } from "@/utils/format";
import { cn } from "@/utils/cn";

type Props = {
  job: OfflineJob;
  onOpenGallery: () => void;
  onRemove?: () => void;
};

/** Formata segundos do vídeo como mm:ss. */
function formatVideoTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

const STATUS_BADGE: Record<
  OfflineJob["status"],
  { label: string; className: string }
> = {
  queued: {
    label: "Na fila",
    className: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  },
  processing: {
    label: "Analisando",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  },
  completed: {
    label: "Concluído",
    className: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
  },
  error: {
    label: "Erro",
    className: "border-red-500/40 bg-red-500/10 text-red-300",
  },
};

/**
 * Cartão de um job de análise offline. Adapta-se ao estado:
 * - em andamento: barra de progresso + mensagem de frame;
 * - concluído: selo de sucesso, contagem de aves e miniaturas;
 * - erro: mensagem clara com opção de remover.
 */
export function OfflineJobCard({ job, onOpenGallery, onRemove }: Props) {
  const badge = STATUS_BADGE[job.status];
  const isActive = job.status === "queued" || job.status === "processing";
  const detections = job.detections ?? [];
  const thumbnails = detections.filter(
    (item) => item.crop_url || item.thumbnail_url,
  );

  return (
    <article
      className={cn(
        "animate-fade-in-up overflow-hidden rounded-2xl border bg-dark-800/80 backdrop-blur transition-colors",
        job.status === "completed"
          ? "border-emerald-500/25"
          : job.status === "error"
            ? "border-red-500/25"
            : "border-dark-700",
      )}
    >
      <header className="flex items-start gap-3 border-b border-dark-700/70 px-4 py-3">
        <span
          className={cn(
            "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
            job.status === "completed"
              ? "bg-emerald-500/15 text-emerald-300"
              : job.status === "error"
                ? "bg-red-500/15 text-red-300"
                : "bg-dark-700 text-emerald-300",
          )}
        >
          {job.status === "completed" ? (
            <CheckCircle2 className="h-5 w-5" />
          ) : job.status === "error" ? (
            <AlertTriangle className="h-5 w-5" />
          ) : (
            <Film className="h-5 w-5" />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-[var(--color-text-primary)]">
            {job.filename}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-[var(--color-text-muted)]">
            {job.camera_name ? <span>{job.camera_name}</span> : null}
            {job.status === "completed" && job.finished_at ? (
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatDateTime(job.finished_at)}
              </span>
            ) : null}
          </p>
        </div>

        <span
          className={cn(
            "shrink-0 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
            badge.className,
          )}
        >
          {badge.label}
        </span>

        {onRemove && !isActive ? (
          <button
            type="button"
            onClick={onRemove}
            aria-label="Remover do histórico"
            className="shrink-0 rounded-lg p-1.5 text-[var(--color-text-muted)] transition hover:bg-red-500/10 hover:text-red-300"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        ) : null}
      </header>

      <div className="px-4 py-4">
        {isActive ? (
          <div className="space-y-2" aria-live="polite">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-[var(--color-text-primary)]">
                <LoaderCircle className="h-4 w-4 animate-spin text-emerald-400" />
                {job.progress_message || "Analisando vídeo…"}
              </span>
              <span className="font-semibold tabular-nums text-emerald-300">
                {Math.floor(job.progress)}%
              </span>
            </div>
            <ProgressBar value={job.progress} />
          </div>
        ) : null}

        {job.status === "error" ? (
          <p className="flex items-start gap-2 text-sm text-red-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {job.error || "A análise não pôde ser concluída."}
          </p>
        ) : null}

        {job.status === "completed" ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="animate-pop-in text-3xl leading-none">🐦</span>
                <div>
                  <p className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
                    {job.birds_detected_count === 1
                      ? "1 Pássaro Encontrado"
                      : `${job.birds_detected_count} Pássaros Encontrados`}
                  </p>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {job.summary ?? "Análise concluída."}
                  </p>
                </div>
              </div>

              {detections.length > 0 ? (
                <button
                  type="button"
                  onClick={onOpenGallery}
                  className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/20"
                >
                  <Images className="h-4 w-4" />
                  Ver na Galeria
                </button>
              ) : null}
            </div>

            {thumbnails.length > 0 ? (
              <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
                {thumbnails.map((detection) => {
                  const src = resolveMediaUrl(
                    detection.crop_url ?? detection.thumbnail_url,
                  );
                  return (
                    <li key={detection.id}>
                      <button
                        type="button"
                        onClick={onOpenGallery}
                        title={`Ave detectada em ${formatVideoTime(
                          detection.timestamp_seconds,
                        )}`}
                        className="group relative block aspect-square w-full overflow-hidden rounded-xl border border-dark-700 bg-dark-900"
                      >
                        {src ? (
                          <img
                            src={src}
                            alt={`Ave detectada em ${formatVideoTime(
                              detection.timestamp_seconds,
                            )}`}
                            loading="lazy"
                            className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
                          />
                        ) : (
                          <span className="flex h-full w-full items-center justify-center text-[var(--color-text-muted)]">
                            <Images className="h-5 w-5" />
                          </span>
                        )}
                        <span className="absolute bottom-1 left-1 rounded-md bg-black/70 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-emerald-200">
                          {formatVideoTime(detection.timestamp_seconds)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="rounded-lg border border-dark-700 bg-dark-900/60 px-3 py-3 text-sm text-[var(--color-text-muted)]">
                Nenhuma ave foi registrada neste vídeo. Tente um vídeo com as aves
                mais próximas do alimentador ou ajuste as zonas de leitura da câmera.
              </p>
            )}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/** Barra de progresso animada reutilizável. */
export function ProgressBar({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.floor(clamped)}
      className={cn(
        "relative h-2 overflow-hidden rounded-full bg-dark-900",
        className,
      )}
    >
      <div
        className="h-full rounded-full bg-emerald-500 transition-[width] duration-500 ease-out"
        style={{ width: `${clamped}%` }}
      >
        <span
          aria-hidden
          className="block h-full w-full animate-progress-stripes rounded-full opacity-40"
          style={{
            backgroundImage:
              "linear-gradient(45deg, rgba(255,255,255,0.35) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.35) 50%, rgba(255,255,255,0.35) 75%, transparent 75%, transparent)",
            backgroundSize: "1rem 1rem",
          }}
        />
      </div>
    </div>
  );
}

/** Botão de descarte reutilizável (usado no dock flutuante). */
export function DismissButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Dispensar"
      className="rounded-md p-1 text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
    >
      <X className="h-3.5 w-3.5" />
    </button>
  );
}
