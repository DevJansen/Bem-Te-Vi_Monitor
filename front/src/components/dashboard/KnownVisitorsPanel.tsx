import { useEffect, useState } from "react";
import {
  Bird,
  CalendarClock,
  Fingerprint,
  History,
  MapPin,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";

import { usePolling } from "@/hooks/usePolling";
import {
  fetchKnownIndividual,
  fetchKnownIndividuals,
  getErrorMessage,
  resolveMediaUrl,
} from "@/services/api";
import { cn } from "@/utils/cn";
import type { IndividualSighting, KnownIndividual } from "@/types";

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatSimilarity(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

function SightingTile({ sighting }: { sighting: IndividualSighting }) {
  const image = resolveMediaUrl(sighting.crop_url);
  return (
    <div className="overflow-hidden rounded-xl border border-dark-700 bg-dark-900/60">
      <div className="aspect-square w-full bg-dark-900">
        {image ? (
          <img
            src={image}
            alt={`Avistamento em ${formatDate(sighting.detected_at)}`}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <Bird className="h-6 w-6 text-[var(--color-text-muted)]" />
          </div>
        )}
      </div>
      <div className="space-y-0.5 p-2">
        <p className="truncate text-[10px] text-[var(--color-text-muted)]">
          {formatDate(sighting.detected_at)}
        </p>
        <p className="flex items-center justify-between text-[10px] text-[var(--color-text-muted)]">
          <span>Similaridade</span>
          <span className="font-mono text-[var(--color-text-primary)]">
            {formatSimilarity(sighting.similarity)}
          </span>
        </p>
        {sighting.location_label ? (
          <p className="flex items-center gap-1 truncate text-[10px] text-[var(--color-text-muted)]">
            <MapPin className="h-2.5 w-2.5 shrink-0" />
            {sighting.location_label}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function IndividualCard({
  individual,
  onOpen,
}: {
  individual: KnownIndividual;
  onOpen: (individual: KnownIndividual) => void;
}) {
  const image =
    resolveMediaUrl(individual.crop_url) ??
    resolveMediaUrl(individual.recent_visits[0]?.crop_url ?? null);

  return (
    <button
      type="button"
      onClick={() => onOpen(individual)}
      className="group overflow-hidden rounded-xl border border-dark-700 bg-dark-900/60 text-left transition hover:border-violet-400/40 hover:bg-dark-900"
    >
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-dark-900">
        {image ? (
          <img
            src={image}
            alt={individual.nickname}
            loading="lazy"
            className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <Bird className="h-8 w-8 text-[var(--color-text-muted)]" />
          </div>
        )}
        {individual.is_recurring ? (
          <span className="absolute left-2 top-2 rounded-full border border-emerald-400/30 bg-emerald-400/15 px-2 py-0.5 text-[10px] font-medium text-emerald-200 backdrop-blur">
            Recorrente
          </span>
        ) : null}
        <span className="absolute right-2 top-2 rounded-full border border-dark-600 bg-dark-950/80 px-2 py-0.5 text-[10px] font-mono text-[var(--color-text-primary)] backdrop-blur">
          {individual.sightings}×
        </span>
      </div>
      <div className="p-2.5">
        <p className="truncate text-xs font-semibold text-[var(--color-text-primary)]">
          {individual.nickname}
        </p>
        <p className="truncate text-[11px] italic text-[var(--color-text-muted)]">
          {individual.scientific_name || individual.common_name}
        </p>
        <p className="mt-1 flex items-center gap-1 text-[10px] text-[var(--color-text-muted)]">
          <CalendarClock className="h-3 w-3" />
          Visto {formatDate(individual.last_seen_at)}
        </p>
      </div>
    </button>
  );
}

function IndividualModal({
  individual,
  onClose,
}: {
  individual: KnownIndividual;
  onClose: () => void;
}) {
  const [visits, setVisits] = useState<IndividualSighting[]>(
    individual.recent_visits,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchKnownIndividual(individual.id)
      .then((detail) => {
        if (active) setVisits(detail.visits);
      })
      .catch((err) => {
        if (active) setError(getErrorMessage(err, "Falha ao carregar o histórico"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [individual.id]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Histórico de ${individual.nickname}`}
      onClick={onClose}
    >
      <div
        className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-t-2xl border border-dark-700 bg-dark-800 p-5 sm:rounded-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-violet-300">
              Conhecido do Jardim
            </p>
            <h3 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
              {individual.nickname}
            </h3>
            <p className="text-xs italic text-[var(--color-text-muted)]">
              {individual.common_name}
              {individual.scientific_name ? ` · ${individual.scientific_name}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-dark-600 p-1.5 text-[var(--color-text-muted)] transition hover:text-[var(--color-text-primary)]"
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
          <span className="rounded-full border border-dark-600 bg-dark-900/60 px-2 py-0.5 text-[var(--color-text-muted)]">
            <Fingerprint className="mr-1 inline h-3 w-3" />
            {individual.sightings} avistamentos
          </span>
          <span className="rounded-full border border-dark-600 bg-dark-900/60 px-2 py-0.5 text-[var(--color-text-muted)]">
            <Sparkles className="mr-1 inline h-3 w-3" />
            Similaridade média {formatSimilarity(individual.avg_similarity)}
          </span>
          <span className="rounded-full border border-dark-600 bg-dark-900/60 px-2 py-0.5 text-[var(--color-text-muted)]">
            Primeira vez {formatDate(individual.first_seen_at)}
          </span>
          <span className="rounded-full border border-dark-600 bg-dark-900/60 px-2 py-0.5 text-[var(--color-text-muted)]">
            Última vez {formatDate(individual.last_seen_at)}
          </span>
        </div>

        {error ? (
          <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </p>
        ) : null}

        <div className="mt-4">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            <History className="h-3.5 w-3.5" />
            Histórico individual
          </p>
          {loading && visits.length === 0 ? (
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  key={index}
                  className="aspect-square animate-pulse rounded-xl bg-dark-700"
                />
              ))}
            </div>
          ) : visits.length === 0 ? (
            <p className="mt-2 rounded-lg border border-dashed border-dark-600 px-3 py-4 text-center text-xs text-[var(--color-text-muted)]">
              Nenhum avistamento registrado para este indivíduo.
            </p>
          ) : (
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {visits.map((sighting) => (
                <SightingTile key={sighting.visit_id} sighting={sighting} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Painel "Conhecidos do Jardim".
 *
 * Mostra os indivíduos re-identificados por assinatura visual (embeddings).
 * Ao abrir um card, o histórico completo daquele indivíduo é carregado e
 * exibido com as respectivas fotos, similaridades e jardins.
 */
export function KnownVisitorsPanel() {
  const query = usePolling(() => fetchKnownIndividuals({ limit: 24 }), 120_000);
  const [selected, setSelected] = useState<KnownIndividual | null>(null);

  const individuals = query.data?.individuals ?? [];

  return (
    <article className="rounded-2xl border border-dark-700 bg-dark-800 p-5">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-violet-400/25 bg-violet-400/10">
            <Fingerprint className="h-5 w-5 text-violet-300" />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
              Re-identificação visual
            </p>
            <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
              Conhecidos do Jardim
            </h2>
            <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">
              Cada ave recorrente ganha uma assinatura visual própria — e um
              histórico individual.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {query.data ? (
            <span className="rounded-full border border-dark-600 bg-dark-900/60 px-2 py-1 text-[10px] text-[var(--color-text-muted)]">
              {query.data.total} indivíduo{query.data.total === 1 ? "" : "s"}
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => void query.refresh()}
            disabled={query.loading}
            className="rounded-lg border border-dark-600 bg-dark-900/60 p-1.5 text-[var(--color-text-muted)] transition hover:text-[var(--color-text-primary)] disabled:opacity-50"
            title="Atualizar a galeria de indivíduos"
            aria-label="Atualizar"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", query.loading && "animate-spin")} />
          </button>
        </div>
      </header>

      {query.error ? (
        <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {query.error}
        </p>
      ) : null}

      {query.loading && individuals.length === 0 ? (
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={index}
              className="aspect-[4/3] animate-pulse rounded-xl bg-dark-700"
            />
          ))}
        </div>
      ) : individuals.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-dark-600 px-4 py-6 text-center">
          <Fingerprint className="mx-auto h-6 w-6 text-[var(--color-text-muted)]" />
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">
            Nenhum indivíduo reconhecido ainda. Assim que uma ave nítida
            reaparecer com a mesma assinatura, ela vira um "Conhecido do Jardim".
          </p>
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
          {individuals.map((individual) => (
            <IndividualCard
              key={individual.id}
              individual={individual}
              onOpen={setSelected}
            />
          ))}
        </div>
      )}

      {selected ? (
        <IndividualModal individual={selected} onClose={() => setSelected(null)} />
      ) : null}
    </article>
  );
}
