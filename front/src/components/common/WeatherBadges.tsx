import {
  formatHumidity,
  formatTemperature,
  hasWeather,
  weatherEmoji,
} from "@/utils/weather";

type Props = {
  temperature: number | null;
  humidity: number | null;
  weather_code: string | null;
  className?: string;
};

/**
 * Badges compactos com o clima do momento da captura, por exemplo:
 * `☀️ 25°C · 💧 60%`. Não renderiza nada quando não há dados.
 */
export function WeatherBadges({
  temperature,
  humidity,
  weather_code,
  className,
}: Props) {
  if (!hasWeather({ temperature, humidity, weather_code })) return null;

  return (
    <div
      className={`flex flex-wrap items-center gap-1.5 ${className ?? ""}`}
      aria-label="Condições do tempo no momento do registro"
    >
      {temperature != null ? (
        <span title={weather_code ?? "Temperatura"} className={badgeClass}>
          <span aria-hidden>{weatherEmoji(weather_code)}</span>
          {formatTemperature(temperature)}
        </span>
      ) : null}
      {humidity != null ? (
        <span title="Umidade relativa" className={badgeClass}>
          <span aria-hidden>💧</span>
          {formatHumidity(humidity)}
        </span>
      ) : null}
    </div>
  );
}

const badgeClass =
  "inline-flex items-center gap-1 rounded-full border border-sky-400/25 bg-sky-400/10 px-2 py-0.5 text-[11px] font-medium text-sky-200";
