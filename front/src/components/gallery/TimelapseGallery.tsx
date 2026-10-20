import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  Clock,
  Download,
  Film,
  LoaderCircle,
  Play,
  RefreshCw,
  Smartphone,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { BirdVisit, ReelInfo, Timelapse } from "@/types";
import {
  deleteTimelapse,
  fetchTimelapses,
  generateReel,
  generateTimelapse,
  getErrorMessage,
  listVisitsByDay,
  resolveMediaUrl,
} from "@/services/api";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { cn } from "@/utils/cn";

/**
 * Converte uma data `YYYY-MM-DD` em `DD/MM/AAAA`.
 *
 * A conversão é feita por texto (e não com `new Date`) para evitar o deslocamento
 * de fuso horário que faria o dia "voltar" um dia no hemisfério oeste.
 */
function formatDay(day: string): string {
  const [year, month, date] = day.split("-");
  if (!year || !month || !date) return day;
  return `${date}/${month}/${year}`;
}

/** Duração em `m:ss` (ou `—` quando desconhecida). */
function formatDuration(seconds: number | null): string {
  if (seconds === null || Number.isNaN(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

/** Tamanho do arquivo em KB/MB. */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Aba "Resumos do Dia": lista e reproduz os time-lapses diários. */
export function TimelapseGallery() {
  const [items, setItems] = useState<Timelapse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Timelapse | null>(null);
  const [deleting, setDeleting] = useState(false);
  /** Reel vertical gerado a partir da melhor visita do dia selecionado. */
  const [reelInfo, setReelInfo] = useState<ReelInfo | null>(null);
  const [reelBusy, setReelBusy] = useState(false);
  const [reelError, setReelError] = useState<string | null>(null);

  /** Carrega a lista de resumos e mantém uma seleção válida. */
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTimelapses();
      setItems(data);
      setSelectedName((current) => {
        if (current && data.some((item) => item.filename === current)) {
          return current;
        }
        return data[0]?.filename ?? null;
      });
    } catch (err) {
      setError(
        getErrorMessage(err, "Não foi possível carregar os resumos do dia."),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => items.find((item) => item.filename === selectedName) ?? null,
    [items, selectedName],
  );

  /** Gera (ou regera) o resumo de hoje a partir dos clipes do dia. */
  const handleGenerate = async () => {
    setGenerating(true);
    setMessage(null);
    try {
      const result = await generateTimelapse(undefined, true);
      setMessage(result.message);
      await load();
      if (result.timelapse) setSelectedName(result.timelapse.filename);
    } catch (err) {
      setMessage(
        getErrorMessage(err, "Não foi possível gerar o resumo do dia."),
      );
    } finally {
      setGenerating(false);
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteTimelapse(pendingDelete.filename);
      setPendingDelete(null);
      await load();
    } catch (err) {
      setMessage(
        getErrorMessage(err, "Não foi possível remover o resumo do dia."),
      );
    } finally {
      setDeleting(false);
    }
  };

  /**
   * Gera um Reel vertical (9:16) a partir da melhor visita (com clipe) do dia
   * selecionado — o mesmo clipe que encabeça o resumo do dia.
   */
  const handleGenerateReel = async () => {
    if (!selected) return;
    setReelBusy(true);
    setReelError(null);
    setReelInfo(null);
    try {
      const visits: BirdVisit[] = await listVisitsByDay(selected.day);
      // Prioriza aves identificadas e com clipe gravado.
      const candidates = visits
        .filter((visit) => visit.clip_path || visit.clip_url)
        .sort((a, b) => {
          const aScore = (a.confidence ?? 0) * (a.species_id ? 1.2 : 1);
          const bScore = (b.confidence ?? 0) * (b.species_id ? 1.2 : 1);
          return bScore - aScore;
        });
      const best = candidates[0] ?? null;
      if (!best) {
        setReelError(
          "Nenhum clipe de vídeo encontrado neste dia para gerar o Reel.",
        );
        return;
      }
      const info = await generateReel(best.id);
      setReelInfo(info);
    } catch (err) {
      setReelError(
        getErrorMessage(err, "Não foi possível gerar o Reel deste dia."),
      );
    } finally {
      setReelBusy(false);
    }
  };

  const playerSrc = selected ? resolveMediaUrl(selected.url) : null;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
            Resumos do Dia (Time-Lapse)
          </h2>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            Os melhores momentos de cada dia, acelerados em um único vídeo
            compacto. A montagem é feita automaticamente no fim do dia — você
            também pode gerar agora.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading || generating}
            className="inline-flex items-center gap-2 rounded-lg border border-dark-600 px-3 py-2 text-sm text-[var(--color-text-muted)] transition hover:bg-dark-700 disabled:opacity-50"
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Atualizar
          </button>
          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={generating}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:opacity-50"
          >
            {generating ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {generating ? "Gerando…" : "Gerar resumo de hoje"}
          </button>
        </div>
      </div>

      {message ? (
        <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
          {message}
        </p>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300"
        >
          {error}
        </p>
      ) : null}

      {loading && items.length === 0 ? (
        <p className="flex items-center gap-2 rounded-xl border border-dark-700 bg-dark-800 p-6 text-sm text-[var(--color-text-muted)]">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Carregando resumos do dia…
        </p>
      ) : null}

      {!loading && !error && items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-dark-700 bg-dark-800/60 p-10 text-center">
          <Film className="h-8 w-8 text-[var(--color-text-muted)]" />
          <p className="text-sm font-medium text-[var(--color-text-primary)]">
            Nenhum resumo do dia ainda
          </p>
          <p className="max-w-md text-xs text-[var(--color-text-muted)]">
            Assim que houver clipes gravados, o Bem-Te-Vi monta o time-lapse
            automaticamente ao fim do dia. Você também pode clicar em
            "Gerar resumo de hoje".
          </p>
        </div>
      ) : null}

      {selected ? (
        <div className="overflow-hidden rounded-xl border border-dark-700 bg-dark-800">
          <div className="bg-black">
            <video
              key={selected.filename}
              controls
              preload="metadata"
              playsInline
              className="mx-auto h-auto max-h-[70vh] w-full"
              src={playerSrc ?? undefined}
            >
              Seu navegador não suporta a tag de vídeo.
            </video>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div>
              <p className="font-display text-base font-semibold text-[var(--color-text-primary)]">
                Resumo de {formatDay(selected.day)}
              </p>
              <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--color-text-muted)]">
                <span className="inline-flex items-center gap-1">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {selected.clips_count}{" "}
                  {selected.clips_count === 1 ? "clipe" : "clipes"}
                </span>
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {formatDuration(selected.duration_seconds)}
                </span>
                <span>{formatBytes(selected.size_bytes)}</span>
                <span>{selected.speed}× mais rápido</span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={playerSrc ?? "#"}
                download={selected.filename}
                className="inline-flex items-center gap-2 rounded-lg border border-dark-600 px-3 py-2 text-sm text-[var(--color-text-muted)] transition hover:bg-dark-700"
              >
                <Download className="h-4 w-4" />
                Baixar
              </a>
              <button
                type="button"
                onClick={() => void handleGenerateReel()}
                disabled={reelBusy}
                className="inline-flex items-center gap-2 rounded-lg border border-violet-400/40 bg-violet-500/15 px-3 py-2 text-sm font-semibold text-violet-200 transition hover:bg-violet-500/25 disabled:cursor-wait disabled:opacity-60"
              >
                {reelBusy ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <Smartphone className="h-4 w-4" />
                )}
                {reelBusy ? "Gerando Reel…" : "🎬 Gerar Reel p/ Redes"}
              </button>
              <button
                type="button"
                onClick={() => setPendingDelete(selected)}
                className="inline-flex items-center gap-2 rounded-lg border border-red-500/30 px-3 py-2 text-sm text-red-300 transition hover:bg-red-500/10"
              >
                <Trash2 className="h-4 w-4" />
                Excluir
              </button>
            </div>
            {reelError ? (
              <p
                role="alert"
                className="mt-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300"
              >
                {reelError}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {items.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => {
            const active = item.filename === selectedName;
            return (
              <button
                key={item.filename}
                type="button"
                onClick={() => setSelectedName(item.filename)}
                className={cn(
                  "group flex items-center gap-3 rounded-xl border p-3 text-left transition",
                  active
                    ? "border-emerald-500/60 bg-emerald-500/10"
                    : "border-dark-700 bg-dark-800 hover:border-dark-600 hover:bg-dark-700/60",
                )}
              >
                <span
                  className={cn(
                    "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg",
                    active
                      ? "bg-emerald-500/20 text-emerald-300"
                      : "bg-dark-700 text-[var(--color-text-muted)]",
                  )}
                >
                  <Play className="h-5 w-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-[var(--color-text-primary)]">
                    {formatDay(item.day)}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-[var(--color-text-muted)]">
                    {item.clips_count}{" "}
                    {item.clips_count === 1 ? "clipe" : "clipes"} ·{" "}
                    {formatDuration(item.duration_seconds)} ·{" "}
                    {formatBytes(item.size_bytes)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ) : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Remover resumo do dia"
        message={
          pendingDelete
            ? `Excluir o time-lapse de ${formatDay(pendingDelete.day)}? O vídeo será apagado do disco.`
            : ""
        }
        confirmLabel="Excluir"
        busy={deleting}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void confirmDelete()}
      />
      {/* Preview do Reel vertical (9:16) gerado para redes sociais */}
      {reelInfo ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Reel vertical gerado"
          onClick={() => setReelInfo(null)}
        >
          <div
            className="flex max-h-[92vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-dark-600 bg-dark-800 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-dark-700 px-4 py-3">
              <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
                🎬 Reel vertical (9:16)
              </h3>
              <button
                type="button"
                onClick={() => setReelInfo(null)}
                aria-label="Fechar preview do Reel"
                className="rounded-md p-1 text-[var(--color-text-muted)] transition hover:text-[var(--color-text-primary)]"
              >
                ✕
              </button>
            </div>
            <div className="flex flex-1 flex-col items-center gap-3 overflow-y-auto p-4">
              <video
                src={reelInfo.url}
                controls
                autoPlay
                muted
                playsInline
                className="max-h-[55vh] w-auto rounded-xl border border-dark-600 bg-black"
              />
              <a
                href={reelInfo.url}
                download
                className="inline-flex items-center gap-2 rounded-lg border border-violet-400/40 bg-violet-500/15 px-4 py-2 text-xs font-semibold text-violet-200 transition hover:bg-violet-500/25"
              >
                <Download className="h-4 w-4" />
                Baixar Reel (MP4 1080×1920)
              </a>
              <p className="text-center text-[11px] text-[var(--color-text-muted)]">
                Pronto para Instagram Reels, TikTok e YouTube Shorts.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
