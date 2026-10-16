import { useMemo, useState } from "react";
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
  CloudRain,
  CloudSun,
  Droplets,
  Sparkles,
  Thermometer,
  Timer,
} from "lucide-react";
import type { WeatherInsights } from "@/types";
import { cn } from "@/utils/cn";

const numberFormat = new Intl.NumberFormat("pt-BR");

/** Métrica exibida no gráfico de faixas de temperatura (interativo). */
type RangeMetric = "visits" | "species" | "perDay";

const RANGE_METRICS: { id: RangeMetric; label: string; hint: string }[] = [
  { id: "visits", label: "Visitas", hint: "Nº de visitas por faixa de temperatura" },
  { id: "species", label: "Espécies", hint: "Espécies diferentes por faixa" },
  { id: "perDay", label: "Visitas/dia", hint: "Média de visitas por dia na faixa" },
];

function formatTemperature(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}°C`;
}

/** Cor de destaque do card conforme o tom sugerido pelo back-end. */
const TONE_STYLES: Record<string, string> = {
  positive: "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
  info: "border-sky-500/30 bg-sky-500/10 text-sky-200",
  warning: "border-amber-400/30 bg-amber-400/10 text-amber-100",
  neutral: "border-dark-700 bg-dark-900/60 text-[var(--color-text-primary)]",
};

/**
 * Seção "Insights Comportamentais & Clima".
 *
 * Combina os cards de resumo inteligente com gráficos cruzados interativos:
 * faixas de temperatura (com métrica alternável), chuva x tempo seco,
 * horário médio no frio x no calor e mudança de horário por espécie.
 */
export function WeatherInsightsPanel({ data }: { data: WeatherInsights }) {
  const [metric, setMetric] = useState<RangeMetric>("visits");

  const rangeData = useMemo(
    () =>
      data.temperature_ranges.map((range) => ({
        label: range.label,
        visits: range.visits,
        species: range.distinct_species,
        perDay: Number(range.visits_per_day.toFixed(2)),
        humidity: range.avg_humidity,
        avgHour: range.avg_hour_label,
        topSpecies: range.top_species,
      })),
    [data.temperature_ranges],
  );

  const conditionData = useMemo(
    () =>
      data.conditions.map((condition) => ({
        label: condition.condition,
        icon: condition.icon,
        visits: condition.visits,
        perDay: Number(condition.visits_per_day.toFixed(2)),
        isRain: ["Chuva", "Tempestade"].includes(condition.condition),
      })),
    [data.conditions],
  );

  const hasWeather = data.visits_with_weather > 0;
  const bestLabel = data.best_temperature_range?.label ?? null;
  const activeMetric = RANGE_METRICS.find((item) => item.id === metric);

  const coldPeriod = data.periods.find((period) => period.period === "frio");
  const hotPeriod = data.periods.find((period) => period.period === "quente");

  return (
    <section
      aria-label="Insights comportamentais e clima"
      className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
            Insights Comportamentais &amp; Clima
          </h2>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Cruzamento automático entre temperatura, umidade, clima e os hábitos
            das aves
          </p>
        </div>
        <span className="rounded-lg bg-violet-500/10 p-2 text-violet-300">
          <Sparkles className="h-4 w-4" />
        </span>
      </div>

      {!hasWeather ? (
        <div className="rounded-lg border border-dashed border-dark-700 px-6 py-8 text-center text-sm text-[var(--color-text-muted)]">
          Ainda não há visitas com dados de clima registrados. Assim que as novas
          capturas incluírem temperatura e condição do tempo, os insights
          aparecerão aqui automaticamente.
        </div>
      ) : (
        <div className="space-y-5">
          {/* Cards de resumo inteligente */}
          {data.insights.length > 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {data.insights.map((card) => (
                <article
                  key={card.id}
                  className={cn(
                    "rounded-lg border p-3",
                    TONE_STYLES[card.tone] ?? TONE_STYLES.neutral,
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span aria-hidden className="text-base leading-none">
                      {card.icon}
                    </span>
                    <p className="text-xs font-semibold uppercase tracking-wide opacity-90">
                      {card.title}
                    </p>
                  </div>
                  <p className="mt-2 text-sm leading-snug">
                    {card.description}
                  </p>
                </article>
              ))}
            </div>
          ) : null}

          {/* Faixas de temperatura (gráfico interativo) */}
          <div className="rounded-lg border border-dark-700 bg-dark-900/40 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
                  Faixa de temperatura x atividade
                </h3>
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                  {activeMetric?.hint}
                </p>
              </div>
              <div
                role="group"
                aria-label="Métrica do gráfico de temperatura"
                className="inline-flex rounded-lg border border-dark-700 bg-dark-800 p-1"
              >
                {RANGE_METRICS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setMetric(item.id)}
                    aria-pressed={metric === item.id}
                    className={cn(
                      "rounded-md px-3 py-1.5 text-xs font-medium transition",
                      metric === item.id
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
                    )}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div
              className="h-60 w-full"
              role="img"
              aria-label="Gráfico de atividade por faixa de temperatura"
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={rangeData}
                  margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
                >
                  <CartesianGrid
                    stroke="rgba(138, 163, 153, 0.12)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: "#8aa399", fontSize: 11 }}
                    axisLine={{ stroke: "#1a2420" }}
                    tickLine={false}
                    interval={0}
                  />
                  <YAxis
                    allowDecimals={metric === "perDay"}
                    tick={{ fill: "#8aa399", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(52, 211, 153, 0.08)" }}
                    contentStyle={{
                      background: "#111816",
                      border: "1px solid #1a2420",
                      borderRadius: 8,
                      color: "#e8f5ef",
                    }}
                    labelStyle={{ color: "#8aa399" }}
                    formatter={(value, _name, item) => {
                      const payload = item?.payload as
                        | (typeof rangeData)[number]
                        | undefined;
                      const details: string[] = [
                        `${numberFormat.format(Number(value))} ${
                          metric === "perDay" ? "visita(s)/dia" : "registro(s)"
                        }`,
                      ];
                      if (payload?.topSpecies) {
                        details.push(`espécie líder: ${payload.topSpecies}`);
                      }
                      if (payload?.humidity != null) {
                        details.push(`umidade ${payload.humidity.toFixed(0)}%`);
                      }
                      return [details.join(" · "), activeMetric?.label ?? ""];
                    }}
                  />
                  <Bar dataKey={metric} name={activeMetric?.label} radius={[4, 4, 0, 0]}>
                    {rangeData.map((item) => (
                      <Cell
                        key={item.label}
                        fill={item.label === bestLabel ? "#34d399" : "#10b981"}
                        fillOpacity={item.visits > 0 ? 0.9 : 0.25}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {data.best_temperature_range ? (
              <p className="mt-3 text-xs text-[var(--color-text-muted)]">
                <span aria-hidden>🌡️</span> Melhor faixa:{" "}
                <span className="font-medium text-emerald-300">
                  {data.best_temperature_range.label}
                </span>{" "}
                — {data.best_temperature_range.distinct_species} espécie(s) em{" "}
                {data.best_temperature_range.visits} visita(s), média de{" "}
                {data.best_temperature_range.visits_per_day.toFixed(2)}/dia.
              </p>
            ) : null}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Chuva x tempo seco */}
            <div className="rounded-lg border border-dark-700 bg-dark-900/40 p-4">
              <div className="mb-3 flex items-center gap-2">
                <CloudRain className="h-4 w-4 text-sky-300" />
                <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
                  Chuva x tempo seco
                </h3>
              </div>

              {data.rainy && data.dry ? (
                <div className="mb-3 grid grid-cols-2 gap-3">
                  <ComparisonCard
                    icon="🌧️"
                    label="Chuva"
                    value={`${data.rainy.visits_per_day.toFixed(2)}/dia`}
                    detail={`${data.rainy.visits} visita(s) · ${data.rainy.active_days} dia(s)`}
                  />
                  <ComparisonCard
                    icon="🌤️"
                    label="Tempo seco"
                    value={`${data.dry.visits_per_day.toFixed(2)}/dia`}
                    detail={`${data.dry.visits} visita(s) · ${data.dry.active_days} dia(s)`}
                  />
                </div>
              ) : (
                <p className="mb-3 text-xs text-[var(--color-text-muted)]">
                  Ainda não há registros suficientes de chuva e tempo seco para
                  comparar.
                </p>
              )}

              {conditionData.length > 0 ? (
                <div
                  className="h-44 w-full"
                  role="img"
                  aria-label="Gráfico de visitas por dia segundo o clima"
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={conditionData}
                      margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
                    >
                      <CartesianGrid
                        stroke="rgba(138, 163, 153, 0.12)"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="label"
                        tick={{ fill: "#8aa399", fontSize: 11 }}
                        axisLine={{ stroke: "#1a2420" }}
                        tickLine={false}
                        interval={0}
                      />
                      <YAxis
                        allowDecimals
                        tick={{ fill: "#8aa399", fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip
                        cursor={{ fill: "rgba(56, 189, 248, 0.08)" }}
                        contentStyle={{
                          background: "#111816",
                          border: "1px solid #1a2420",
                          borderRadius: 8,
                          color: "#e8f5ef",
                        }}
                        labelStyle={{ color: "#8aa399" }}
                        formatter={(value, _name, item) => {
                          const payload = item?.payload as
                            | (typeof conditionData)[number]
                            | undefined;
                          return [
                            `${Number(value).toFixed(2)} visita(s)/dia · ${
                              payload?.visits ?? 0
                            } no total`,
                            "Clima",
                          ];
                        }}
                      />
                      <Bar dataKey="perDay" name="Visitas/dia" radius={[4, 4, 0, 0]}>
                        {conditionData.map((item) => (
                          <Cell
                            key={item.label}
                            fill={item.isRain ? "#38bdf8" : "#0ea5e9"}
                            fillOpacity={item.visits > 0 ? 0.9 : 0.25}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : null}
            </div>

            {/* Horário no frio x no calor */}
            <div className="rounded-lg border border-dark-700 bg-dark-900/40 p-4">
              <div className="mb-3 flex items-center gap-2">
                <Timer className="h-4 w-4 text-emerald-300" />
                <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
                  Horário no frio x no calor
                </h3>
              </div>

              {coldPeriod && hotPeriod ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <ComparisonCard
                      icon="🧊"
                      label={coldPeriod.label}
                      value={coldPeriod.avg_hour_label ?? "—"}
                      detail={`${coldPeriod.visits} visita(s) · ${formatTemperature(
                        coldPeriod.avg_temperature,
                      )}`}
                    />
                    <ComparisonCard
                      icon="🔥"
                      label={hotPeriod.label}
                      value={hotPeriod.avg_hour_label ?? "—"}
                      detail={`${hotPeriod.visits} visita(s) · ${formatTemperature(
                        hotPeriod.avg_temperature,
                      )}`}
                    />
                  </div>
                  <p className="mt-3 text-xs text-[var(--color-text-muted)]">
                    {timingPhrase(coldPeriod.avg_hour, hotPeriod.avg_hour)}
                  </p>
                </>
              ) : (
                <p className="text-xs text-[var(--color-text-muted)]">
                  Ainda não há variação de temperatura suficiente para comparar
                  os horários.
                </p>
              )}
            </div>
          </div>

          {/* Horário por espécie */}
          {data.species_timing.length > 0 ? (
            <div className="rounded-lg border border-dark-700 bg-dark-900/40 p-4">
              <div className="mb-3 flex items-center gap-2">
                <Bird className="h-4 w-4 text-amber-200" />
                <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
                  Como cada espécie muda de horário com a temperatura
                </h3>
              </div>
              <ul className="space-y-3">
                {data.species_timing.map((item) => (
                  <SpeciesTimingRow key={item.species} item={item} />
                ))}
              </ul>
            </div>
          ) : null}

          {/* Rodapé com resumo rápido */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-[var(--color-text-muted)]">
            <span className="inline-flex items-center gap-1.5">
              <CloudSun className="h-3.5 w-3.5 text-sky-300" />
              {numberFormat.format(data.visits_with_weather)} de{" "}
              {numberFormat.format(data.total_visits)} visita(s) com clima
            </span>
            {data.cold_threshold_celsius != null ? (
              <span className="inline-flex items-center gap-1.5">
                <Thermometer className="h-3.5 w-3.5 text-emerald-300" />
                Limiar frio/quente: {formatTemperature(data.cold_threshold_celsius)}
              </span>
            ) : null}
            <span className="inline-flex items-center gap-1.5">
              <Droplets className="h-3.5 w-3.5 text-sky-300" />
              Gerado em {new Date(data.generated_at).toLocaleString("pt-BR")}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}

/** Frase pronta comparando o horário médio no frio e no calor. */
function timingPhrase(
  coldHour: number | null,
  hotHour: number | null,
): string {
  if (coldHour == null || hotHour == null) return "";
  const diff = (coldHour - hotHour) * 60;
  if (Math.abs(diff) < 15) {
    return "As aves aparecem praticamente no mesmo horário nas duas condições.";
  }
  const when = diff > 0 ? "mais cedo" : "mais tarde";
  return `No calor, as aves aparecem cerca de ${humanizeMinutes(diff)} ${when} do que no frio.`;
}

function humanizeMinutes(minutes: number): string {
  const total = Math.round(Math.abs(minutes));
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  if (hours && mins) return `${hours}h${String(mins).padStart(2, "0")}`;
  if (hours) return `${hours}h`;
  return `${mins} min`;
}

function ComparisonCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: string;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="rounded-lg border border-dark-700 bg-dark-800 p-3">
      <div className="flex items-center gap-2">
        <span aria-hidden>{icon}</span>
        <p className="text-xs font-medium text-[var(--color-text-muted)]">
          {label}
        </p>
      </div>
      <p className="mt-2 font-display text-lg font-semibold text-[var(--color-text-primary)]">
        {value}
      </p>
      <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{detail}</p>
    </article>
  );
}

/** Linha com a mudança de horário de uma espécie (barra proporcional). */
function SpeciesTimingRow({
  item,
}: {
  item: WeatherInsights["species_timing"][number];
}) {
  const minutes = Math.abs(item.minutes_earlier ?? 0);
  // Escala relativa: 2h de diferença = barra cheia.
  const width = Math.min(100, (minutes / 120) * 100);
  const earlier = (item.minutes_earlier ?? 0) > 0;
  const similar = item.direction === "similar";

  return (
    <li>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-[var(--color-text-primary)]">
            {item.species}
          </p>
          {item.scientific_name ? (
            <p className="truncate text-xs italic text-[var(--color-text-muted)]">
              {item.scientific_name}
            </p>
          ) : null}
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
            similar
              ? "bg-dark-700 text-[var(--color-text-muted)]"
              : earlier
                ? "bg-emerald-500/15 text-emerald-300"
                : "bg-amber-400/15 text-amber-100",
          )}
        >
          {similar
            ? "horário estável"
            : `${earlier ? "−" : "+"}${humanizeMinutes(minutes)} no calor`}
        </span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-dark-700">
        <div
          className={cn(
            "h-full rounded-full",
            similar ? "bg-dark-600" : earlier ? "bg-emerald-400" : "bg-amber-300",
          )}
          style={{ width: `${similar ? 4 : Math.max(6, width)}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">
        Frio às {formatHourValue(item.cold_avg_hour)} · Calor às{" "}
        {formatHourValue(item.hot_avg_hour)}
      </p>
    </li>
  );
}

/** Formata uma hora decimal (ex.: 7.5) como HH:MM. */
function formatHourValue(value: number | null): string {
  if (value == null) return "—";
  const total = Math.round(value * 60) % (24 * 60);
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}
