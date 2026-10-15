import type { CurrentWeather } from "@/types";

/**
 * Emoji associado a cada rótulo de clima em pt-BR persistido na visita.
 * Os rótulos espelham os códigos WMO convertidos em `weather_service.py`.
 */
const LABEL_ICONS: Record<string, string> = {
  Ensolarado: "☀️",
  "Predomínio de sol": "🌤️",
  "Parcialmente nublado": "⛅",
  Nublado: "☁️",
  Nevoeiro: "🌫️",
  "Nevoeiro com geada": "🌫️",
  "Chuvisco leve": "🌦️",
  Chuvisco: "🌦️",
  "Chuvisco forte": "🌦️",
  "Chuvisco congelante": "🌧️",
  "Chuvisco congelante forte": "🌧️",
  "Chuva leve": "🌧️",
  Chuva: "🌧️",
  "Chuva forte": "🌧️",
  "Chuva congelante": "🌧️",
  "Chuva congelante forte": "🌧️",
  "Neve leve": "🌨️",
  Neve: "🌨️",
  "Neve forte": "❄️",
  "Grãos de neve": "❄️",
  "Pancadas de chuva": "🌦️",
  "Pancadas de chuva moderadas": "🌧️",
  "Pancadas de chuva fortes": "⛈️",
  "Pancadas de neve": "🌨️",
  "Pancadas de neve fortes": "🌨️",
  Tempestade: "⛈️",
  "Tempestade com granizo": "⛈️",
  "Tempestade com granizo forte": "⛈️",
};

/** Devolve o emoji do clima a partir do rótulo persistido na visita. */
export function weatherEmoji(label: string | null | undefined): string {
  if (!label) return "🌡️";
  return LABEL_ICONS[label] ?? "🌡️";
}

export function formatTemperature(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value)}°C`;
}

export function formatHumidity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value)}%`;
}

export function formatWind(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value)} km/h`;
}

type WeatherFields = {
  temperature?: number | null;
  humidity?: number | null;
  weather_code?: string | null;
  wind_speed?: number | null;
};

/** Indica se há algum dado meteorológico registrado na visita/detecção. */
export function hasWeather(entry: WeatherFields): boolean {
  return (
    entry.temperature != null ||
    entry.humidity != null ||
    entry.weather_code != null ||
    entry.wind_speed != null
  );
}

/** Indica se o clima atual está disponível (online ou vindo do cache). */
export function weatherIsAvailable(
  weather: CurrentWeather | null,
): weather is CurrentWeather {
  return Boolean(weather?.available);
}
