import { useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Bird,
  BookOpen,
  CalendarDays,
  Clock3,
  Eye,
  FileText,
  MapPin,
  RefreshCw,
  Sparkles,
  Timer,
  Trophy,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  fetchAchievements,
  fetchAnalyticsSummary,
  fetchCollectorLevel,
  fetchHourlyDistribution,
  fetchLifeList,
  fetchMetrics,
  fetchWeatherCorrelation,
  fetchWeatherInsights,
  getErrorMessage,
  laudoPdfUrl,
  listCameras,
} from "@/services/api";
import type {
  Achievement,
  AnalyticsSummary,
  Camera,
  CollectorLevel,
  HourlyDistribution,
  LifeListSpecies,
  Metrics,
  WeatherCorrelation,
  WeatherInsights,
} from "@/types";
import { usePolling } from "@/hooks/usePolling";
import { formatSpeciesLabel } from "@/utils/format";
import { cn } from "@/utils/cn";
import { WeatherCorrelationPanel } from "@/components/dashboard/WeatherCorrelationPanel";
import { WeatherInsightsPanel } from "@/components/dashboard/WeatherInsightsPanel";
import { LifeListAlbum } from "@/components/dashboard/LifeListAlbum";
import { AchievementsGrid } from "@/components/dashboard/AchievementsGrid";

type AnalyticsData = {
  summary: AnalyticsSummary;
  hourly: HourlyDistribution[];
  lifeList: LifeListSpecies[];
  weather: WeatherCorrelation;
  weatherInsights: WeatherInsights;
  achievements: Achievement[];
  collectorLevel: CollectorLevel | null;
};

async function loadAnalytics(cameraId?: string): Promise<AnalyticsData> {
  try {
    const [summary, hourly, lifeList, weather, weatherInsights, achievements, collectorLevel] =
      await Promise.all([
        fetchAnalyticsSummary(cameraId),
        fetchHourlyDistribution(cameraId),
        fetchLifeList(),
        fetchWeatherCorrelation(),
        fetchWeatherInsights(),
        fetchAchievements(),
        fetchCollectorLevel().catch(() => null),
      ]);
    return {
      summary,
      hourly,
      lifeList,
      weather,
      weatherInsights,
      achievements,
      collectorLevel,
    };
  } catch (error) {
    throw new Error(
      getErrorMessage(error, "Não foi possível carregar as estatísticas."),
    );
  }
}

const numberFormat = new Intl.NumberFormat("pt-BR");

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0 s";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const remainingSeconds = rounded % 60;
  if (!minutes) return `${remainingSeconds} s`;
  return remainingSeconds
    ? `${minutes} min ${remainingSeconds} s`
    : `${minutes} min`;
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: LucideIcon;
}) {
  return (
    <article className="rounded-xl border border-dark-700 bg-dark-800 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-[var(--color-text-muted)]">
            {label}
          </p>
          <p className="mt-2 truncate font-display text-xl font-semibold text-[var(--color-text-primary)]">
            {value}
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">{detail}</p>
        </div>
        <span className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400">
          <Icon className="h-4 w-4" />
        </span>
      </div>
    </article>
  );
}

export function AnalyticsDashboard() {
  // Jardim selecionado ("" = Visão Total Consolidada de todos os jardins).
  const [garden, setGarden] = useState("");
  const gardenRef = useRef("");
  // Ref síncrona: o refresh disparado no onChange já usa a seleção nova.
  gardenRef.current = garden;

  const camerasQuery = usePolling(listCameras, 60_000);
  const query = usePolling(
    () => loadAnalytics(gardenRef.current || undefined),
    30_000,
  );
  // Métricas do jardim (visitas/espécies presentes) — consolidadas ou filtradas.
  const metricsQuery = usePolling(
    () => fetchMetrics(gardenRef.current || undefined),
    30_000,
  );
  const refresh = () => {
    void query.refresh();
    void metricsQuery.refresh();
  };
  const data = query.data;
  const cameras: Camera[] = camerasQuery.data ?? [];
  const scopedMetrics: Metrics | null = metricsQuery.data;
  const unlockedCount = data?.lifeList.filter((item) => item.is_unlocked).length ?? 0;
  const peakHour = data?.summary.peak_hour;
  // Número de espécies distintas registradas no escopo atual (jardim ou total).
  const speciesPresent = Object.keys(scopedMetrics?.species_counts ?? {}).length;
  const gardenLabel =
    cameras.find((camera) => camera.id === garden)?.location_label ||
    cameras.find((camera) => camera.id === garden)?.name ||
    "Visão Total Consolidada";
  // Aba interna: Álbum de figurinhas x Medalhas do observador.
  const [view, setView] = useState<"album" | "badges">("album");

  const handleGardenChange = (value: string) => {
    gardenRef.current = value;
    setGarden(value);
    void query.refresh();
    void metricsQuery.refresh();
  };

  return (
    <div className="space-y-6">
      {/* Seletor: cada jardim × Visão Total Consolidada */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dark-700 bg-dark-800 px-4 py-3">
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <MapPin className="h-4 w-4 text-emerald-400" />
          <label htmlFor="analytics-garden" className="font-medium">
            Escopo das estatísticas:
          </label>
          <select
            id="analytics-garden"
            value={garden}
            onChange={(event) => handleGardenChange(event.target.value)}
            className="rounded-md border border-dark-700 bg-dark-900/70 px-2.5 py-1.5 text-xs text-[var(--color-text-primary)]"
          >
            <option value="">Visão Total Consolidada</option>
            {cameras.map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.location_label || camera.name || "Jardim sem nome"}
              </option>
            ))}
          </select>
        </div>
        <p className="text-xs text-[var(--color-text-muted)]">
          Exibindo:{" "}
          <span className="font-semibold text-emerald-300">{gardenLabel}</span>
        </p>
      </div>

      {query.error ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300"
        >
          <span>{query.error}</span>
          <button
            type="button"
            onClick={refresh}
            className="inline-flex items-center gap-2 rounded-md px-2 py-1 font-medium hover:bg-red-500/10"
          >
            <RefreshCw className="h-4 w-4" />
            Tentar novamente
          </button>
        </div>
      ) : null}

      {query.loading && !data ? (
        <p className="rounded-xl border border-dark-700 bg-dark-800 p-6 text-sm text-[var(--color-text-muted)]">
          Carregando suas estatísticas e conquistas…
        </p>
      ) : null}

      {data ? (
        <>
          <section aria-label="Indicadores de visitas">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
                  Seus hábitos de observação
                </h2>
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  Resumo de {gardenLabel}
                </p>
              </div>
              <a
                href={laudoPdfUrl()}
                download="laudo-ornitologico-aviawatch.pdf"
                className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-300 transition hover:bg-emerald-500/20"
              >
                <FileText className="h-4 w-4" />
                Gerar Laudo (PDF)
              </a>
              <button
                type="button"
                onClick={refresh}
                disabled={query.loading}
                aria-label="Atualizar estatísticas"
                className="rounded-lg border border-dark-700 p-2 text-[var(--color-text-muted)] transition hover:text-emerald-400 disabled:opacity-50"
              >
                <RefreshCw
                  className={`h-4 w-4 ${query.loading ? "animate-spin" : ""}`}
                />
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <MetricCard
                label="Visitas hoje"
                value={numberFormat.format(data.summary.visits_today)}
                detail={`${numberFormat.format(data.summary.visits_last_7_days)} nos últimos 7 dias`}
                icon={CalendarDays}
              />
              <MetricCard
                label="Espécie líder"
                value={
                  data.summary.most_frequent_species
                    ? formatSpeciesLabel(data.summary.most_frequent_species)
                    : "Sem registros"
                }
                detail={`${numberFormat.format(data.summary.most_frequent_species_count)} visita(s)`}
                icon={Bird}
              />
              <MetricCard
                label="Duração média"
                value={formatDuration(data.summary.average_duration_seconds)}
                detail="Tempo médio de permanência"
                icon={Timer}
              />
              <MetricCard
                label="Horário de pico"
                value={peakHour ?? "Sem registros"}
                detail="Faixa com mais visitas"
                icon={Clock3}
              />
              <MetricCard
                label="Visitas no total"
                value={numberFormat.format(data.summary.total_visits)}
                detail="Desde o início do monitoramento"
                icon={Eye}
              />
              <MetricCard
                label="Espécies conquistadas"
                value={`${unlockedCount} de ${data.lifeList.length}`}
                detail="Espécies do catálogo já observadas"
                icon={Sparkles}
              />
              <MetricCard
                label="Espécies presentes"
                value={numberFormat.format(speciesPresent)}
                detail={`Registradas em ${gardenLabel}`}
                icon={Bird}
              />
            </div>
          </section>

          <section className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
            <div className="mb-4">
              <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
                Frequência por horário
              </h2>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Visitas de {gardenLabel}, distribuídas pelas 24 horas do dia
              </p>
            </div>
            <div className="h-64 w-full" role="img" aria-label="Gráfico de visitas por hora">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={data.hourly}
                  margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
                >
                  <CartesianGrid
                    stroke="rgba(138, 163, 153, 0.12)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="hour"
                    tickFormatter={(hour: string) => `${hour}h`}
                    interval={2}
                    tick={{ fill: "#8aa399", fontSize: 11 }}
                    axisLine={{ stroke: "#1a2420" }}
                    tickLine={false}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fill: "#8aa399", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(16, 185, 129, 0.08)" }}
                    contentStyle={{
                      background: "#111816",
                      border: "1px solid #1a2420",
                      borderRadius: 8,
                      color: "#e8f5ef",
                    }}
                    labelStyle={{ color: "#8aa399" }}
                    labelFormatter={(hour) => `${hour}h`}
                    formatter={(value) => [
                      `${numberFormat.format(Number(value))} visita(s)`,
                      "Registros",
                    ]}
                  />
                  <Bar dataKey="visits" name="Visitas" radius={[4, 4, 0, 0]}>
                    {data.hourly.map((item) => (
                      <Cell
                        key={item.hour}
                        fill={item.hour === peakHour?.slice(0, 2) ? "#34d399" : "#10b981"}
                        fillOpacity={item.visits > 0 ? 0.9 : 0.25}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <WeatherInsightsPanel data={data.weatherInsights} />

          <WeatherCorrelationPanel data={data.weather} />

          <section aria-label="Álbum e conquistas">
            {/* Alternância entre o álbum de figurinhas e as medalhas */}
            <div className="mb-4 inline-flex flex-wrap gap-1 rounded-xl border border-dark-700 bg-dark-800 p-1.5">
              <button
                type="button"
                onClick={() => setView("album")}
                aria-pressed={view === "album"}
                className={cn(
                  "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition",
                  view === "album"
                    ? "bg-emerald-500/15 text-emerald-300"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
                )}
              >
                <BookOpen className="h-4 w-4" />
                Álbum de Conquistas
              </button>
              <button
                type="button"
                onClick={() => setView("badges")}
                aria-pressed={view === "badges"}
                className={cn(
                  "inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition",
                  view === "badges"
                    ? "bg-amber-400/15 text-amber-200"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
                )}
              >
                <Trophy className="h-4 w-4" />
                Medalhas
                {data.achievements.length > 0 ? (
                  <span className="rounded-full bg-dark-900 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums">
                    {data.achievements.filter((item) => item.unlocked).length}/
                    {data.achievements.length}
                  </span>
                ) : null}
              </button>
            </div>

            {view === "album" ? (
              <LifeListAlbum species={data.lifeList} />
            ) : (
              <AchievementsGrid achievements={data.achievements} collectorLevel={data.collectorLevel} />
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
