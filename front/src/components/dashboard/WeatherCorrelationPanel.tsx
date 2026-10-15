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
import type { ReactNode } from "react";
import { CloudSun, Droplets, Thermometer } from "lucide-react";
import type { WeatherCorrelation } from "@/types";
import { weatherEmoji } from "@/utils/weather";

const numberFormat = new Intl.NumberFormat("pt-BR");

function formatTemperature(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}°C`;
}

/**
 * Painel de insights que cruza a frequência de visitas com as condições do
 * tempo (temperatura, umidade e condição registradas pela Open-Meteo).
 */
export function WeatherCorrelationPanel({ data }: { data: WeatherCorrelation }) {
  const chartData = data.by_category.map((item) => ({
    label: item.condition,
    icon: weatherEmoji(item.condition),
    visits: item.visits,
    avgTemperature: item.avg_temperature,
  }));

  const hasWeatherData = data.visits_with_weather > 0 && chartData.length > 0;
  const leading = chartData[0];
  const peak = data.peak_hours[0];

  return (
    <section className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
            Clima e visitas
          </h2>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Como as condições do tempo influenciam a presença dos passarinhos
          </p>
        </div>
        <span className="rounded-lg bg-sky-500/10 p-2 text-sky-300">
          <CloudSun className="h-4 w-4" />
        </span>
      </div>

      {!hasWeatherData ? (
        <div className="rounded-lg border border-dashed border-dark-700 px-6 py-8 text-center text-sm text-[var(--color-text-muted)]">
          Ainda não há visitas com dados de clima registrados. As novas capturas
          passarão a incluir temperatura, umidade e condição do tempo.
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <InsightCard
              icon={<CloudSun className="h-4 w-4" />}
              label="Visitas com clima"
              value={numberFormat.format(data.visits_with_weather)}
              detail={`de ${numberFormat.format(data.total_visits)} no total`}
            />
            <InsightCard
              icon={<Thermometer className="h-4 w-4" />}
              label="Temperatura média"
              value={formatTemperature(data.avg_temperature_on_visits)}
              detail={`entre ${formatTemperature(
                data.min_temperature_on_visits,
              )} e ${formatTemperature(data.max_temperature_on_visits)}`}
            />
            <InsightCard
              icon={<Droplets className="h-4 w-4" />}
              label="Horário de pico"
              value={peak?.hour ?? "—"}
              detail={
                peak?.avg_temperature != null
                  ? `${formatTemperature(peak.avg_temperature)} em média`
                  : "sem dados de temperatura"
              }
            />
          </div>

          <div
            className="mt-5 h-60 w-full"
            role="img"
            aria-label="Gráfico de visitas por condição do tempo"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
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
                  allowDecimals={false}
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
                    const temp = item?.payload?.avgTemperature;
                    return [
                      `${numberFormat.format(Number(value))} visita(s)${
                        temp != null ? ` · ${formatTemperature(temp)}` : ""
                      }`,
                      "Registros",
                    ];
                  }}
                />
                <Bar dataKey="visits" name="Visitas" radius={[4, 4, 0, 0]}>
                  {chartData.map((item) => (
                    <Cell
                      key={item.label}
                      fill={item.label === leading?.label ? "#38bdf8" : "#0ea5e9"}
                      fillOpacity={item.visits > 0 ? 0.9 : 0.25}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {leading ? (
            <p className="mt-3 text-xs text-[var(--color-text-muted)]">
              <span aria-hidden>{leading.icon}</span> A maioria das visitas (
              {numberFormat.format(leading.visits)}) ocorreu com o tempo “
              {leading.label}”.
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

function InsightCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <article className="rounded-lg border border-dark-700 bg-dark-900/60 p-3">
      <div className="flex items-center gap-2 text-sky-300">
        {icon}
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
