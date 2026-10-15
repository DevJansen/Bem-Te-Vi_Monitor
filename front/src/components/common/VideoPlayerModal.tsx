import { useEffect, useState } from "react";
import { AlertTriangle, Download, ExternalLink, X } from "lucide-react";

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
};

export function VideoPlayerModal({ open, title, src, onClose }: Props) {
  const [error, setError] = useState<string | null>(null);

  // Reinicia o erro sempre que um novo clipe é aberto.
  useEffect(() => {
    if (open) setError(null);
  }, [open, src]);

  if (!open) return null;

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

        <div className="mt-3 overflow-hidden rounded-lg bg-black">
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
