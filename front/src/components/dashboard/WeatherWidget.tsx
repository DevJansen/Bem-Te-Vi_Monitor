import { Droplets, Thermometer, Wind } from "lucide-react";
import type { ReactNode } from "react";
import { fetchCurrentWeather } from "@/services/api";
import { usePolling } from "@/hooks/usePolling";
import {
  formatHumidity,
  formatTemperature,
  formatWind,
  weatherIsAvailable,
} from "@/utils/weather";

/**
 * Widget discreto com o clima atual do local do alimentador.
 *
 * O backend mantém um cache de 30 minutos da Open-Meteo; aqui apenas
 * sincronizamos o valor de tempos em tempos. Se o clima estiver indisponível
 * (sem internet e sem cache) o widget simplesmente não é renderizado.
 */
export function WeatherWidget() {
  const query = usePolling(fetchCurrentWeather, 600_000);
  const weather = query.data;

  if (!weatherIsAvailable(weather)) return null;

  return (
    <section
      aria-label="Clima atual do local do alimentador"
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-xl border border-dark-700 bg-dark-800/80 px-4 py-3"
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl leading-none" aria-hidden>
          {weather.icon}
        </span>
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Clima atual
          </p>
          <p className="text-sm font-semibold text-[var(--color-text-primary)]">
            {weather.condition}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
        <WeatherMetric
          icon={<Thermometer className="h-3.5 w-3.5" />}
          label="Temperatura"
          value={formatTemperature(weather.temperature)}
        />
        <WeatherMetric
          icon={<Droplets className="h-3.5 w-3.5" />}
          label="Umidade"
          value={formatHumidity(weather.humidity)}
        />
        <WeatherMetric
          icon={<Wind className="h-3.5 w-3.5" />}
          label="Vento"
          value={formatWind(weather.wind_speed)}
        />
      </div>
    </section>
  );
}

function WeatherMetric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sky-300">{icon}</span>
      <div className="leading-none">
        <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {label}
        </p>
        <p className="mt-0.5 text-sm font-semibold text-[var(--color-text-primary)]">
          {value}
        </p>
      </div>
    </div>
  );
}
