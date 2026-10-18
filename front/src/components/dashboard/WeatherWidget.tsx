import { useCallback, useRef, useState } from "react";
import { Droplets, MapPin, Thermometer, Wind } from "lucide-react";
import type { ReactNode } from "react";
import type { Camera } from "@/types";
import { fetchCurrentWeather, getCameraWeather } from "@/services/api";
import { usePolling } from "@/hooks/usePolling";
import {
  formatHumidity,
  formatTemperature,
  formatWind,
} from "@/utils/weather";

type Props = {
  /** Câmeras/jardins disponíveis para o seletor de localidade do clima. */
  cameras: Camera[];
};

/** Clima normalizado, seja da localização global ou do jardim selecionado. */
type WeatherView = {
  available: boolean;
  condition: string;
  icon: string;
  temperature: number | null;
  humidity: number | null;
  wind_speed: number | null;
  /** Horário local do jardim remoto (ex.: "14:30"), quando houver fuso. */
  localTime: string | null;
  /** Rótulo da localidade exibida (nome do jardim ou "Localização global"). */
  location: string;
};

/**
 * Card de clima com **seletor de localidade**.
 *
 * O observador alterna entre a **localização global** (padrão do sistema) e o
 * **clima local de cada jardim** cadastrado (cada câmera pode ter coordenadas e
 * fuso próprios). O backend mantém um cache de 30 minutos da Open-Meteo; aqui
 * apenas sincronizamos de tempos em tempos. Se o clima estiver indisponível
 * (sem internet e sem cache), o card permanece visível com um aviso — sem
 * travar a página.
 */
export function WeatherWidget({ cameras }: Props) {
  const [selected, setSelected] = useState("");
  // Ref atualizada de forma síncrona: garante que o `refresh` use a seleção
  // nova imediatamente (evita corrida com o estado assíncrono do React).
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const camerasRef = useRef(cameras);
  camerasRef.current = cameras;

  const load = useCallback(async (): Promise<WeatherView> => {
    const target = selectedRef.current;
    if (target) {
      const camera = camerasRef.current.find((cam) => cam.id === target);
      const data = await getCameraWeather(target);
      return {
        available: data.available,
        condition: data.condition,
        icon: data.icon,
        temperature: data.temperature,
        humidity: data.humidity,
        wind_speed: data.wind_speed,
        localTime: data.local_time_label,
        location: camera?.location_label || camera?.name || "Jardim",
      };
    }
    const data = await fetchCurrentWeather();
    return {
      available: data.available,
      condition: data.condition,
      icon: data.icon,
      temperature: data.temperature,
      humidity: data.humidity,
      wind_speed: data.wind_speed,
      localTime: null,
      location: "Localização global",
    };
  }, []);

  const query = usePolling(load, 600_000);
  const weather = query.data;
  const available = Boolean(weather?.available);

  const handleSelect = (value: string) => {
    selectedRef.current = value;
    setSelected(value);
    void query.refresh();
  };

  return (
    <section
      aria-label="Clima atual por localidade"
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-xl border border-dark-700 bg-dark-800/80 px-4 py-3"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="text-2xl leading-none" aria-hidden>
          {available ? weather?.icon : "🌡️"}
        </span>
        <div className="min-w-0">
          <label className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            <MapPin className="h-3 w-3" />
            Clima
            <select
              value={selected}
              onChange={(e) => handleSelect(e.target.value)}
              className="ml-1 rounded-md border border-dark-700 bg-dark-900/70 px-2 py-1 text-[11px] font-normal normal-case text-[var(--color-text-primary)]"
            >
              <option value="">Localização global</option>
              {cameras.map((cam) => (
                <option key={cam.id} value={cam.id}>
                  {cam.location_label || cam.name || "Jardim sem nome"}
                </option>
              ))}
            </select>
          </label>
          <p className="mt-0.5 truncate text-sm font-semibold text-[var(--color-text-primary)]">
            {available
              ? `${weather?.condition}${
                  weather?.localTime ? ` · ${weather.localTime}` : ""
                }`
              : query.loading
                ? "Carregando clima…"
                : "Clima indisponível"}
          </p>
          <p className="truncate text-[10px] text-[var(--color-text-muted)]">
            {weather?.location ?? "Localização global"}
          </p>
        </div>
      </div>

      {available ? (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <WeatherMetric
            icon={<Thermometer className="h-3.5 w-3.5" />}
            label="Temperatura"
            value={formatTemperature(weather?.temperature)}
          />
          <WeatherMetric
            icon={<Droplets className="h-3.5 w-3.5" />}
            label="Umidade"
            value={formatHumidity(weather?.humidity)}
          />
          <WeatherMetric
            icon={<Wind className="h-3.5 w-3.5" />}
            label="Vento"
            value={formatWind(weather?.wind_speed)}
          />
        </div>
      ) : (
        <p className="text-xs text-[var(--color-text-muted)]">
          Sem dados de clima para esta localidade. Confira as coordenadas do
          jardim em Configurações.
        </p>
      )}
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
