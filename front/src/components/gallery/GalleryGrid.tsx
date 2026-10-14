import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  Download,
  Filter,
  LoaderCircle,
  Trash2,
} from "lucide-react";
import type { BirdSpecies, BirdVisit } from "@/types";
import {
  assignVisitSpecies,
  deleteVisit,
  getErrorMessage,
  identifyVisitExternal,
  resolveMediaUrl,
} from "@/services/api";
import { formatDateTime, formatPercent, formatSpeciesLabel } from "@/utils/format";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";

type Props = {
  visits: BirdVisit[];
  species: BirdSpecies[];
  loading?: boolean;
  onVisitDeleted: (visitId: string) => void;
  onVisitUpdated: () => void;
};

export function GalleryGrid({
  visits,
  species: catalogSpecies,
  loading,
  onVisitDeleted,
  onVisitUpdated,
}: Props) {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [species, setSpecies] = useState("");
  const [identificationOverrides, setIdentificationOverrides] = useState<
    Record<string, BirdVisit>
  >({});
  const [identifyingVisitId, setIdentifyingVisitId] = useState<string | null>(null);
  const [assigningVisitId, setAssigningVisitId] = useState<string | null>(null);
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
  const [toast, setToast] = useState<string | null>(null);

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
      const identified = await identifyVisitExternal(visit.id);
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
    a.download = `aviawatch-visitas-${new Date().toISOString().slice(0, 10)}.csv`;
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
            const genericSpecies = [
              "bird",
              "ave",
              "ave (genérica)",
              "ave não identificada",
              "não identificada",
              "unidentified",
            ].includes(visit.species.trim().toLocaleLowerCase("pt-BR"));
            return (
              <article
                key={visit.id}
                className="overflow-hidden rounded-xl border border-dark-700 bg-dark-800"
              >
                <div className="aspect-video bg-dark-900">
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
                </div>
                <div className="space-y-1 p-3">
                  <p className="font-medium text-[var(--color-text-primary)]">
                    {formatSpeciesLabel(visit.species)}
                  </p>
                  {visit.assigned_species_scientific_name ? (
                    <p className="text-xs italic text-[var(--color-text-muted)]">
                      {visit.assigned_species_scientific_name}
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
                  {assignmentError?.visitId === visit.id ? (
                    <p role="alert" className="text-xs text-red-300">
                      {assignmentError.message}
                    </p>
                  ) : null}
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
                  {identificationError?.visitId === visit.id ? (
                    <p role="alert" className="text-xs text-red-300">
                      {identificationError.message}
                    </p>
                  ) : null}
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {formatDateTime(visit.detected_at)} · {formatPercent(visit.confidence)}
                  </p>
                  <p className="truncate text-xs text-[var(--color-text-muted)]">
                    {visit.camera_name ?? visit.camera_id}
                  </p>
                  {clip ? (
                    <a
                      href={clip}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-block pt-1 text-xs font-medium text-emerald-400 hover:text-emerald-500"
                    >
                      Abrir clipe
                    </a>
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
    </section>
  );
}

const filterInput =
  "mt-1 block rounded-lg border border-dark-700 bg-dark-900 px-2 py-1.5 text-sm text-[var(--color-text-primary)] outline-none focus:border-emerald-500/50";
