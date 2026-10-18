import { useMemo } from "react";
import type { BirdSpecies, Metrics } from "@/types";
import { formatSpeciesLabel, isGenericSpecies } from "@/utils/format";
import { resolveMediaUrl } from "@/services/api";
import { BIRD_SILHOUETTE_DATA_URI } from "@/utils/speciesImage";

type Props = {
  metrics: Metrics | null;
  /** Catálogo local (Minhas Aves) para resolver a foto de cada espécie. */
  species?: BirdSpecies[];
  limit?: number;
  title?: string;
  subtitle?: string;
};

/**
 * Ranking das espécies mais frequentes, com foto em cada posição.
 *
 * A contagem vem das métricas (já filtradas pelo jardim selecionado). A foto é
 * resolvida pelo catálogo local cruzando o rótulo da espécie com o nome popular
 * (tolerante a acentos e a sufixos com o nome científico). Quando não há foto —
 * ou a espécie é uma detecção genérica — usamos a **silhueta padrão** rotulada
 * "Pássaro Desconhecido".
 */
export function SpeciesRanking({
  metrics,
  species = [],
  limit = 5,
  title = "Ranking de espécies",
  subtitle = "Aves mais frequentes no histórico",
}: Props) {
  const entries = Object.entries(metrics?.species_counts ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
  const max = entries[0]?.[1] ?? 1;

  // Índice nome popular (normalizado) → foto de referência.
  const photoByName = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of species) {
      const url = resolveMediaUrl(item.reference_image_url);
      if (!url) continue;
      map.set(item.common_name.trim().toLowerCase(), url);
    }
    return map;
  }, [species]);

  const photoFor = (label: string): string | null => {
    const normalized = label.trim().toLowerCase();
    const direct = photoByName.get(normalized);
    if (direct) return direct;
    // Tolera rótulos como "Nome (Nome científico)".
    for (const [name, url] of photoByName) {
      if (normalized.startsWith(name)) return url;
    }
    return null;
  };

  return (
    <section className="rounded-xl border border-dark-700 bg-dark-800 p-4">
      <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
        {title}
      </h2>
      <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{subtitle}</p>

      <ul className="mt-4 space-y-3">
        {entries.length === 0 ? (
          <li className="rounded-lg border border-dashed border-dark-700 px-3 py-6 text-center text-sm text-[var(--color-text-muted)]">
            Nenhuma visita registrada ainda.
          </li>
        ) : (
          entries.map(([label, count], index) => {
            const pct = Math.round((count / max) * 100);
            const generic = isGenericSpecies(label);
            const photo = photoFor(label) ?? BIRD_SILHOUETTE_DATA_URI;
            return (
              <li key={label} className="flex items-center gap-3">
                <img
                  src={photo}
                  alt={`Foto de ${formatSpeciesLabel(label)}`}
                  onError={(event) => {
                    event.currentTarget.src = BIRD_SILHOUETTE_DATA_URI;
                  }}
                  loading="lazy"
                  className="h-10 w-10 shrink-0 rounded-lg border border-dark-700 object-cover"
                />
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-[var(--color-text-primary)]">
                      <span className="mr-2 text-[var(--color-text-muted)]">
                        #{index + 1}
                      </span>
                      {formatSpeciesLabel(label)}
                      {generic ? (
                        <span className="ml-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-medium text-amber-200">
                          Não identificado
                        </span>
                      ) : null}
                    </span>
                    <span className="shrink-0 tabular-nums text-emerald-400">
                      {count}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-dark-700">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
