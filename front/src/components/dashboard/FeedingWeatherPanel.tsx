import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  CloudRain,
  CloudSun,
  Droplets,
  Gauge,
  MapPin,
  RefreshCw,
  Sparkles,
  Timer,
} from "lucide-react";
import type { FeedingWeatherGarden } from "@/types";
import {
  fetchFeedingWeatherInsights,
  getErrorMessage,
} from "@/services/api";
import { usePolling } from "@/hooks/usePolling";
import { cn } from "@/utils/cn";

/** Cores por tom do insight (mantém o Dark Mode coeso). */
const TONES: Record<
  string,
  { ring: string; glow: string; text: string; chip: string; bar: string }
> = {
  warning: {
    ring: "border-amber-400/30",
    glow: "from-amber-400/15",
    text: "text-amber-200",
    chip: "bg-amber-400/10 text-amber-200 border-amber-400/20",
    bar: "bg-amber-400",
  },
  info: {
    ring: "border-sky-400/30",
    glow: "from-sky-400/15",
    text: "text-sky-200",
    chip: "bg-sky-400/10 text-sky-200 border-sky-400/20",
    bar: "bg-sky-400",
  },
  positive: {
    ring: "border-emerald-400/30",
    glow: "from-emerald-400/15",
    text: "text-emerald-200",
    chip: "bg-emerald-400/10 text-emerald-200 border-emerald-400/20",
    bar: "bg-emerald-400",
  },
  neutral: {
    ring: "border-dark-600",
    glow: "from-slate-400/10",
    text: "text-[var(--color-text-muted)]",
    chip: "bg-dark-700 text-[var(--color-text-muted)] border-dark-600",
    bar: "bg-slate-400",
  },
};

function toneOf(garden: FeedingWeatherGarden) {
  return TONES[garden.tone] ?? TONES.neutral;
}

function liftLabel(lift: number): string {
  const rounded = Math.round(Math.abs(lift));
  if (rounded === 0) return "estável";
  return `${lift >= 0 ? "+" : "−"}${rounded}%`;
}

/**
 * Card "Insights Meteorológicos do Bem-Te-Vi Core".
 *
 * Cruza a previsão das próximas horas de cada jardim com o histórico de
 * alimentação daquele jardim. Quando há chuva a caminho, mostra a estimativa de
 * intensificação (ou redução) da atividade e a ação tomada pelo Bem-Te-Vi Core.
 */
export function FeedingWeatherPanel() {
  const query = usePolling(() => fetchFeedingWeatherInsights(), 5 * 60_000);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const gardens = query.data?.gardens ?? [];
  const highlight = query.data?.highlight ?? null;

  // Mantém uma seleção válida quando a lista de jardins muda.
  useEffect(() => {
    if (!gardens.length) {
      if (selectedId !== null) setSelectedId(null);
      return;
    }
    if (!selectedId || !gardens.some((garden) => garden.camera_id === selectedId)) {
      setSelectedId(highlight?.camera_id ?? gardens[0].camera_id);
    }
  }, [gardens, highlight?.camera_id, selectedId]);

  const selected = useMemo(
    () =>
      gardens.find((garden) => garden.camera_id === selectedId) ??
      highlight ??
      gardens[0] ??
      null,
    [gardens, highlight, selectedId],
  );

  if (query.error && !query.data) {
    return (
      <article className="rounded-2xl border border-dark-700 bg-dark-800 p-5">
        <Header query={query} />
        <p className="mt-4 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-300">
          {getErrorMessage(query.error, "Não foi possível carregar os insights de clima.")}
        </p>
      </article>
    );
  }

  if (!query.data) {
    return (
      <article className="rounded-2xl border border-dark-700 bg-dark-800 p-5">
        <Header query={query} />
        <div className="mt-4 space-y-2">
          <div className="h-4 w-3/4 animate-pulse rounded bg-dark-700" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-dark-700" />
        </div>
      </article>
    );
  }

  return (
    <article
      className={cn(
        "relative overflow-hidden rounded-2xl border bg-dark-800 p-5",
        selected ? toneOf(selected).ring : "border-dark-700",
      )}
    >
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-0 bg-gradient-to-br to-transparent opacity-70",
          selected ? toneOf(selected).glow : "from-transparent",
        )}
      />
      <div className="relative">
        <Header query={query} />

        {gardens.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-dark-600 px-4 py-6 text-center">
            <MapPin className="mx-auto h-6 w-6 text-[var(--color-text-muted)]" />
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
              Cadastre a localização de uma câmera para o Bem-Te-Vi Core cruzar a
              previsão do tempo com a atividade das aves.
            </p>
          </div>
        ) : selected ? (
          <>
            <div className="mt-4 flex items-start gap-4">
              <span
                className={cn(
                  "flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border text-2xl shadow-inner",
                  selected.forecast?.rain_expected
                    ? "border-sky-400/30 bg-sky-400/10"
                    : "border-emerald-400/30 bg-emerald-400/10",
                )}
                aria-hidden
              >
                {selected.forecast?.rain_expected ? "🌧️" : selected.icon}
              </span>
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                  {selected.garden}
                  {selected.country ? ` · ${selected.country}` : ""}
                </p>
                <p
                  className={cn(
                    "mt-1 font-display text-lg font-semibold leading-snug",
                    toneOf(selected).text,
                  )}
                >
                  {selected.headline}
                </p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-muted)]">
                  {selected.detail}
                </p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
              <Chip icon={CloudRain} tone={toneOf(selected)}>
                {selected.forecast?.rain_expected
                  ? `Chuva ${
                      selected.forecast.rain_in_hours === 0
                        ? "agora"
                        : `em ~${selected.forecast.rain_in_hours}h`
                    }`
                  : "Tempo firme"}
              </Chip>
              {selected.forecast ? (
                <Chip icon={Droplets} tone={toneOf(selected)}>
                  {selected.forecast.peak_probability}% de chuva
                </Chip>
              ) : null}
              <Chip icon={Gauge} tone={toneOf(selected)}>
                {selected.history.confidence === "estimativa"
                  ? "Estimativa inicial"
                  : `Confiança ${selected.history.confidence}`}
              </Chip>
              {selected.history.best_window ? (
                <Chip icon={Timer} tone={toneOf(selected)}>
                  Pico histórico ~{selected.history.best_window}
                </Chip>
              ) : null}
            </div>

            <div className="mt-4 rounded-xl border border-dark-700 bg-dark-900/60 p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  {selected.history.lift_percent >= 0 ? (
                    <ArrowUpRight className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <ArrowDownRight className="h-4 w-4 text-amber-400" />
                  )}
                  <span className="text-xs font-medium text-[var(--color-text-primary)]">
                    Atividade em dias de chuva
                  </span>
                </div>
                <span
                  className={cn(
                    "font-mono text-sm font-semibold",
                    selected.history.lift_percent >= 0
                      ? "text-emerald-300"
                      : "text-amber-300",
                  )}
                >
                  {liftLabel(selected.history.lift_percent)}
                </span>
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-dark-700">
                <div
                  className={cn("h-full rounded-full", toneOf(selected).bar)}
                  style={{
                    width: `${Math.max(
                      6,
                      Math.min(100, Math.abs(selected.history.lift_percent)),
                    )}%`,
                  }}
                />
              </div>
              <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
                <Sparkles className="h-3.5 w-3.5 text-emerald-400/80" />
                <span>{selected.action}</span>
              </div>
            </div>

            {gardens.length > 1 ? (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {gardens.map((garden) => {
                  const active = garden.camera_id === selected.camera_id;
                  return (
                    <button
                      key={garden.camera_id}
                      type="button"
                      onClick={() => setSelectedId(garden.camera_id)}
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition",
                        active
                          ? "border-emerald-400/40 bg-emerald-400/15 text-emerald-200"
                          : "border-dark-600 bg-dark-900/50 text-[var(--color-text-muted)] hover:border-dark-500 hover:text-[var(--color-text-primary)]",
                      )}
                    >
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          garden.forecast?.rain_expected
                            ? "bg-sky-400"
                            : garden.available
                              ? "bg-emerald-400"
                              : "bg-slate-500",
                        )}
                      />
                      {garden.garden}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </article>
  );
}

function Header({
  query,
}: {
  query: {
    loading: boolean;
    refresh: () => void | Promise<void>;
  };
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400">
          <CloudSun className="h-4 w-4" />
        </span>
        <div>
          <h2 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
            Insights Meteorológicos do Bem-Te-Vi Core
          </h2>
          <p className="text-[11px] text-[var(--color-text-muted)]">
            Previsão de chuva × comportamento histórico de alimentação
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => void query.refresh()}
        disabled={query.loading}
        aria-label="Atualizar insights meteorológicos"
        className="rounded-lg border border-dark-700 p-2 text-[var(--color-text-muted)] transition hover:text-emerald-400 disabled:opacity-50"
      >
        <RefreshCw className={cn("h-4 w-4", query.loading && "animate-spin")} />
      </button>
    </div>
  );
}

function Chip({
  icon: Icon,
  tone,
  children,
}: {
  icon: typeof CloudRain;
  tone: (typeof TONES)[string];
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1",
        tone.chip,
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </span>
  );
}
