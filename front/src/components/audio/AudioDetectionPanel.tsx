import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  AudioLines,
  Bot,
  ChevronDown,
  LoaderCircle,
  Music2,
  RefreshCw,
  Sparkles,
  Tags,
  Trash2,
  Wand2,
} from "lucide-react";
import type { AudioAnalysisStatus, AudioDetection, BirdSpecies } from "@/types";
import {
  deleteAudioDetection,
  fetchAudioAnalysisStatus,
  fetchAudioDetectionPage,
  fetchAudioNfcPage,
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

/** Espectrograma do canto com fallback elegante se o PNG ainda não existir. */
function SpectrogramPreview({ src, species }: { src: string; species: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="flex min-h-20 items-center justify-center rounded-xl border border-dashed border-dark-700 px-3 py-2 text-center text-xs text-[var(--color-text-muted)]">
        O espectrograma está sendo gerado a partir do clipe gravado.
      </div>
    );
  }
  return (
    <a
      href={src}
      target="_blank"
      rel="noreferrer"
      title="Abrir o espectrograma em tamanho real"
      className="group relative overflow-hidden rounded-xl border border-violet-500/20 bg-dark-950/60"
    >
      <img
        src={src}
        alt={`Espectrograma do canto de ${species}`}
        loading="lazy"
        onError={() => setFailed(true)}
        className="h-full max-h-40 w-full object-cover transition duration-300 group-hover:scale-[1.02]"
      />
      <span className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-gradient-to-t from-dark-950/90 to-transparent px-2.5 pb-1.5 pt-6 text-[10px] font-medium text-violet-100">
        <span>Espectrograma · frequência × tempo</span>
        <span className="text-[var(--color-text-muted)]">
          clique para ampliar
        </span>
      </span>
    </a>
  );
}

/**
 * Aba **Detecção Sonora** (Bioacústica / BirdNET).
 *
 * Lista os cantos identificados em **blocos de 5 itens**, carregados de forma
 * incremental pelo botão **"Ver mais…"** (sem paginação numérica), com player de
 * áudio integrado a cada card e ações para **identificar a espécie manualmente**
 * (vinculando ao card da Life List) ou **acionar a IA externa** sobre o
 * espectrograma do áudio — além de consultar a ficha ornitológica profunda.
 */
export function AudioDetectionPanel({ species }: Props) {
  const [items, setItems] = useState<AudioDetection[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [aiTarget, setAiTarget] = useState<AudioDetection | null>(null);
  /** "all" = todos os cantos · "nfc" = Viajantes Noturnos (Migração). */
  const [view, setView] = useState<"all" | "nfc">("all");

  const statusQuery = usePolling(fetchAudioAnalysisStatus, 8_000);

  /** Carrega o primeiro bloco (ou recarrega do zero a partir do topo). */
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data =
        view === "nfc"
          ? await fetchAudioNfcPage(PAGE_SIZE, 0)
          : await fetchAudioDetectionPage(PAGE_SIZE, 0);
      setItems(data.items);
      setTotal(data.total);
    } catch (cause) {
      setError(
        getErrorMessage(cause, "Não foi possível carregar as detecções sonoras."),
      );
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    void reload();
  }, [reload]);

  /** Anexa o próximo bloco de 5 ao final da lista ("Ver mais…"). */
  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    setError(null);
    try {
      const data =
        view === "nfc"
          ? await fetchAudioNfcPage(PAGE_SIZE, items.length)
          : await fetchAudioDetectionPage(PAGE_SIZE, items.length);
      setItems((current) => [...current, ...data.items]);
      setTotal(data.total);
    } catch (cause) {
      setError(
        getErrorMessage(cause, "Não foi possível carregar mais detecções."),
      );
    } finally {
      setLoadingMore(false);
    }
  }, [items.length, view]);

  const refresh = useCallback(() => {
    void reload();
    void statusQuery.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);

  // Enquanto houver mais itens no servidor do que já carregamos, mostra "Ver mais…".
  const hasMore = items.length < total;

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
    setItems((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
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
      // Remove o card da lista e ajusta o total (sem recarregar tudo).
      setItems((current) => current.filter((item) => item.id !== detection.id));
      setTotal((current) => Math.max(0, current - 1));
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
              {view === "nfc" ? "Viajantes Noturnos (Migração)" : "Detecção Sonora"}
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              {view === "nfc"
                ? "Chamados de voo (NFC) capturados na janela noturna · 22:00–05:00"
                : "Cantos identificados pelo BirdNET · ouça, identifique e consulte a IA"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Alternador: Todos os cantos ↔ Viajantes Noturnos (NFC) */}
          <div
            role="tablist"
            aria-label="Filtrar detecções"
            className="flex rounded-lg border border-dark-700 bg-dark-900 p-0.5"
          >
            <button
              type="button"
              role="tab"
              aria-selected={view === "all"}
              onClick={() => setView("all")}
              className={cn(
                "rounded-md px-3 py-1.5 text-[11px] font-semibold transition",
                view === "all"
                  ? "bg-violet-500/20 text-violet-200"
                  : "text-[var(--color-text-muted)] hover:text-violet-300",
              )}
            >
              Todos os cantos
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "nfc"}
              onClick={() => setView("nfc")}
              className={cn(
                "rounded-md px-3 py-1.5 text-[11px] font-semibold transition",
                view === "nfc"
                  ? "bg-indigo-500/20 text-indigo-200"
                  : "text-[var(--color-text-muted)] hover:text-indigo-300",
              )}
            >
              🌙 Viajantes Noturnos
            </button>
          </div>
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

      {/* Blocos de 5 itens, carregados incrementalmente */}
      {loading && items.length === 0 ? (
        <p className="flex items-center gap-2 rounded-xl border border-dark-700 bg-dark-800 p-6 text-sm text-[var(--color-text-muted)]">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          {view === "nfc"
            ? "Carregando viajantes noturnos…"
            : "Carregando detecções sonoras…"}
        </p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-dark-700 bg-dark-800/60 p-8 text-center text-sm text-[var(--color-text-muted)]">
          {view === "nfc"
            ? "Nenhum chamado de voo noturno registrado ainda. A escuta noturna (NFC) captura os chamados curtos das aves que cruzam o céu entre 22:00 e 05:00."
            : status?.status === "disabled"
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
                        {detection.is_nfc ? (
                          <span
                            title={`Chamado de voo migratório · noite ${detection.night_date ?? ""} · NFC ${Math.round((detection.nfc_score ?? 0) * 100)}%`}
                            className="rounded-full border border-indigo-400/30 bg-indigo-500/15 px-2 py-0.5 text-[10px] font-medium text-indigo-200"
                          >
                            🌙 NFC
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

                {/* Player de áudio + espectrograma visual lado a lado */}
                {detection.audio_url ? (
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    <AudioClipPlayer
                      src={detection.audio_url}
                      label={formatSpeciesLabel(detection.species)}
                    />
                    {detection.spectrogram_url ? (
                      <SpectrogramPreview
                        src={detection.spectrogram_url}
                        species={formatSpeciesLabel(detection.species)}
                      />
                    ) : (
                      <div className="flex min-h-20 items-center justify-center rounded-xl border border-dashed border-dark-700 px-3 py-2 text-center text-xs text-[var(--color-text-muted)]">
                        O espectrograma será gerado a partir do clipe gravado.
                      </div>
                    )}
                  </div>
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

      {/* Carregamento incremental: "Ver mais…" em vez de paginação numérica */}
      {total > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dark-700 bg-dark-800 px-4 py-2.5">
          <p className="text-xs text-[var(--color-text-muted)]">
            Mostrando {items.length} de {total} detecção(ões)
          </p>
          {hasMore ? (
            <button
              type="button"
              onClick={() => void loadMore()}
              disabled={loadingMore}
              className="inline-flex items-center gap-1.5 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs font-medium text-violet-200 transition hover:bg-violet-500/20 disabled:opacity-50"
            >
              {loadingMore ? (
                <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
              {loadingMore ? "Carregando…" : "Ver mais…"}
            </button>
          ) : (
            <span className="text-xs text-[var(--color-text-muted)]">
              Fim da lista
            </span>
          )}
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
