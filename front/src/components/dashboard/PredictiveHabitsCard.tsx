import { useState } from "react";
import {
  Activity,
  Brain,
  CalendarDays,
  CloudSun,
  Droplets,
  RefreshCw,
  Sparkles,
  Thermometer,
  Timer,
} from "lucide-react";

import { usePolling } from "@/hooks/usePolling";
import {
  fetchBehavioralPrediction,
  getErrorMessage,
  refreshBehavioralMemory,
} from "@/services/api";
import { cn } from "@/utils/cn";
import type { BehavioralFactor, BehavioralPrediction } from "@/types";

/** Paleta por tom da previsão (coerente com o Dark Mode do painel). */
const TONES: Record<
  string,
  { ring: string; glow: string; text: string; chip: string; bar: string }
> = {
  positive: {
    ring: "border-emerald-400/30",
    glow: "from-emerald-400/15",
    text: "text-emerald-200",
    chip: "border-emerald-400/20 bg-emerald-400/10 text-emerald-200",
    bar: "bg-emerald-400",
  },
  info: {
    ring: "border-sky-400/30",
    glow: "from-sky-400/15",
    text: "text-sky-200",
    chip: "border-sky-400/20 bg-sky-400/10 text-sky-200",
    bar: "bg-sky-400",
  },
  neutral: {
    ring: "border-dark-600",
    glow: "from-slate-400/10",
    text: "text-[var(--color-text-muted)]",
    chip: "border-dark-600 bg-dark-700 text-[var(--color-text-muted)]",
    bar: "bg-slate-400",
  },
};

const FACTOR_ICONS: Record<string, typeof Timer> = {
  horario: Timer,
  temperatura: Thermometer,
  umidade: Droplets,
  clima: CloudSun,
  sazonalidade: CalendarDays,
};

function toneOf(prediction: BehavioralPrediction) {
  return TONES[prediction.tone] ?? TONES.neutral;
}

function FactorRow({ factor }: { factor: BehavioralFactor }) {
  const Icon = FACTOR_ICONS[factor.key] ?? Activity;
  return (
    <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--color-text-primary)]">
          <Icon className="h-3.5 w-3.5 text-[var(--color-text-muted)]" />
          {factor.label}
        </span>
        <span className="font-mono text-[11px] text-[var(--color-text-muted)]">
          {factor.score}%
        </span>
      </div>
      <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-dark-700">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            factor.score >= 65
              ? "bg-emerald-400"
              : factor.score >= 40
                ? "bg-sky-400"
                : "bg-slate-500",
          )}
          style={{ width: `${Math.max(4, Math.min(100, factor.score))}%` }}
        />
      </div>
      <p className="mt-1 text-[11px] leading-snug text-[var(--color-text-muted)]">
        {factor.detail}
      </p>
    </div>
  );
}

/**
 * Card preditivo da **Memória Comportamental**.
 *
 * Cruza o histórico de visitas com horário do dia, temperatura/umidade e
 * sazonalidade — e devolve a frase pronta do Bem-Te-Vi Core, por exemplo:
 * "Probabilidade de pico de Beija-Flores nas próximas 2 horas: 85% —
 * condizente com a umidade e histórico de temperatura".
 */
export function PredictiveHabitsCard() {
  const query = usePolling(() => fetchBehavioralPrediction({ limit: 5 }), 300_000);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshError(null);
    try {
      await refreshBehavioralMemory();
      await query.refresh();
    } catch (error) {
      setRefreshError(getErrorMessage(error, "Falha ao atualizar a memória"));
    } finally {
      setRefreshing(false);
    }
  };

  const highlight = query.data?.highlight ?? null;
  const others = (query.data?.predictions ?? []).filter(
    (item) => item.species !== highlight?.species,
  );
  const tone = highlight ? toneOf(highlight) : TONES.neutral;
  const weather = query.data?.current_weather;

  return (
    <article
      className={cn(
        "relative overflow-hidden rounded-2xl border bg-dark-800 p-5",
        highlight ? tone.ring : "border-dark-700",
      )}
    >
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-0 bg-gradient-to-br to-transparent opacity-70",
          highlight ? tone.glow : "from-transparent",
        )}
      />

      <div className="relative">
        <header className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-violet-400/25 bg-violet-400/10">
              <Brain className="h-5 w-5 text-violet-300" />
            </span>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
                Memória Comportamental
              </p>
              <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
                Previsão de picos do jardim
              </h2>
              <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">
                {query.data
                  ? `${query.data.history_days} dias de histórico · janela de ${query.data.horizon_hours}h`
                  : "Cruzando histórico, clima e sazonalidade…"}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={refreshing || query.loading}
            className="flex items-center gap-1.5 rounded-lg border border-dark-600 bg-dark-900/60 px-2.5 py-1.5 text-[11px] text-[var(--color-text-muted)] transition hover:border-dark-500 hover:text-[var(--color-text-primary)] disabled:opacity-50"
            title="Reconstruir os perfis comportamentais agora"
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", refreshing && "animate-spin")}
            />
            Atualizar
          </button>
        </header>

        {query.error ? (
          <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {query.error}
          </p>
        ) : null}
        {refreshError ? (
          <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            {refreshError}
          </p>
        ) : null}

        {query.loading && !query.data ? (
          <div className="mt-4 space-y-2">
            <div className="h-4 w-4/5 animate-pulse rounded bg-dark-700" />
            <div className="h-4 w-3/5 animate-pulse rounded bg-dark-700" />
            <div className="h-16 animate-pulse rounded-xl bg-dark-700" />
          </div>
        ) : highlight ? (
          <>
            <div className="mt-4 flex items-start gap-4">
              <div className="relative flex h-20 w-20 shrink-0 flex-col items-center justify-center rounded-2xl border border-dark-600 bg-dark-900/70">
                <span className="text-2xl" aria-hidden>
                  {highlight.icon || "🐦"}
                </span>
                <span className={cn("font-display text-xl font-bold", tone.text)}>
                  {highlight.probability}%
                </span>
                <span className="text-[9px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  {highlight.horizon_hours}h
                </span>
              </div>

              <div className="min-w-0">
                <p
                  className={cn(
                    "font-display text-base font-semibold leading-snug",
                    tone.text,
                  )}
                >
                  {highlight.headline}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-[var(--color-text-muted)]">
                  {highlight.detail}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                  <span
                    className={cn(
                      "rounded-full border px-2 py-0.5 font-medium",
                      tone.chip,
                    )}
                  >
                    <Sparkles className="mr-1 inline h-3 w-3" />
                    Confiança {highlight.confidence}
                  </span>
                  {highlight.expected_peak_hour ? (
                    <span className="rounded-full border border-dark-600 bg-dark-900/60 px-2 py-0.5 text-[var(--color-text-muted)]">
                      Pico ~{highlight.expected_peak_hour}
                    </span>
                  ) : null}
                  <span className="rounded-full border border-dark-600 bg-dark-900/60 px-2 py-0.5 text-[var(--color-text-muted)]">
                    {highlight.visits_analyzed} visitas analisadas
                  </span>
                  {weather?.available ? (
                    <span className="rounded-full border border-dark-600 bg-dark-900/60 px-2 py-0.5 text-[var(--color-text-muted)]">
                      <CloudSun className="mr-1 inline h-3 w-3" />
                      {weather.condition}
                      {weather.temperature != null
                        ? ` · ${Math.round(weather.temperature)}°C`
                        : ""}
                      {weather.humidity != null
                        ? ` · ${Math.round(weather.humidity)}% UR`
                        : ""}
                    </span>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {highlight.factors.map((factor) => (
                <FactorRow key={factor.key} factor={factor} />
              ))}
            </div>

            {others.length > 0 ? (
              <div className="mt-4 border-t border-dark-700 pt-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                  Outros candidatos
                </p>
                <ul className="mt-2 space-y-1.5">
                  {others.map((prediction) => (
                    <li
                      key={prediction.species}
                      className="flex items-center justify-between gap-3 text-xs"
                    >
                      <span className="flex min-w-0 items-center gap-1.5 text-[var(--color-text-primary)]">
                        <span aria-hidden>{prediction.icon || "🐦"}</span>
                        <span className="truncate">{prediction.species}</span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        <span className="h-1 w-24 overflow-hidden rounded-full bg-dark-700">
                          <span
                            className={cn("block h-full rounded-full", toneOf(prediction).bar)}
                            style={{
                              width: `${Math.max(
                                4,
                                Math.min(100, prediction.probability),
                              )}%`,
                            }}
                          />
                        </span>
                        <span className="w-9 text-right font-mono text-[var(--color-text-muted)]">
                          {prediction.probability}%
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : (
          <div className="mt-4 rounded-xl border border-dashed border-dark-600 px-4 py-6 text-center">
            <Brain className="mx-auto h-6 w-6 text-[var(--color-text-muted)]" />
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
              {query.data?.notes ||
                "Ainda não há histórico suficiente para prever picos. As previsões aparecem após algumas visitas identificadas."}
            </p>
          </div>
        )}
      </div>
    </article>
  );
}
