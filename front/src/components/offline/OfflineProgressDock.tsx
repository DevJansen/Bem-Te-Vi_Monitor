import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  LoaderCircle,
  UploadCloud,
  X,
} from "lucide-react";
import { useOfflineAnalysis } from "@/context/OfflineAnalysisContext";
import { DismissButton, ProgressBar } from "@/components/offline/OfflineJobCard";
import { cn } from "@/utils/cn";

type Props = {
  onOpenGallery?: () => void;
};

/**
 * Cartão flutuante de progresso global.
 *
 * Fica montado no topo da aplicação (fora das abas), então **nunca desaparece**
 * ao navegar entre Painel, Câmeras e Galeria: os uploads e as análises
 * continuam visíveis e atualizados em tempo real.
 */
export function OfflineProgressDock({ onOpenGallery }: Props) {
  const { uploads, jobs, successes, activeCount, dismissUpload, dismissSuccess } =
    useOfflineAnalysis();
  const [collapsed, setCollapsed] = useState(false);

  const activeJobs = jobs.filter(
    (job) => job.status === "queued" || job.status === "processing",
  );
  const uploading = uploads.filter((item) => item.status === "uploading");
  const failedUploads = uploads.filter((item) => item.status === "error");
  const totalItems =
    activeJobs.length + uploading.length + failedUploads.length + successes.length;

  if (totalItems === 0) return null;

  return (
    <aside
      aria-label="Progresso das análises de vídeo"
      className={cn(
        "fixed bottom-4 left-4 right-4 z-50 sm:left-auto sm:right-5 sm:bottom-5 sm:w-[22rem]",
        "animate-slide-in-right",
      )}
    >
      <div className="overflow-hidden rounded-2xl border border-dark-700 bg-dark-800/95 shadow-2xl shadow-black/50 backdrop-blur-xl">
        <header className="flex items-center gap-2 border-b border-dark-700/70 px-3.5 py-2.5">
          <span className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
            {activeCount > 0 ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-[var(--color-text-primary)]">
              {activeCount > 0
                ? `Analisando ${activeCount} vídeo${activeCount > 1 ? "s" : ""}…`
                : "Análises de vídeo"}
            </p>
            <p className="text-[11px] text-[var(--color-text-muted)]">
              {activeCount > 0
                ? "Roda no servidor — pode trocar de aba"
                : "Tudo em dia"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            aria-label={collapsed ? "Expandir" : "Recolher"}
            className="rounded-md p-1 text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
          >
            {collapsed ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>
        </header>

        {!collapsed ? (
          <ul className="max-h-[60vh] space-y-3 overflow-y-auto px-3.5 py-3">
            {uploading.map((item) => (
              <li key={item.id} className="space-y-1.5">
                <div className="flex items-center gap-2 text-xs">
                  <UploadCloud className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                  <span className="min-w-0 flex-1 truncate text-[var(--color-text-primary)]">
                    Enviando {item.filename}
                  </span>
                  <span className="tabular-nums text-emerald-300">
                    {item.progress}%
                  </span>
                </div>
                <ProgressBar value={item.progress} className="h-1.5" />
              </li>
            ))}

            {activeJobs.map((job) => (
              <li key={job.id} className="space-y-1.5">
                <div className="flex items-center gap-2 text-xs">
                  <LoaderCircle className="h-3.5 w-3.5 shrink-0 animate-spin text-emerald-400" />
                  <span className="min-w-0 flex-1 truncate text-[var(--color-text-primary)]">
                    {job.filename}
                  </span>
                  <span className="tabular-nums text-emerald-300">
                    {Math.floor(job.progress)}%
                  </span>
                </div>
                <ProgressBar value={job.progress} className="h-1.5" />
                <p className="truncate text-[11px] text-[var(--color-text-muted)]">
                  {job.progress_message || "Analisando vídeo…"}
                </p>
              </li>
            ))}

            {successes.map((job) => (
              <li
                key={job.id}
                className="flex items-start gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/5 px-2.5 py-2"
              >
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-[var(--color-text-primary)]">
                    {job.birds_detected_count === 1
                      ? "1 pássaro encontrado"
                      : `${job.birds_detected_count} pássaros encontrados`}
                  </p>
                  <p className="truncate text-[11px] text-[var(--color-text-muted)]">
                    {job.filename}
                  </p>
                  {onOpenGallery && job.birds_detected_count > 0 ? (
                    <button
                      type="button"
                      onClick={onOpenGallery}
                      className="mt-1 text-[11px] font-medium text-emerald-300 hover:underline"
                    >
                      Ver na Galeria →
                    </button>
                  ) : null}
                </div>
                <DismissButton onClick={() => dismissSuccess(job.id)} />
              </li>
            ))}

            {failedUploads.map((item) => (
              <li
                key={item.id}
                className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 px-2.5 py-2"
              >
                <X className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-red-200">
                    Falha no envio
                  </p>
                  <p className="text-[11px] text-red-300/80">{item.error}</p>
                </div>
                <DismissButton onClick={() => dismissUpload(item.id)} />
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </aside>
  );
}
