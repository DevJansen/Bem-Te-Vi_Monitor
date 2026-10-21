import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Bird,
  Download,
  ExternalLink,
  Leaf,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { formatPercent, formatSpeciesLabel } from "@/utils/format";

/** MIME type conforme a extensão do clipe (o navegador usa isso no <source>). */
function videoMimeType(url: string): string {
  const clean = url.split("?")[0].toLowerCase();
  if (clean.endsWith(".webm")) return "video/webm";
  if (clean.endsWith(".mov")) return "video/quicktime";
  if (clean.endsWith(".avi")) return "video/x-msvideo";
  if (clean.endsWith(".mkv")) return "video/x-matroska";
  return "video/mp4";
}

type Props = {
  open: boolean;
  title: string;
  /** URL de streaming do clipe (ex.: `/api/videos/arquivo.mp4`). */
  src: string | null;
  onClose: () => void;
  /** Espécie identificada pelo Bem-Te-Vi Core (selo sobre o vídeo). */
  species?: string | null;
  /** Confiança da identificação (0..1). */
  confidence?: number | null;
  /** Nome científico associado, quando houver. */
  scientificName?: string | null;
  /** Selo ecológico regional (ex.: "🟢 Nativa"). */
  ecologicalBadge?: string | null;
  /** Indivíduos no pico do bando (selo "👥 N"). */
  individualsPeak?: number | null;
};

export function VideoPlayerModal({
  open,
  title,
  src,
  onClose,
  species,
  confidence,
  scientificName,
  ecologicalBadge,
  individualsPeak,
}: Props) {
  const [error, setError] = useState<string | null>(null);

  // Reinicia o erro sempre que um novo clipe é aberto.
  useEffect(() => {
    if (open) setError(null);
  }, [open, src]);

  if (!open) return null;

  const speciesLabel = species ? formatSpeciesLabel(species) : null;
  const hasConfidence = typeof confidence === "number" && confidence > 0;
  const showOverlay = Boolean(speciesLabel || hasConfidence);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/80"
        aria-label="Fechar player"
        onClick={onClose}
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-label={`Reprodução do clipe: ${title}`}
        className="relative z-10 w-full max-w-3xl rounded-xl border border-dark-700 bg-dark-800 p-4 shadow-2xl sm:p-5"
      >
        <div className="flex items-start gap-3">
          <h2 className="min-w-0 flex-1 truncate font-display text-base font-semibold text-[var(--color-text-primary)]">
            {title}
          </h2>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="rounded-md p-1 text-[var(--color-text-muted)] hover:bg-dark-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="relative mt-3 overflow-hidden rounded-lg bg-black">
          {src ? (
            <video
              key={src}
              controls
              preload="metadata"
              playsInline
              className="h-auto w-full rounded-lg"
              onError={() =>
                setError(
                  "Não foi possível reproduzir este vídeo. O arquivo pode estar corrompido ou em um formato não suportado pelo navegador.",
                )
              }
            >
              <source src={src} type={videoMimeType(src)} />
              Seu navegador não suporta a tag de vídeo.
            </video>
          ) : (
            <div className="flex aspect-video items-center justify-center text-sm text-[var(--color-text-muted)]">
              Clipe indisponível para esta captura.
            </div>
          )}

          {/* Selo de identificação do Bem-Te-Vi Core sobre o vídeo (dark mode). */}
          {showOverlay ? (
            <div className="pointer-events-none absolute inset-0 flex items-start justify-between gap-2 p-3">
              <div className="flex max-w-[78%] flex-col gap-1.5">
                <div className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-black/65 px-3 py-2 shadow-lg backdrop-blur-md">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300">
                    <Bird className="h-4 w-4" />
                  </span>
                  <span className="flex min-w-0 flex-col leading-tight">
                    <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-300/90">
                      <Sparkles className="h-2.5 w-2.5" />
                      Bem-Te-Vi Core
                    </span>
                    <span className="truncate text-sm font-semibold text-white sm:text-base">
                      {speciesLabel ?? "Ave"}
                    </span>
                  </span>
                  {hasConfidence ? (
                    <span className="ml-1 shrink-0 rounded-md bg-emerald-500/20 px-1.5 py-0.5 text-[11px] font-bold tabular-nums text-emerald-300">
                      {formatPercent(confidence ?? 0)}
                    </span>
                  ) : null}
                </div>
                {scientificName ? (
                  <span className="truncate rounded-md bg-black/55 px-2 py-0.5 text-[11px] italic text-white/75 backdrop-blur-sm">
                    {scientificName}
                  </span>
                ) : null}
              </div>

              <div className="flex shrink-0 flex-col items-end gap-1.5">
                {ecologicalBadge ? (
                  <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-black/65 px-2 py-1 text-[11px] font-medium text-white/85 backdrop-blur-md">
                    <Leaf className="h-3 w-3 text-emerald-300" />
                    {ecologicalBadge}
                  </span>
                ) : null}
                {individualsPeak && individualsPeak > 1 ? (
                  <span className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-black/65 px-2 py-1 text-[11px] font-medium text-white/85 backdrop-blur-md">
                    <Users className="h-3 w-3 text-cyan-300" />
                    {individualsPeak} indivíduos
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        {error ? (
          <p
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap justify-end gap-2">
          {src ? (
            <>
              <a
                href={src}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-dark-600 px-3 py-2 text-sm text-[var(--color-text-muted)] transition hover:bg-dark-700"
              >
                <ExternalLink className="h-4 w-4" />
                Abrir em nova aba
              </a>
              <a
                href={src}
                download
                className="inline-flex items-center gap-2 rounded-lg border border-dark-600 px-3 py-2 text-sm text-[var(--color-text-muted)] transition hover:bg-dark-700"
              >
                <Download className="h-4 w-4" />
                Baixar clipe
              </a>
            </>
          ) : null}
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400"
          >
            Fechar
          </button>
        </div>
      </section>
    </div>
  );
}
