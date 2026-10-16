import { useRef, useState, type DragEvent } from "react";
import { Film, FolderOpen, UploadCloud } from "lucide-react";
import { cn } from "@/utils/cn";

type Props = {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
};

const FORMATS = ["MP4", "AVI", "MOV", "MKV"];

/**
 * Área de arraste e solte moderna para os vídeos do cartão de memória.
 *
 * Aceita um ou vários arquivos de uma vez, destaca-se ao arrastar por cima e
 * também abre o seletor nativo ao clicar.
 */
export function OfflineDropzone({ onFiles, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const emit = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    onFiles(Array.from(list));
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    emit(event.dataTransfer?.files ?? null);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === " ") && !disabled) {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        setDragging(false);
      }}
      onDrop={handleDrop}
      className={cn(
        "group relative flex cursor-pointer flex-col items-center justify-center gap-4 overflow-hidden rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-all duration-300",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60",
        disabled
          ? "cursor-not-allowed border-dark-700 bg-dark-900/60 opacity-60"
          : dragging
            ? "scale-[1.01] border-emerald-400 bg-emerald-500/10 shadow-[0_0_45px_-10px_rgba(16,185,129,0.55)]"
            : "border-dark-700 bg-dark-900/40 hover:border-emerald-500/50 hover:bg-emerald-500/5",
      )}
    >
      {/* Halo de fundo suave */}
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500",
          dragging && "opacity-100",
        )}
        style={{
          background:
            "radial-gradient(circle at 50% 30%, rgba(16,185,129,0.18), transparent 65%)",
        }}
      />

      <span
        className={cn(
          "relative flex h-16 w-16 items-center justify-center rounded-2xl border transition-all duration-300",
          dragging
            ? "border-emerald-400/60 bg-emerald-500/20 text-emerald-300"
            : "border-dark-700 bg-dark-800 text-emerald-400 group-hover:border-emerald-500/40",
        )}
      >
        <UploadCloud
          className={cn(
            "h-7 w-7 transition-transform duration-300",
            dragging ? "-translate-y-1 scale-110" : "group-hover:-translate-y-0.5",
          )}
          strokeWidth={1.75}
        />
      </span>

      <div className="relative space-y-1">
        <p className="font-display text-base font-semibold text-[var(--color-text-primary)]">
          {dragging ? "Solte o vídeo para analisar" : "Arraste e solte o vídeo aqui"}
        </p>
        <p className="text-sm text-[var(--color-text-muted)]">
          ou{" "}
          <span className="font-medium text-emerald-300 underline-offset-4 group-hover:underline">
            clique para selecionar
          </span>{" "}
          do cartão de memória
        </p>
      </div>

      <div className="relative flex flex-wrap items-center justify-center gap-2">
        {FORMATS.map((format) => (
          <span
            key={format}
            className="inline-flex items-center gap-1 rounded-full border border-dark-700 bg-dark-800/80 px-2.5 py-1 text-[11px] font-semibold tracking-wide text-[var(--color-text-muted)]"
          >
            <Film className="h-3 w-3 text-emerald-400/80" />
            {format}
          </span>
        ))}
      </div>

      <p className="relative flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
        <FolderOpen className="h-3.5 w-3.5" />
        Um ou vários arquivos · limite de 2 GB por vídeo
      </p>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".mp4,.avi,.mov,.mkv,video/mp4,video/x-msvideo,video/quicktime,video/x-matroska"
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          emit(event.target.files);
          event.currentTarget.value = "";
        }}
      />
    </div>
  );
}
