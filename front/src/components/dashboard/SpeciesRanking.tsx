import type { Metrics } from "@/types";
import { formatSpeciesLabel } from "@/utils/format";

type Props = {
  metrics: Metrics | null;
  limit?: number;
};

export function SpeciesRanking({ metrics, limit = 8 }: Props) {
  const entries = Object.entries(metrics?.species_counts ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
  const max = entries[0]?.[1] ?? 1;

  return (
    <section className="rounded-xl border border-dark-700 bg-dark-800 p-4">
      <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
        Ranking de espécies
      </h2>
      <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
        Aves mais frequentes no histórico local
      </p>

      <ul className="mt-4 space-y-3">
        {entries.length === 0 ? (
          <li className="rounded-lg border border-dashed border-dark-700 px-3 py-6 text-center text-sm text-[var(--color-text-muted)]">
            Nenhuma visita registrada ainda.
          </li>
        ) : (
          entries.map(([species, count], index) => {
            const pct = Math.round((count / max) * 100);
            return (
              <li key={species}>
                <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                  <span className="text-[var(--color-text-primary)]">
                    <span className="mr-2 text-[var(--color-text-muted)]">
                      #{index + 1}
                    </span>
                    {formatSpeciesLabel(species)}
                  </span>
                  <span className="tabular-nums text-emerald-400">{count}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-dark-700">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
