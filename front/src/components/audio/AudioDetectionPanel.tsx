import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  AudioLines,
  Bot,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  Music2,
  RefreshCw,
  Sparkles,
  Tags,
  Trash2,
  Wand2,
} from "lucide-react";
import type { AudioAnalysisStatus, AudioDetection, AudioDetectionPage, BirdSpecies } from "@/types";
import {
  deleteAudioDetection,
  fetchAudioAnalysisStatus,
  fetchAudioDetectionPage,
  getErrorMessage,
  identifyAudioDetection,
  identifyAudioExternal,
} from "@/services/api";
import { usePolling } from "@/hooks/usePolling";
import { formatDateTime, formatPercent, formatSpeciesLabel, isGenericSpecies } from "@/utils/format";
import { WeatherBadges } from "@/components/common/WeatherBadges";
import { AudioClipPlayer } from "@/components/audio/AudioClipPlayer";
import { AudioAiConsultModal } from "@/components/audio/AudioAiConsultModal";
import { cn } from "@/utils/cn";

type Props = {
  /** Espécies da Life List ("Minhas Aves") para a identificação manual. */
  species: BirdSpecies[];
};

const PAGE_SIZE = 5;

const statusLabels: Record<AudioAnalysisStatus["status"], string> = {
  disabled: "Desativada",
  starting: "Iniciando",
  monitoring: "Monitorando",
  no_cameras: "Sem câmeras compatíveis",
  error: "Indisponível",
};

/**
 * Aba **Detecção Sonora** (Bioacústica / BirdNET).
 *
 * Lista os cantos identificados em blocos de 5 itens por página, com paginação
 * fluida, player de áudio integrado a cada card e ações para **identificar a
 * espécie manualmente** (vinculando ao card da Life List) ou **acionar a IA
 * externa** sobre o espectrograma do áudio — além de consultar a ficha
 * ornitológica profunda da espécie.
 */
export function AudioDetectionPanel({ species }: Props) {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<AudioDetectionPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [aiTarget, setAiTarget] = useState<AudioDetection | null>(null);

  const statusQuery = usePolling(fetchAudioAnalysisStatus, 8_000);

  const load = useCallback(
    async (targetOffset: number) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchAudioDetectionPage(PAGE_SIZE, targetOffset);
        setPage(data);
      } catch (cause) {
        setError(
          getErrorMessage(cause, "Não foi possível carregar as detecções sonoras."),
        );
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load(offset);
  }, [load, offset]);

  const refresh = useCallback(() => {
    void load(offset);
    void statusQuery.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, offset]);

  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const items = page?.items ?? [];

  const speciesOptions = useMemo(
    () =>
      [...species]
        .sort((a, b) => a.common_name.localeCompare(b.common_name, "pt-BR"))
        .map((sp) => ({
          id: sp.id,
          label: `${sp.common_name}${
            sp.scientific_name ? ` (${sp.scientific_name})` : ""
          }`,
        })),
    [species],
  );

  const applyUpdated = (updated: AudioDetection) => {
    setPage((current) =>
      current
        ? {
            ...current,
            items: current.items.map((item) =>
              item.id === updated.id ? updated : item,
            ),
          }
        : current,
    );
  };

  const handleManualIdentify = async (
    detection: AudioDetection,
    speciesId: string,
  ) => {
    if (!speciesId) return;
    setBusyId(detection.id);
    setNotice(null);
    try {
      const updated = await identifyAudioDetection(detection.id, {
        species_id: speciesId,
      });
      applyUpdated(updated);
      setNotice(
        `Canto associado a "${formatSpeciesLabel(updated.species)}" na Life List.`,
      );
    } catch (cause) {
      setError(getErrorMessage(cause, "Não foi possível associar a espécie."));
    } finally {
      setBusyId(null);
    }
  };

  const handleIdentifyExternal = async (detection: AudioDetection) => {
    setBusyId(detection.id);
    setNotice(null);
    setError(null);
    try {
      const updated = await identifyAudioExternal(detection.id, true);
      applyUpdated(updated);
      setNotice(
        `IA externa identificou: "${formatSpeciesLabel(updated.species)}" (${updated.scientific_name}).`,
      );
    } catch (cause) {
      setError(
        getErrorMessage(
          cause,
          "Não foi possível acionar a IA externa para esta detecção.",
        ),
      );
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (detection: AudioDetection) => {
    const ok = window.confirm(
      `Remover a detecção sonora de "${formatSpeciesLabel(detection.species)}"?`,
    );
    if (!ok) return;
    setBusyId(detection.id);
    try {
      await deleteAudioDetection(detection.id);
      setNotice("Detecção sonora removida do histórico.");
      // Recua uma página se a última ficou vazia.
      const nextOffset = items.length === 1 && offset > 0 ? offset - PAGE_SIZE : offset;
      if (nextOffset !== offset) setOffset(nextOffset);
      else await load(offset);
      void statusQuery.refresh();
    } catch (cause) {
      setError(getErrorMessage(cause, "Não foi possível remover a detecção."));
    } finally {
      setBusyId(null);
    }
  };

  const status = statusQuery.data;

  return (
    <section className="space-y-4">
      {/* Cabeçalho da aba */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dark-700 bg-dark-800 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-violet-500/15 p-2.5 text-violet-300">
            <AudioLines className="h-5 w-5" />
          </span>
          <div>
            <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
              Detecção Sonora
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Cantos identificados pelo BirdNET · ouça, identifique e consulte a IA
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {status ? (
            <span
              className={cn(
                "rounded-full border px-2.5 py-1 text-[10px] font-medium",
                status.status === "monitoring"
                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300"
                  : status.status === "error"
                    ? "border-red-500/25 bg-red-500/10 text-red-300"
                    : "border-dark-700 bg-dark-900 text-[var(--color-text-muted)]",
              )}
            >
              {statusLabels[status.status]}
              {status.status === "monitoring"
                ? ` · ${status.monitored_cameras} câmera(s)`
                : ""}
            </span>
          ) : null}
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            aria-label="Atualizar detecções sonoras"
            className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:text-violet-300 disabled:opacity-50"
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {status && status.status === "monitoring" && status.message ? (
        <p className="text-xs text-[var(--color-text-muted)]">{status.message}</p>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </p>
      ) : null}

      {notice ? (
        <p className="flex items-center gap-2 rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
          <Sparkles className="h-4 w-4 shrink-0" />
          {notice}
        </p>
      ) : null}

      {/* Blocos de 5 itens por página */}
      {loading && !page ? (
        <p className="flex items-center gap-2 rounded-xl border border-dark-700 bg-dark-800 p-6 text-sm text-[var(--color-text-muted)]">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Carregando detecções sonoras…
        </p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-dark-700 bg-dark-800/60 p-8 text-center text-sm text-[var(--color-text-muted)]">
          {status?.status === "disabled"
            ? "A análise sonora está desativada. Habilite a Bioacústica em uma câmera para começar."
            : "Nenhum canto identificado ainda. As detecções do BirdNET aparecerão aqui."}
        </p>
      ) : (
        <ul className="space-y-3">
          {items.map((detection) => {
            const generic = isGenericSpecies(detection.species);
            const busy = busyId === detection.id;
            return (
              <li
                key={detection.id}
                className="rounded-2xl border border-dark-700 bg-dark-800/80 p-4 shadow-[0_10px_40px_-24px_rgba(139,92,246,0.6)] backdrop-blur"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="rounded-xl bg-violet-500/15 p-2.5 text-violet-300">
                      <Music2 className="h-4 w-4" />
                    </span>
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
                        {formatSpeciesLabel(detection.species)}
                        {generic ? (
                          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-200">
                            Não identificado
                          </span>
                        ) : null}
                        {detection.identification_status ? (
                          <span className="rounded-full border border-violet-400/25 bg-violet-400/10 px-2 py-0.5 text-[10px] font-medium text-violet-200">
                            {detection.identification_status}
                          </span>
                        ) : null}
                        {detection.species_id ? (
                          <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-200">
                            Na Life List
                          </span>
                        ) : null}
                      </p>
                      <p className="text-xs italic text-[var(--color-text-muted)]">
                        {detection.scientific_name || "—"}
                      </p>
                      <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                        {detection.camera_name} · {formatDateTime(detection.detected_at)}
                        {detection.linked_visit_id ? " · visita visual associada" : ""}
                      </p>
                      <WeatherBadges
                        temperature={detection.temperature}
                        humidity={detection.humidity}
                        weather_code={detection.weather_code}
                        className="mt-1"
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded-full border border-violet-400/20 bg-violet-400/10 px-2.5 py-1 text-xs font-semibold text-violet-200">
                      {formatPercent(detection.confidence)}
                    </span>
                    <button
                      type="button"
                      onClick={() => void handleDelete(detection)}
                      disabled={busy}
                      aria-label="Remover detecção"
                      className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Player de áudio integrado ao card */}
                {detection.audio_url ? (
                  <AudioClipPlayer
                    src={detection.audio_url}
                    label={formatSpeciesLabel(detection.species)}
                    className="mt-3"
                  />
                ) : (
                  <p className="mt-3 rounded-lg border border-dashed border-dark-700 px-3 py-2 text-xs text-[var(--color-text-muted)]">
                    Sem clipe de áudio gravado para esta detecção.
                  </p>
                )}

                {/* Ações de identificação */}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                    <Tags className="h-3.5 w-3.5" />
                    Associar à espécie:
                    <select
                      value={detection.species_id ?? ""}
                      onChange={(e) =>
                        void handleManualIdentify(detection, e.target.value)
                      }
                      disabled={busy}
                      className="rounded-md border border-dark-700 bg-dark-900/70 px-2 py-1.5 text-xs text-[var(--color-text-primary)] disabled:opacity-50"
                    >
                      <option value="">Selecionar da Life List…</option>
                      {speciesOptions.map((opt) => (
                        <option key={opt.id} value={opt.id}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <button
                    type="button"
                    onClick={() => void handleIdentifyExternal(detection)}
                    disabled={busy || !detection.audio_url}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs font-medium text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-50"
                  >
                    {busy ? (
                      <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Wand2 className="h-3.5 w-3.5" />
                    )}
                    Identificar com IA Externa
                  </button>

                  <button
                    type="button"
                    onClick={() => setAiTarget(detection)}
                    disabled={busy || generic}
                    title={
                      generic
                        ? "Identifique a espécie antes de consultar a IA."
                        : undefined
                    }
                    className="inline-flex items-center gap-1.5 rounded-lg border border-dark-600 px-3 py-1.5 text-xs font-medium text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)] disabled:opacity-50"
                  >
                    <Bot className="h-3.5 w-3.5" />
                    Perguntar à IA Externa
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {/* Paginação fluida */}
      {total > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dark-700 bg-dark-800 px-4 py-2.5">
          <p className="text-xs text-[var(--color-text-muted)]">
            {total} detecção(ões) · página {currentPage} de {pageCount}
          </p>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0 || loading}
              className="inline-flex items-center gap-1 rounded-md border border-dark-700 px-2.5 py-1.5 text-xs text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)] disabled:opacity-40"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Anterior
            </button>
            {Array.from({ length: pageCount }, (_, index) => index)
              .slice(
                Math.max(0, currentPage - 3),
                Math.min(pageCount, Math.max(0, currentPage - 3) + 5),
              )
              .map((index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => setOffset(index * PAGE_SIZE)}
                  disabled={loading}
                  className={cn(
                    "h-7 w-7 rounded-md text-xs font-medium transition",
                    index === currentPage - 1
                      ? "bg-violet-500/20 text-violet-200"
                      : "text-[var(--color-text-muted)] hover:bg-dark-700",
                  )}
                >
                  {index + 1}
                </button>
              ))}
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total || loading}
              className="inline-flex items-center gap-1 rounded-md border border-dark-700 px-2.5 py-1.5 text-xs text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)] disabled:opacity-40"
            >
              Próxima
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      ) : null}

      {aiTarget ? (
        <AudioAiConsultModal
          detection={aiTarget}
          onClose={() => setAiTarget(null)}
        />
      ) : null}
    </section>
  );
}
