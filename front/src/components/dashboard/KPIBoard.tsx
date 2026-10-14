import { Bird, Camera, Clock3, Footprints } from "lucide-react";
import type { Metrics } from "@/types";
import { peakHourFromMap } from "@/utils/format";

type Props = {
  metrics: Metrics | null;
  loading?: boolean;
};

export function KPIBoard({ metrics, loading }: Props) {
  const speciesToday = metrics
    ? Object.keys(metrics.species_counts).length
    : 0;

  const items = [
    {
      label: "Visitas hoje",
      value: metrics?.visits_today ?? "—",
      hint: metrics ? `${metrics.total_visits} no total` : "Carregando…",
      icon: Footprints,
    },
    {
      label: "Espécies registradas",
      value: loading && !metrics ? "—" : speciesToday,
      hint: "Ranking local do dia",
      icon: Bird,
    },
    {
      label: "Horário de pico",
      value: metrics ? peakHourFromMap(metrics.visits_by_hour) : "—",
      hint: "Maior fluxo nas últimas horas",
      icon: Clock3,
    },
    {
      label: "Câmeras online",
      value: metrics
        ? `${metrics.active_cameras}/${metrics.total_cameras}`
        : "—",
      hint: "Streams ativos no pipeline",
      icon: Camera,
    },
  ];

  return (
    <section aria-label="Indicadores do dia" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map(({ label, value, hint, icon: Icon }) => (
        <article
          key={label}
          className="rounded-xl border border-dark-700 bg-dark-800 px-4 py-4"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                {label}
              </p>
              <p className="mt-2 font-display text-3xl font-semibold text-[var(--color-text-primary)]">
                {value}
              </p>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">{hint}</p>
            </div>
            <div className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400">
              <Icon className="h-5 w-5" strokeWidth={1.75} />
            </div>
          </div>
        </article>
      ))}
    </section>
  );
}
