import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Bird,
  Bot,
  CalendarClock,
  Dna,
  Globe2,
  Lightbulb,
  LoaderCircle,
  MapPin,
  RefreshCw,
  Ruler,
  ShieldCheck,
  Sparkles,
  Utensils,
  Weight,
  X,
} from "lucide-react";
import type { BirdVisit, SpeciesAiConsult } from "@/types";
import {
  askSpeciesAi,
  askVisitAi,
  getErrorMessage,
  resolveMediaUrl,
  visitCropUrl,
} from "@/services/api";
import { cn } from "@/utils/cn";
import { resolveVisitNames, resolveVisitSpeciesLabel } from "@/utils/visits";

/** Referência de espécie usada na consulta a partir de "Minhas Aves". */
export type SpeciesConsultSubject = {
  id: string;
  common_name: string;
  scientific_name: string;
  /** Imagem tratada da espécie (foto de referência), quando existir. */
  image_url?: string | null;
};

type Props = {
  /** Visita consultada (consulta no nível da visita). */
  visit?: BirdVisit | null;
  /** Espécie consultada (consulta no nível da espécie, ex.: Minhas Aves). */
  species?: SpeciesConsultSubject | null;
  onClose: () => void;
};

/**
 * Modal da **consulta ornitológica profunda** ("Perguntar à IA Externa").
 *
 * Funciona em dois níveis: por **visita** (Galeria / detalhe da visita) e por
 * **espécie** (Minhas Aves / Álbum de Conquistas). Em ambos, o backend estrutura
 * um *prompt* ornitológico rico e devolve a ficha formatada: nome científico,
 * família, status de conservação, comportamento alimentar, habitat, curiosidades
 * e dados biogeográficos. O resultado é cacheado (o botão "Atualizar" refaz).
 */
export function SpeciesAiConsultModal({ visit, species, onClose }: Props) {
  const [consult, setConsult] = useState<SpeciesAiConsult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const visitId = visit?.id ?? null;
  const speciesId = species?.id ?? null;

  const load = useCallback(
    async (refresh: boolean): Promise<SpeciesAiConsult> => {
      if (visitId) return askVisitAi(visitId, refresh);
      if (speciesId) return askSpeciesAi(speciesId, refresh);
      throw new Error("Nada para consultar");
    },
    [visitId, speciesId],
  );

  // Carrega (do cache ou da IA) sempre que o alvo da consulta muda.
  useEffect(() => {
    if (!visitId && !speciesId) return;
    setConsult(null);
    setError(null);
    let active = true;
    setLoading(true);
    void (async () => {
      try {
        const data = await load(false);
        if (active) setConsult(data);
      } catch (cause) {
        if (active) {
          setError(
            getErrorMessage(cause, "Não foi possível consultar a IA externa."),
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [visitId, speciesId, load]);

  // Fecha com a tecla Esc.
  useEffect(() => {
    if (!visitId && !speciesId) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [visitId, speciesId, onClose]);

  if (!visitId && !speciesId) return null;

  // Nomes e imagem dependem do nível (visita × espécie).
  const names = visit ? resolveVisitNames(visit) : null;
  const title = visit
    ? names?.commonName || resolveVisitSpeciesLabel(visit)
    : species?.common_name ?? "";
  const scientificName = visit
    ? names?.scientificName ?? null
    : species?.scientific_name ?? null;
  const label = title || "Espécie";
  const image = visit
    ? visit.metadata?.crop_path
      ? visitCropUrl(visit.id)
      : resolveMediaUrl(visit.thumbnail_url ?? visit.thumbnail_path)
    : species?.image_url ?? null;

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-3 sm:p-6">
      <button
        type="button"
        aria-label="Fechar ficha ornitológica"
        onClick={onClose}
        className="absolute inset-0 bg-black/80 backdrop-blur-md"
      />

      <section
        role="dialog"
        aria-modal="true"
        aria-label={`Ficha ornitológica de ${label}`}
        className="relative z-10 flex max-h-[92vh] w-full max-w-3xl animate-pop-in flex-col overflow-hidden rounded-2xl border border-violet-500/25 bg-dark-800/95 shadow-[0_0_70px_-15px_rgba(139,92,246,0.55)]"
      >
        {/* Cabeçalho */}
        <header className="flex items-start gap-3 border-b border-dark-700 px-4 py-3 sm:px-5">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-500/15 text-violet-300">
            <Bot className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-violet-300/90">
              <Sparkles className="h-3 w-3" />
              Alaris Core · Consulta Ornitológica
            </p>
            <h2 className="truncate font-display text-base font-semibold text-[var(--color-text-primary)] sm:text-lg">
              {label}
            </h2>
            <p className="text-xs italic text-[var(--color-text-muted)]">
              {scientificName ?? "Nome científico não identificado"}
            </p>
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
          {/* Foto tratada + ações */}
          <div className="flex items-center gap-3">
            {image ? (
              <img
                src={image}
                alt={`Registro de ${label}`}
                className="h-20 w-20 shrink-0 rounded-xl border border-dark-700 object-cover"
              />
            ) : (
              <span className="flex h-20 w-20 shrink-0 items-center justify-center rounded-xl border border-dark-700 bg-dark-900 text-[var(--color-text-muted)]">
                <Bird className="h-7 w-7" />
              </span>
            )}
            <div className="min-w-0 flex-1">
              <p className="text-xs text-[var(--color-text-muted)]">
                Ficha técnica gerada pela IA externa a partir da imagem tratada
                pelo Alaris Core.
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {consult?.provider ? (
                  <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] font-semibold text-violet-200">
                    Google Gemini
                    {consult.model ? ` · ${consult.model}` : ""}
                  </span>
                ) : null}
                {consult?.cached ? (
                  <span className="rounded-full border border-dark-600 bg-dark-900 px-2 py-0.5 text-[10px] text-[var(--color-text-muted)]">
                    Em cache
                  </span>
                ) : null}
                {consult?.image_source ? (
                  <span className="rounded-full border border-dark-600 bg-dark-900 px-2 py-0.5 text-[10px] text-[var(--color-text-muted)]">
                    Fonte: {consult.image_source}
                  </span>
                ) : null}
                <button
                  type="button"
                  disabled={loading}
                  onClick={() =>
                    void (async () => {
                      setLoading(true);
                      setError(null);
                      try {
                        setConsult(await load(true));
                      } catch (cause) {
                        setError(
                          getErrorMessage(
                            cause,
                            "Não foi possível consultar a IA externa.",
                          ),
                        );
                      } finally {
                        setLoading(false);
                      }
                    })()
                  }
                  className="inline-flex items-center gap-1.5 rounded-lg border border-dark-600 px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)] disabled:opacity-50"
                >
                  <RefreshCw
                    className={cn("h-3.5 w-3.5", loading && "animate-spin")}
                  />
                  Atualizar
                </button>
              </div>
            </div>
          </div>

          {loading && !consult ? (
            <div className="flex flex-col items-center justify-center gap-3 py-12 text-sm text-[var(--color-text-muted)]">
              <LoaderCircle className="h-7 w-7 animate-spin text-violet-300" />
              Consultando a IA externa sobre a espécie…
            </div>
          ) : null}

          {error ? (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-200"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </p>
          ) : null}

          {consult ? (
            <>
              <div className="grid gap-2 sm:grid-cols-2">
                <ConsultField
                  icon={<Dna className="h-3.5 w-3.5" />}
                  label="Família / Ordem"
                  value={[consult.family, consult.order]
                    .filter(Boolean)
                    .join(" · ")}
                />
                <ConsultField
                  icon={<ShieldCheck className="h-3.5 w-3.5" />}
                  label="Status de conservação"
                  value={consult.conservation_status}
                />
                <ConsultField
                  icon={<Utensils className="h-3.5 w-3.5" />}
                  label="Dieta"
                  value={consult.diet}
                />
                <ConsultField
                  icon={<Utensils className="h-3.5 w-3.5" />}
                  label="Comportamento alimentar"
                  value={consult.feeding_behavior}
                />
                <ConsultField
                  icon={<MapPin className="h-3.5 w-3.5" />}
                  label="Habitat"
                  value={consult.habitat}
                />
                <ConsultField
                  icon={<CalendarClock className="h-3.5 w-3.5" />}
                  label="Migração / sazonalidade"
                  value={consult.migration}
                />
                <ConsultField
                  icon={<Globe2 className="h-3.5 w-3.5" />}
                  label="Distribuição geográfica"
                  value={consult.distribution}
                />
                <ConsultField
                  icon={<Globe2 className="h-3.5 w-3.5" />}
                  label="Dados biogeográficos"
                  value={consult.biogeography}
                />
                <ConsultField
                  icon={<Ruler className="h-3.5 w-3.5" />}
                  label="Tamanho"
                  value={consult.size_cm}
                />
                <ConsultField
                  icon={<Weight className="h-3.5 w-3.5" />}
                  label="Peso"
                  value={consult.weight_g}
                />
                <ConsultField
                  icon={<CalendarClock className="h-3.5 w-3.5" />}
                  label="Longevidade"
                  value={consult.lifespan}
                />
              </div>

              {consult.curiosities.length > 0 ? (
                <div className="rounded-xl border border-violet-500/15 bg-violet-500/5 p-3">
                  <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-violet-200/90">
                    <Lightbulb className="h-3 w-3" />
                    Curiosidades
                  </p>
                  <ul className="space-y-1.5">
                    {consult.curiosities.map((item, index) => (
                      <li
                        key={`${index}-${item.slice(0, 12)}`}
                        className="flex gap-2 text-xs leading-snug text-[var(--color-text-primary)]"
                      >
                        <span className="text-violet-300">•</span>
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {consult.notes ? (
                <p className="rounded-xl border border-emerald-500/15 bg-emerald-500/5 p-3 text-[11px] italic leading-snug text-emerald-200/85">
                  🧠 {consult.notes}
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}

/** Bloco compacto de um campo da ficha ornitológica. */
function ConsultField({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  if (!value) return null;
  return (
    <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
        {icon}
        {label}
      </p>
      <p className="mt-1 text-sm leading-snug text-[var(--color-text-primary)]">
        {value}
      </p>
    </div>
  );
}
