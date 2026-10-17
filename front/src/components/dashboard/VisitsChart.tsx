import { useEffect, useState } from "react";
import type { Metrics, TodayByGarden } from "@/types";
import { fetchTodayByGarden } from "@/services/api";
import { usePolling } from "@/hooks/usePolling";

type Props = {
  metrics: Metrics | null;
  /** Quando informado, exibe o fluxo de horário apenas desse jardim. */
  gardenId?: string | null;
};

export function VisitsChart({ metrics, gardenId }: Props) {
  const [gardenData, setGardenData] = useState<TodayByGarden | null>(null);

  const { data } = usePolling(fetchTodayByGarden, 15_000);
  useEffect(() => {
    if (data) setGardenData(data);
  }, [data]);

  const consolidatedMap = metrics?.visits_by_hour ?? {};
  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"));

  let map: Record<string, number> = consolidatedMap;
  let titleSuffix = "";
  if (gardenId && gardenData) {
    const garden = gardenData.gardens.find((g) => g.camera_id === gardenId);
    if (garden) {
      map = garden.visits_by_hour;
      titleSuffix = ` · ${garden.garden}`;
    }
  } else if (!gardenId && gardenData) {
    map = gardenData.consolidated_visits_by_hour;
  }

  const values = hours.map((h) => map[h] ?? map[String(Number(h))] ?? 0);
  const max = Math.max(...values, 1);

  return (
    <section className="rounded-xl border border-dark-700 bg-dark-800 p-4">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
            Visitas por horário{titleSuffix}
          </h2>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
            Distribuição de hoje (segmentada por jardim)
          </p>
        </div>
        <p className="text-xs text-[var(--color-text-muted)]">
          Pico:{" "}
          <span className="font-medium text-emerald-400">
            {Math.max(...values, 0)} visitas
          </span>
        </p>
      </div>

      <div className="flex h-44 items-end gap-1">
        {hours.map((hour, idx) => {
          const value = values[idx];
          const height = value === 0 ? 2 : Math.max(8, Math.round((value / max) * 100));
          return (
            <div key={hour} className="group flex flex-1 flex-col items-center gap-1">
              <div className="relative flex h-36 w-full items-end justify-center">
                <div
                  className="w-full max-w-[14px] rounded-t-sm bg-emerald-500/80 transition group-hover:bg-emerald-400"
                  style={{ height: `${height}%` }}
                  title={`${hour}h — ${value} visita(s)`}
                />
              </div>
              {idx % 3 === 0 ? (
                <span className="text-[9px] text-[var(--color-text-muted)]">{hour}</span>
              ) : (
                <span className="text-[9px] opacity-0">·</span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}