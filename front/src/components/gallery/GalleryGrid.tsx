import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  CheckCircle2,
  Download,
  Film,
  Filter,
  ImageDown,
  LoaderCircle,
  Moon,
  Play,
  RefreshCw,
  Trash2,
} from "lucide-react";
import type { BirdSpecies, BirdVisit, ReelInfo } from "@/types";
import {
  assignVisitSpecies,
  confirmVisit,
  deleteVisit,
  generateReel,
  getErrorMessage,
  identifyVisitExternal,
  resolveMediaUrl,
  visitCropDownloadUrl,
  visitCropUrl,
} from "@/services/api";
import { formatDateTime, formatPercent, formatSpeciesLabel } from "@/utils/format";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { VideoPlayerModal } from "@/components/common/VideoPlayerModal";
import { WeatherBadges } from "@/components/common/WeatherBadges";
import { SpeciesAiConsultModal } from "@/components/species/SpeciesAiConsultModal";
import { ReclassifySpeciesModal } from "@/components/gallery/ReclassifySpeciesModal";
import {
  isEcologicalUnknown,
  resolveEcological,
  resolveIdentificationBadge,
} from "@/utils/visits";

type Props = {
  visits: BirdVisit[];
  species: BirdSpecies[];
  loading?: boolean;
  onVisitDeleted: (visitId: string) => void;
  onVisitUpdated: () => void;
  /** Visita que deve abrir automaticamente no player (atalho do painel). */
  focusVisitId?: string | null;
  /** Avisa que o foco já foi consumido. */
  onFocusHandled?: () => void;
};

export function GalleryGrid({
  visits,
  species: catalogSpecies,
  loading,
  onVisitDeleted,
  onVisitUpdated,
  focusVisitId,
  onFocusHandled,
}: Props) {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [species, setSpecies] = useState("");
  const [identificationOverrides, setIdentificationOverrides] = useState<
    Record<string, BirdVisit>
  >({});
  const [identifyingVisitId, setIdentifyingVisitId] = useState<string | null>(null);
  const [assigningVisitId, setAssigningVisitId] = useState<string | null>(null);
  const [confirmingVisitId, setConfirmingVisitId] = useState<string | null>(null);
  const [assignmentError, setAssignmentError] = useState<{
    visitId: string;
    message: string;
  } | null>(null);
  const [identificationError, setIdentificationError] = useState<{
    visitId: string;
    message: string;
  } | null>(null);
  const [deletingVisit, setDeletingVisit] = useState<BirdVisit | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletedVisitIds, setDeletedVisitIds] = useState<Set<string>>(new Set());
  // Visita aberta na ficha ornitológica da IA externa (null = fechado).
  const [consultVisit, setConsultVisit] = useState<BirdVisit | null>(null);
  // Visitas cujo recorte (close-up) falhou ao carregar — esconde o inset.
  const [cropFailures, setCropFailures] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);
  // Visita cujo clipe está aberto no player de vídeo (null = fechado).
  const [playingVisit, setPlayingVisit] = useState<BirdVisit | null>(null);
  // Visita aberta no modal de reclassificação (null = fechado).
  const [reclassifyVisit, setReclassifyVisit] = useState<BirdVisit | null>(null);
  // Visita cujo Reel vertical está sendo gerado/preview (null = fechado).
  const [reelVisit, setReelVisit] = useState<BirdVisit | null>(null);
  const [reelInfo, setReelInfo] = useState<ReelInfo | null>(null);
  const [reelBusy, setReelBusy] = useState(false);
  const [reelError, setReelError] = useState<string | null>(null);

  // Atalho do painel "Visitas de Hoje": abre o player da visita solicitada
  // assim que ela aparece na lista (aguarda o primeiro carregamento).
  useEffect(() => {
    if (!focusVisitId) return;
    const target = visits.find((visit) => visit.id === focusVisitId);
    if (target) {
      setPlayingVisit(target);
      onFocusHandled?.();
      return;
    }
    if (!loading && visits.length > 0) onFocusHandled?.();
  }, [focusVisitId, visits, loading, onFocusHandled]);

  const currentVisits = useMemo(
    () =>
      visits
        .filter((visit) => !deletedVisitIds.has(visit.id))
        .map((visit) => identificationOverrides[visit.id] ?? visit),
    [visits, identificationOverrides, deletedVisitIds],
  );

  const speciesOptions = useMemo(() => {
    const set = new Set(currentVisits.map((v) => v.species));
    return Array.from(set).sort();
  }, [currentVisits]);

  const filtered = useMemo(() => {
    return currentVisits.filter((v) => {
      const t = new Date(v.detected_at).getTime();
      if (dateFrom) {
        const from = new Date(`${dateFrom}T00:00:00`).getTime();
        if (t < from) return false;
      }
      if (dateTo) {
        const to = new Date(`${dateTo}T23:59:59`).getTime();
        if (t > to) return false;
      }
      if (species && v.species !== species) return false;
      return true;
    });
  }, [currentVisits, dateFrom, dateTo, species]);

  const askExternalAi = async (visit: BirdVisit) => {
    setIdentifyingVisitId(visit.id);
    setIdentificationError(null);
    try {
      const identified = await identifyVisitExternal(visit.id, {
        // Preenche automaticamente o Catálogo Local / Life List com a espécie
        // identificada, usando a foto tratada como referência.
        addToCatalog: true,
      });
      setIdentificationOverrides((current) => ({
        ...current,
        [visit.id]: identified,
      }));
    } catch (error) {
      setIdentificationError({
        visitId: visit.id,
        message: getErrorMessage(error, "Falha ao identificar a ave"),
      });
    } finally {
      setIdentifyingVisitId(null);
    }
  };

  const updateVisitSpecies = async (visit: BirdVisit, speciesId: string) => {
    setAssigningVisitId(visit.id);
    setAssignmentError(null);
    try {
      const updated = await assignVisitSpecies(visit.id, speciesId || null);
      setIdentificationOverrides((current) => ({
        ...current,
        [visit.id]: updated,
      }));
      setToast(
        speciesId
          ? "Espécie associada ao registro."
          : "Associação de espécie removida.",
      );
      onVisitUpdated();
    } catch (error) {
      setAssignmentError({
        visitId: visit.id,
        message: getErrorMessage(error, "Não foi possível associar a espécie."),
      });
    } finally {
      setAssigningVisitId(null);
    }
  };

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  /** Gera (ou reaproveita) o Reel vertical 9:16 da visita e abre o preview. */
  const handleGenerateReel = async (visit: BirdVisit) => {
    setReelVisit(visit);
    setReelInfo(null);
    setReelError(null);
    setReelBusy(true);
    try {
      const info = await generateReel(visit.id);
      setReelInfo(info);
    } catch (cause) {
      setReelError(
        getErrorMessage(cause, "Não foi possível gerar o Reel desta visita."),
      );
    } finally {
      setReelBusy(false);
    }
  };

  /**
   * Confirma a espécie já associada e alimenta o aprendizado ativo.
   *
   * Diferente de apenas associar no dropdown: aqui o usuário atesta que a
   * detecção está correta, gerando uma amostra de treino de alta qualidade e a
   * assinatura visual do indivíduo.
   */
  const confirmDetection = async (visit: BirdVisit) => {
    setConfirmingVisitId(visit.id);
    setAssignmentError(null);
    try {
      const result = await confirmVisit(visit.id, {
        species_id: visit.species_id,
        species_name: visit.assigned_species_common_name ?? visit.species,
      });
      setToast(
        result.training_queued
          ? "Detecção confirmada — amostra enviada ao Bem-Te-Vi Core."
          : result.training_reason ||
              "Detecção confirmada para a memória do jardim.",
      );
      onVisitUpdated();
    } catch (error) {
      setAssignmentError({
        visitId: visit.id,
        message: getErrorMessage(error, "Não foi possível confirmar a detecção."),
      });
    } finally {
      setConfirmingVisitId(null);
    }
  };

  const confirmDeleteVisit = async () => {
    if (!deletingVisit) return;
    const visit = deletingVisit;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteVisit(visit.id);
      setDeletedVisitIds((current) => new Set(current).add(visit.id));
      setDeletingVisit(null);
      setToast("Registro e mídias associados foram excluídos.");
      onVisitDeleted(visit.id);
    } catch (error) {
      setDeleteError(getErrorMessage(error, "Não foi possível excluir o registro."));
      setDeletingVisit(null);
    } finally {
      setDeleting(false);
    }
  };

  const exportCsv = () => {
    const header = [
      "id",
      "detected_at",
      "species",
      "confidence",
      "camera_name",
      "camera_id",
      "zone_id",
      "dwell_seconds",
      "thumbnail_url",
      "clip_url",
    ];
    const rows = filtered.map((v) =>
      [
        v.id,
        v.detected_at,
        v.species,
        v.confidence,
        v.camera_name ?? "",
        v.camera_id,
        v.zone_id ?? "",
        v.dwell_seconds,
        v.thumbnail_url ?? "",
        v.clip_url ?? "",
      ]
        .map((cell) => `"${String(cell).replaceAll('"', '""')}"`)
        .join(","),
    );
    const csv = [header.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bem-te-vi-monitor-visitas-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
            Galeria de capturas
          </h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            Thumbnails locais · {filtered.length} registro(s)
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            A consulta externa envia somente o recorte da ave e ocorre apenas quando você clicar.
          </p>
        </div>
        <button
          type="button"
          onClick={exportCsv}
          disabled={filtered.length === 0}
          className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-400 transition hover:bg-emerald-500/20 disabled:opacity-40"
        >
          <Download className="h-4 w-4" />
          Exportar CSV
        </button>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-dark-700 bg-dark-800 p-3">
        <Filter className="mb-2 h-4 w-4 text-[var(--color-text-muted)]" />
        <label className="text-xs text-[var(--color-text-muted)]">
          De
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className={filterInput}
          />
        </label>
        <label className="text-xs text-[var(--color-text-muted)]">
          Até
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className={filterInput}
          />
        </label>
        <label className="text-xs text-[var(--color-text-muted)]">
          Espécie
          <select
            value={species}
            onChange={(e) => setSpecies(e.target.value)}
            className={filterInput}
          >
            <option value="">Todas</option>
            {speciesOptions.map((s) => (
              <option key={s} value={s}>
                {formatSpeciesLabel(s)}
              </option>
            ))}
          </select>
        </label>
        {(dateFrom || dateTo || species) && (
          <button
            type="button"
            onClick={() => {
              setDateFrom("");
              setDateTo("");
              setSpecies("");
            }}
            className="mb-0.5 text-xs text-emerald-400 hover:text-emerald-500"
          >
            Limpar filtros
          </button>
        )}
      </div>

      {loading && visits.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">Carregando capturas…</p>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-dark-700 px-6 py-12 text-center text-sm text-[var(--color-text-muted)]">
          Nenhuma captura encontrada para os filtros selecionados.
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((visit) => {
            const thumb = resolveMediaUrl(visit.thumbnail_url ?? visit.thumbnail_path);
            const clip = resolveMediaUrl(visit.clip_url ?? visit.clip_path);
            const alreadyExternallyIdentified =
              visit.metadata.identification_status === "Identificado por IA Externa";
            // Captura registrada com o realce de visão noturna ativo.
            const nightCapture = Boolean(visit.metadata?.night_mode);
            const genericSpecies = [
              "bird",
              "ave",
              "ave (genérica)",
              "ave não identificada",
              "não identificada",
              "unidentified",
            ].includes(visit.species.trim().toLocaleLowerCase("pt-BR"));
            // Inteligência biológica: status ecológico, bando e comportamento.
            // O selo vem dos metadados da visita (IA na captura/identificação) ou,
            // na falta, da espécie associada no catálogo local.
            const catalogEntry = visit.species_id
              ? catalogSpecies.find((item) => item.id === visit.species_id)
              : undefined;
            const ecological = resolveEcological(visit, catalogEntry);
            // O selo "⚪ Status desconhecido" é omitido: a identificação já é
            // comunicada pelo badge elegante ("Identificado pelo Bem-Te-Vi Core" /
            // "Espécie Confirmada") exibido no topo do card.
            const ecologicalBadge =
              ecological && !isEcologicalUnknown(ecological)
                ? (ecological.badge ?? undefined)
                : undefined;
            const ecologicalStatus = ecological?.status;
            const ecologicalLabel = ecological?.label ?? "";
            const isRareSpecies = ecologicalStatus === "rara";
            const individualsPeak = visit.metadata?.individuals_peak ?? 0;
            const individualsSummary = visit.metadata?.individuals_summary;
            const behaviorLabel = visit.metadata?.behavior_label;
            const behaviorIcon = visit.metadata?.behavior_icon;
            // Índice de certeza da IA (barra de precisão) e anotação ornitológica.
            const confidencePct = Math.round(
              Math.min(1, Math.max(0, visit.confidence)) * 100,
            );
            const confidenceTone =
              visit.confidence >= 0.8
                ? "bg-emerald-400"
                : visit.confidence >= 0.5
                  ? "bg-amber-400"
                  : "bg-red-400";
            const aiAnnotation = visit.metadata?.ai_analysis?.annotation;
            // Selo de identificação (substitui a antiga tag "Desconhecido").
            const identificationBadge = resolveIdentificationBadge(visit);
            return (
              <article
                key={visit.id}
                className="overflow-hidden rounded-xl border border-dark-700 bg-dark-800"
              >
                <div className="relative aspect-video bg-dark-900">
                  {thumb ? (
                    <img
                      src={thumb}
                      alt={formatSpeciesLabel(visit.species)}
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-xs text-[var(--color-text-muted)]">
                      Sem thumbnail
                    </div>
                  )}
                  {clip ? (
                    <button
                      type="button"
                      onClick={() => setPlayingVisit(visit)}
                      aria-label={`Reproduzir clipe de ${formatSpeciesLabel(visit.species)}`}
                      className="group absolute inset-0 flex items-center justify-center bg-black/0 transition hover:bg-black/40"
                    >
                      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-black/60 text-emerald-300 transition group-hover:scale-105 group-hover:bg-black/80">
                        <Play className="h-5 w-5 translate-x-0.5 fill-current" />
                      </span>
                    </button>
                  ) : null}
                  {nightCapture ? (
                    <span
                      className="absolute right-2 top-2 flex items-center gap-1 rounded-md bg-indigo-500/85 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                      title="Captura em visão noturna (infravermelho)"
                    >
                      <Moon className="h-3 w-3" />
                      Noturno
                    </span>
                  ) : null}
                  {visit.metadata?.enhanced ? (
                    <span
                      className="absolute left-2 top-2 rounded-md bg-emerald-500/85 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                      title="Foto tratada automaticamente (alta definição)"
                    >
                      HD
                    </span>
                  ) : null}
                  {/* Recorte focado da ave (close-up tratado pelo Bem-Te-Vi Core):
                      clicar nele abre **direto** a ficha ornitológica da IA
                      externa daquela ave — sem passo extra. */}
                  {visit.metadata?.crop_path && !cropFailures.has(visit.id) ? (
                    <button
                      type="button"
                      onClick={() => setConsultVisit(visit)}
                      title="Abrir a ficha ornitológica (IA) desta ave"
                      aria-label={`Abrir a ficha ornitológica da IA para ${formatSpeciesLabel(visit.species)}`}
                      className="group/crop absolute bottom-2 left-2 flex flex-col items-center gap-1 rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
                    >
                      <img
                        src={visitCropUrl(visit.id)}
                        alt={`Recorte focado da ave: ${formatSpeciesLabel(visit.species)}`}
                        onError={() =>
                          setCropFailures((current) =>
                            new Set(current).add(visit.id),
                          )
                        }
                        className="h-16 w-16 rounded-xl border-2 border-emerald-400/50 bg-black object-cover shadow-xl transition group-hover/crop:scale-105 group-hover/crop:border-violet-400"
                      />
                      <span className="rounded-full bg-black/70 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-200 backdrop-blur transition group-hover/crop:text-violet-200">
                        Recorte · IA
                      </span>
                    </button>
                  ) : null}
                </div>
                <div className="space-y-1 p-3">
                  <p className="font-medium text-[var(--color-text-primary)]">
                    {formatSpeciesLabel(visit.species)}
                  </p>
                  {identificationBadge ? (
                    <span
                      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${identificationBadge.className}`}
                      title={identificationBadge.title}
                    >
                      <CheckCircle2 className="h-2.5 w-2.5" />
                      {identificationBadge.label}
                    </span>
                  ) : null}
                  {visit.assigned_species_scientific_name ? (
                    <p className="text-xs italic text-[var(--color-text-muted)]">
                      {visit.assigned_species_scientific_name}
                    </p>
                  ) : null}
                  {ecologicalBadge || individualsPeak > 1 || behaviorLabel ? (
                    <div className="flex flex-wrap items-center gap-1 pt-1">
                      {ecologicalBadge ? (
                        <span
                          className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
                            isRareSpecies
                              ? "bg-amber-400/90 text-amber-950"
                              : "bg-dark-700 text-[var(--color-text-primary)]"
                          }`}
                          title={`Status ecológico: ${ecologicalLabel}`}
                        >
                          {ecologicalBadge}
                        </span>
                      ) : null}
                      {individualsPeak > 1 ? (
                        <span
                          className="rounded-md bg-sky-500/85 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                          title={
                            individualsSummary ?? `${individualsPeak} aves simultâneas`
                          }
                        >
                          👥 {individualsPeak}
                        </span>
                      ) : null}
                      {behaviorLabel ? (
                        <span
                          className="rounded-md bg-dark-700 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-text-primary)]"
                          title={`Comportamento: ${behaviorLabel}`}
                        >
                          {behaviorIcon} {behaviorLabel}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {/* Índice de certeza da IA (barra de precisão da classificação). */}
                  <div className="pt-1.5">
                    <div className="mb-1 flex items-center justify-between text-[10px] text-[var(--color-text-muted)]">
                      <span className="inline-flex items-center gap-1">
                        <Bot className="h-3 w-3 text-emerald-400/80" />
                        Índice de certeza da IA
                      </span>
                      <span className="font-mono font-semibold text-emerald-300">
                        {confidencePct}%
                      </span>
                    </div>
                    <div
                      className="h-1.5 w-full overflow-hidden rounded-full bg-dark-700"
                      role="meter"
                      aria-valuenow={confidencePct}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label="Índice de certeza da IA"
                    >
                      <div
                        className={`h-full rounded-full ${confidenceTone} transition-all`}
                        style={{ width: `${confidencePct}%` }}
                      />
                    </div>
                  </div>
                  {aiAnnotation ? (
                    <p
                      className="pt-1 text-[11px] italic leading-snug text-emerald-200/80"
                      title="Anotação ornitológica gerada pela IA"
                    >
                      🧠 {aiAnnotation}
                    </p>
                  ) : null}
                  <label className="block pt-1 text-xs text-[var(--color-text-muted)]">
                    Associar ao catálogo
                    <select
                      value={visit.species_id ?? ""}
                      onChange={(event) =>
                        void updateVisitSpecies(visit, event.target.value)
                      }
                      disabled={assigningVisitId !== null}
                      className={`${filterInput} w-full disabled:opacity-60`}
                    >
                      <option value="">Sem associação</option>
                      {catalogSpecies.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.common_name} · {item.scientific_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {visit.species_id ? (
                    <button
                      type="button"
                      onClick={() => void confirmDetection(visit)}
                      disabled={confirmingVisitId !== null || assigningVisitId !== null}
                      title="Confirmar que esta detecção está correta e ensinar o Core"
                      className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-2.5 py-1.5 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:cursor-wait disabled:opacity-60"
                    >
                      {confirmingVisitId === visit.id ? (
                        <>
                          <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                          Confirmando…
                        </>
                      ) : (
                        <>
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Confirmar detecção
                        </>
                      )}
                    </button>
                  ) : null}
                  {assignmentError?.visitId === visit.id ? (
                    <p role="alert" className="text-xs text-red-300">
                      {assignmentError.message}
                    </p>
                  ) : null}
                  {/* Exportação do recorte HD + curadoria (reclassificação). */}
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    {visit.metadata?.crop_path ? (
                      <a
                        href={visitCropDownloadUrl(visit.id)}
                        download
                        title="Baixar o recorte da ave em alta resolução (JPEG HD)"
                        className="inline-flex items-center gap-1.5 rounded-lg border border-sky-400/40 bg-sky-500/10 px-2.5 py-1.5 text-xs font-semibold text-sky-200 transition hover:bg-sky-500/20"
                      >
                        <ImageDown className="h-3.5 w-3.5" />
                        Baixar Recorte HD (Crop)
                      </a>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setReclassifyVisit(visit)}
                      title="A associação está errada? Escolha a espécie correta — o recorte é salvo para o retreinamento do Core"
                      className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-2.5 py-1.5 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/20"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Associação Incorreta / Reclassificar
                    </button>
                  </div>
                  {alreadyExternallyIdentified ? (
                    <p className="text-[11px] text-emerald-300">
                      Identificado por IA Externa
                    </p>
                  ) : genericSpecies ? (
                    <button
                      type="button"
                      onClick={() => void askExternalAi(visit)}
                      disabled={identifyingVisitId !== null}
                      className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-violet-400/40 bg-violet-500/15 px-2.5 py-2 text-xs font-semibold text-violet-200 transition hover:bg-violet-500/25 disabled:cursor-wait disabled:opacity-60"
                    >
                      {identifyingVisitId === visit.id ? (
                        <>
                          <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                          Analisando ave...
                        </>
                      ) : (
                        <>
                          <Bot className="h-3.5 w-3.5" />
                          🤖 Perguntar à IA Externa
                        </>
                      )}
                    </button>
                  ) : null}
                  {!genericSpecies ? (
                    <button
                      type="button"
                      onClick={() => setConsultVisit(visit)}
                      title="Ficha ornitológica completa (nome científico, família, conservação, dieta, habitat, curiosidades)"
                      className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-violet-400/40 bg-violet-500/15 px-2.5 py-2 text-xs font-semibold text-violet-200 transition hover:bg-violet-500/25"
                    >
                      <Bot className="h-3.5 w-3.5" />
                      🔎 Ficha ornitológica (IA)
                    </button>
                  ) : null}
                  {identificationError?.visitId === visit.id ? (
                    <p role="alert" className="text-xs text-red-300">
                      {identificationError.message}
                    </p>
                  ) : null}
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {formatDateTime(visit.detected_at)} · {formatPercent(visit.confidence)}
                  </p>
                  <WeatherBadges
                    temperature={visit.temperature}
                    humidity={visit.humidity}
                    weather_code={visit.weather_code}
                    className="pt-1"
                  />
                  <p className="truncate text-xs text-[var(--color-text-muted)]">
                    {visit.camera_name ?? visit.camera_id}
                  </p>
                  {clip ? (
                    <button
                      type="button"
                      onClick={() => setPlayingVisit(visit)}
                      className="mt-1 inline-flex items-center gap-1 pt-1 text-xs font-medium text-emerald-400 transition hover:text-emerald-500"
                    >
                      <Play className="h-3.5 w-3.5 fill-current" />
                      Reproduzir clipe
                    </button>
                  ) : null}
                  {clip ? (
                    <button
                      type="button"
                      onClick={() => void handleGenerateReel(visit)}
                      disabled={reelBusy}
                      title="Gerar Reel vertical (9:16) com marca d'água, espécie e temperatura"
                      className="mt-1 ml-3 inline-flex items-center gap-1 pt-1 text-xs font-medium text-violet-400 transition hover:text-violet-300 disabled:opacity-50"
                    >
                      {reelBusy ? (
                        <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Film className="h-3.5 w-3.5" />
                      )}
                      {reelBusy ? "Gerando Reel…" : "🎬 Gerar Reel p/ Redes"}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteError(null);
                      setDeletingVisit(visit);
                    }}
                    aria-label={`Excluir registro de ${formatSpeciesLabel(visit.species)}`}
                    className="mt-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-300 transition hover:bg-red-500/10"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Excluir registro
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
      {deleteError ? (
        <p role="alert" className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {deleteError}
        </p>
      ) : null}
      {toast ? (
        <p role="status" className="fixed bottom-5 right-5 z-50 rounded-lg border border-emerald-500/30 bg-emerald-950 px-4 py-3 text-sm text-emerald-300 shadow-xl">
          {toast}
        </p>
      ) : null}
      <ConfirmDialog
        open={deletingVisit !== null}
        title="Excluir registro da Galeria?"
        message={
          deletingVisit
            ? `Deseja realmente excluir o registro de ${formatSpeciesLabel(deletingVisit.species)} e suas imagens e clipes associados? Esta ação não pode ser desfeita.`
            : ""
        }
        confirmLabel="Excluir registro"
        busy={deleting}
        onCancel={() => setDeletingVisit(null)}
        onConfirm={() => void confirmDeleteVisit()}
      />
      <VideoPlayerModal
        open={playingVisit !== null}
        title={
          playingVisit
            ? `${formatSpeciesLabel(playingVisit.species)} · ${formatDateTime(playingVisit.detected_at)}`
            : ""
        }
        src={
          playingVisit
            ? resolveMediaUrl(playingVisit.clip_url ?? playingVisit.clip_path)
            : null
        }
        species={playingVisit?.species ?? null}
        confidence={playingVisit?.confidence ?? null}
        scientificName={playingVisit?.assigned_species_scientific_name ?? null}
        ecologicalBadge={
          (playingVisit?.metadata?.ecological?.badge as string | undefined) ??
          (playingVisit?.metadata?.ai_analysis?.ecological_badge as string | undefined) ??
          null
        }
        individualsPeak={playingVisit?.metadata?.individuals_peak ?? null}
        onClose={() => setPlayingVisit(null)}
      />
      <SpeciesAiConsultModal
        visit={consultVisit}
        onClose={() => setConsultVisit(null)}
      />
      {/* Modal de curadoria: "Associação Incorreta / Reclassificar". */}
      <ReclassifySpeciesModal
        visit={reclassifyVisit}
        species={catalogSpecies}
        onClose={() => setReclassifyVisit(null)}
        onReclassified={(updated) => {
          setIdentificationOverrides((current) => ({
            ...current,
            [updated.id]: updated,
          }));
          setToast(
            "Correção salva — o recorte foi enviado para o retreinamento do Core.",
          );
          onVisitUpdated();
        }}
      />
      {/* Preview do Reel vertical (9:16) gerado para redes sociais */}
      {reelVisit ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Reel vertical gerado"
          onClick={() => setReelVisit(null)}
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
                onClick={() => setReelVisit(null)}
                aria-label="Fechar preview do Reel"
                className="rounded-md p-1 text-[var(--color-text-muted)] transition hover:text-[var(--color-text-primary)]"
              >
                ✕
              </button>
            </div>
            <div className="flex flex-1 flex-col items-center gap-3 overflow-y-auto p-4">
              {reelBusy ? (
                <div className="flex flex-col items-center gap-2 py-10 text-sm text-[var(--color-text-muted)]">
                  <LoaderCircle className="h-6 w-6 animate-spin text-violet-300" />
                  Gerando vídeo vertical…
                </div>
              ) : reelError ? (
                <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                  {reelError}
                </p>
              ) : reelInfo ? (
                <>
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
                </>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

const filterInput =
  "mt-1 block rounded-lg border border-dark-700 bg-dark-900 px-2 py-1.5 text-sm text-[var(--color-text-primary)] outline-none focus:border-emerald-500/50";
