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
  CalendarDays,
  Clock3,
  Eye,
  LockKeyhole,
  RefreshCw,
  Sparkles,
  Timer,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  fetchAnalyticsSummary,
  fetchHourlyDistribution,
  fetchLifeList,
  getErrorMessage,
} from "@/services/api";
import type {
  AnalyticsSummary,
  HourlyDistribution,
  LifeListSpecies,
} from "@/types";
import { usePolling } from "@/hooks/usePolling";
import { formatDateTime, formatSpeciesLabel } from "@/utils/format";

type AnalyticsData = {
  summary: AnalyticsSummary;
  hourly: HourlyDistribution[];
  lifeList: LifeListSpecies[];
};

async function loadAnalytics(): Promise<AnalyticsData> {
  try {
    const [summary, hourly, lifeList] = await Promise.all([
      fetchAnalyticsSummary(),
      fetchHourlyDistribution(),
      fetchLifeList(),
    ]);
    return { summary, hourly, lifeList };
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
  const query = usePolling(loadAnalytics, 30_000);
  const refresh = () => void query.refresh();
  const data = query.data;
  const unlockedCount = data?.lifeList.filter((item) => item.is_unlocked).length ?? 0;
  const peakHour = data?.summary.peak_hour;

  return (
    <div className="space-y-6">
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
                  Resumo do histórico local de visitas
                </p>
              </div>
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
            </div>
          </section>

          <section className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
            <div className="mb-4">
              <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
                Frequência por horário
              </h2>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Visitas de todo o histórico, distribuídas pelas 24 horas do dia
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

          <section>
            <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
              <div>
                <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
                  Álbum de conquistas
                </h2>
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  Sua Life List de espécies cadastradas no catálogo
                </p>
              </div>
              <p className="text-xs text-[var(--color-text-muted)]">
                {unlockedCount} desbloqueada(s) · {data.lifeList.length} no catálogo
              </p>
            </div>

            {data.lifeList.length === 0 ? (
              <div className="rounded-xl border border-dashed border-dark-700 px-6 py-10 text-center">
                <Bird className="mx-auto h-8 w-8 text-emerald-400" />
                <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                  Seu álbum está vazio. Cadastre espécies em “Minhas Aves” para começar.
                </p>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {data.lifeList.map((species) => {
                  const imageUrl =
                    species.featured_photo_url ?? species.reference_image_url;
                  return (
                    <article
                      key={species.id}
                      className={`overflow-hidden rounded-xl border bg-dark-800 ${
                        species.is_unlocked
                          ? "border-emerald-500/25"
                          : "border-dark-700"
                      }`}
                    >
                      <div className="relative aspect-[4/3] overflow-hidden bg-dark-900">
                        {imageUrl ? (
                          <img
                            src={imageUrl}
                            alt={
                              species.is_unlocked
                                ? `Registro de ${species.common_name}`
                                : `Silhueta de ${species.common_name}`
                            }
                            className={`h-full w-full object-cover ${
                              species.is_unlocked
                                ? ""
                                : "grayscale opacity-35"
                            }`}
                            loading="lazy"
                          />
                        ) : (
                          <div className="flex h-full items-center justify-center">
                            <Bird
                              aria-hidden
                              className={`h-16 w-16 ${
                                species.is_unlocked
                                  ? "text-emerald-400/50"
                                  : "text-[var(--color-text-muted)]/30"
                              }`}
                            />
                          </div>
                        )}
                        {!species.is_unlocked ? (
                          <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                            <LockKeyhole className="h-7 w-7 text-white/70" />
                          </div>
                        ) : null}
                        <span
                          className={`absolute left-3 top-3 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${
                            species.is_unlocked
                              ? "border-emerald-400/30 bg-dark-900/80 text-emerald-300"
                              : "border-white/10 bg-dark-900/80 text-[var(--color-text-muted)]"
                          }`}
                        >
                          {species.is_unlocked
                            ? `Primeiro registro: ${formatDateTime(species.first_seen_at)}`
                            : "Ainda não registrada"}
                        </span>
                      </div>
                      <div className="space-y-1 p-4">
                        <h3 className="font-medium text-[var(--color-text-primary)]">
                          {species.common_name}
                        </h3>
                        <p className="text-xs italic text-[var(--color-text-muted)]">
                          {species.scientific_name}
                        </p>
                        <p className="pt-2 text-xs text-[var(--color-text-muted)]">
                          {species.is_unlocked
                            ? `${numberFormat.format(species.sightings_count)} visita(s)`
                            : "Visite o alimentador para desbloquear"}
                        </p>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
