import { Bird, Clock3, RefreshCw } from "lucide-react";
import { fetchTodayVisits, getErrorMessage, resolveMediaUrl } from "@/services/api";
import type { BirdVisit } from "@/types";
import { usePolling } from "@/hooks/usePolling";
import { formatPercent, formatSpeciesLabel, formatTime } from "@/utils/format";
import { WeatherBadges } from "@/components/common/WeatherBadges";

async function loadTodayVisits(): Promise<BirdVisit[]> {
  try {
    return await fetchTodayVisits(24);
  } catch (error) {
    throw new Error(
      getErrorMessage(error, "Não foi possível carregar as visitas de hoje."),
    );
  }
}

/**
 * Painel de Visitas de Hoje: lista os registros recentes do dia com a miniatura
 * (capturada pelo YOLOv8) ao lado do horário e do nome da espécie.
 */
export function TodayVisitsPanel() {
  const query = usePolling(loadTodayVisits, 8_000);
  const visits = query.data ?? [];

  return (
    <section className="rounded-xl border border-dark-700 bg-dark-800">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-dark-700 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400">
            <Clock3 className="h-4 w-4" />
          </span>
          <div>
            <h2 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
              Visitas de Hoje
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Registros recentes do alimentador com miniatura
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {visits.length > 0 ? (
            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-semibold text-emerald-300">
              {visits.length} hoje
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => void query.refresh()}
            disabled={query.loading}
            aria-label="Atualizar visitas de hoje"
            className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:text-emerald-300 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${query.loading ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      <div className="p-4">
        {query.error ? (
          <p role="alert" className="text-sm text-red-300">
            {query.error}
          </p>
        ) : query.loading && visits.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            Carregando visitas de hoje…
          </p>
        ) : visits.length === 0 ? (
          <div className="rounded-lg border border-dashed border-dark-700 px-6 py-10 text-center">
            <Bird className="mx-auto h-7 w-7 text-emerald-400/70" />
            <p className="mt-3 text-sm text-[var(--color-text-muted)]">
              Nenhuma visita registrada hoje ainda. As capturas de hoje
              aparecerão aqui automaticamente.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-dark-700">
            {visits.map((visit, index) => {
              const thumb = resolveMediaUrl(
                visit.thumbnail_url ?? visit.thumbnail_path,
              );
              return (
                <li
                  key={visit.id}
                  style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}
                  className="flex animate-fade-in-up items-center gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded-full ring-2 ring-emerald-500/25">
                    {thumb ? (
                      <img
                        src={thumb}
                        alt={`Miniatura de ${formatSpeciesLabel(visit.species)}`}
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <span className="flex h-full w-full items-center justify-center bg-dark-900 text-[var(--color-text-muted)]">
                        <Bird className="h-5 w-5" />
                      </span>
                    )}
                  </div>

                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
                      {formatSpeciesLabel(visit.species)}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {formatPercent(visit.confidence)} de confiança
                      {visit.camera_name ? ` · ${visit.camera_name}` : ""}
                    </p>
                    <WeatherBadges
                      temperature={visit.temperature}
                      humidity={visit.humidity}
                      weather_code={visit.weather_code}
                      className="mt-1"
                    />
                  </div>

                  <span className="shrink-0 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold tabular-nums text-emerald-300">
                    {formatTime(visit.detected_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
