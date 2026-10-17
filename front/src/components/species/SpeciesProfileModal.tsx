import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  Bird,
  CalendarClock,
  CloudSun,
  Droplets,
  Flame,
  Leaf,
  LoaderCircle,
  Moon,
  Snowflake,
  Thermometer,
  TrendingUp,
  X,
} from "lucide-react";
import type { SpeciesProfile } from "@/types";
import {
  fetchSpeciesProfile,
  getErrorMessage,
  visitCropUrl,
} from "@/services/api";
import { cn } from "@/utils/cn";
import { formatDateTime } from "@/utils/format";
import { formatHumidity, formatTemperature, weatherEmoji } from "@/utils/weather";
import { formatDwell } from "@/utils/visits";

/** Referência mínima de uma espécie (serve para Minhas Aves e para o Álbum). */
export type SpeciesRef = {
  id: string;
  common_name: string;
  scientific_name: string;
  description?: string;
};

type Props = {
  /** Espécie da ficha (null = modal fechado). */
  species: SpeciesRef | null;
  onClose: () => void;
};

/**
 * Ficha técnica completa de uma espécie ("Minhas Aves" / Álbum de Conquistas).
 *
 * Busca o perfil no backend e exibe conteúdo rico: histórico de avistagens,
 * horários de pico no comedouro, temperatura média preferida (cruzada com a
 * Open-Meteo), notas científicas e o status ecológico regional.
 */
export function SpeciesProfileModal({ species, onClose }: Props) {
  const [profile, setProfile] = useState<SpeciesProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (speciesId: string) => {
    setLoading(true);
    setError(null);
    try {
      setProfile(await fetchSpeciesProfile(speciesId));
    } catch (cause) {
      setError(getErrorMessage(cause, "Não foi possível carregar a ficha."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!species) return;
    setProfile(null);
    setError(null);
    void load(species.id);
  }, [species, load]);

  useEffect(() => {
    if (!species) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [species, onClose]);

  if (!species) return null;

  const hero =
    profile?.best_photo_url ?? profile?.reference_image_url ?? null;
  const peakKey = profile?.peak_hour?.replace("h", "") ?? "";
  const maxHourly = Math.max(
    1,
    ...(profile?.hourly_distribution.map((hour) => hour.visits) ?? [1]),
  );

  return (
    <div className="fixed inset-0 z-[85] flex items-center justify-center p-3 sm:p-6">
      <button
        type="button"
        aria-label="Fechar ficha da espécie"
        onClick={onClose}
        className="absolute inset-0 bg-black/80 backdrop-blur-md"
      />

      <section
        role="dialog"
        aria-modal="true"
        aria-label={`Ficha da espécie ${species.common_name}`}
        className="relative z-10 flex max-h-[92vh] w-full max-w-4xl animate-pop-in flex-col overflow-hidden rounded-2xl border border-emerald-500/20 bg-dark-800/95 shadow-[0_0_70px_-15px_rgba(16,185,129,0.5)]"
      >
        <header className="flex items-start gap-3 border-b border-dark-700 px-4 py-3 sm:px-5">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
            <Bird className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300/90">
              Ficha técnica · Catálogo local
            </p>
            <h2 className="truncate font-display text-base font-semibold text-[var(--color-text-primary)] sm:text-lg">
              {profile?.common_name ?? species.common_name}
            </h2>
            <p className="text-xs italic text-[var(--color-text-muted)]">
              {profile?.scientific_name ?? species.scientific_name}
            </p>
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
          {loading && !profile ? (
            <div className="flex flex-col items-center justify-center gap-3 py-12 text-sm text-[var(--color-text-muted)]">
              <LoaderCircle className="h-7 w-7 animate-spin text-emerald-300" />
              Montando a ficha da espécie…
            </div>
          ) : null}

          {error ? (
            <p
              role="alert"
              className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-200"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </p>
          ) : null}

          {profile ? (
            <>
              {/* Foto + selos */}
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
                <div className="relative aspect-[4/3] overflow-hidden rounded-xl border border-dark-700 bg-dark-900">
                  {hero ? (
                    <img
                      src={hero}
                      alt={`Melhor registro de ${profile.common_name}`}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-[var(--color-text-muted)]">
                      <Bird className="h-10 w-10 text-emerald-400/60" />
                    </div>
                  )}
                </div>
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                      {profile.rarity}
                    </span>
                    {profile.ecological_badge ? (
                      <span
                        className={cn(
                          "rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                          profile.ecological_status === "rara"
                            ? "border-amber-400/40 bg-amber-400/15 text-amber-300"
                            : "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
                        )}
                        title={profile.ecological_status_label ?? ""}
                      >
                        {profile.ecological_badge}
                      </span>
                    ) : null}
                    {profile.badges.map((badge) => (
                      <span
                        key={badge}
                        className="rounded-full border border-dark-600 bg-dark-900 px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-muted)]"
                      >
                        {badge}
                      </span>
                    ))}
                  </div>
                  {profile.description ? (
                    <p className="text-xs leading-relaxed text-[var(--color-text-muted)]">
                      {profile.description}
                    </p>
                  ) : null}
                  {profile.ecological_notes ? (
                    <p className="flex items-start gap-1.5 rounded-lg border border-emerald-500/15 bg-emerald-500/5 p-2 text-[11px] italic leading-snug text-emerald-200/85">
                      <Leaf className="mt-0.5 h-3 w-3 shrink-0" />
                      {profile.ecological_notes}
                    </p>
                  ) : null}
                </div>
              </div>

              {/* Estatísticas de avistagem */}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <StatTile
                  icon={<Activity className="h-3.5 w-3.5" />}
                  label="Avistagens"
                  value={String(profile.visits_count)}
                />
                <StatTile
                  icon={<CalendarClock className="h-3.5 w-3.5" />}
                  label="Dias ativos"
                  value={String(profile.active_days)}
                />
                <StatTile
                  icon={<TrendingUp className="h-3.5 w-3.5" />}
                  label="Horário de pico"
                  value={profile.peak_hour ?? "—"}
                />
                <StatTile
                  icon={<Activity className="h-3.5 w-3.5" />}
                  label="Permanência média"
                  value={formatDwell(profile.average_dwell_seconds)}
                />
              </div>

              <p className="text-xs text-[var(--color-text-muted)]">
                Primeiro registro em {formatDateTime(profile.first_seen_at)} ·
                último em {formatDateTime(profile.last_seen_at)}
              </p>

              {/* Horários de pico (histograma de 24h) */}
              <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
                <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  <CalendarClock className="h-3 w-3" />
                  Horários de pico no comedouro
                </p>
                <div className="flex h-24 items-end gap-[3px]">
                  {profile.hourly_distribution.map((hour) => {
                    const isPeak = hour.hour === peakKey && hour.visits > 0;
                    return (
                      <div
                        key={hour.hour}
                        className="flex flex-1 flex-col items-center justify-end gap-1"
                        title={`${hour.hour}h · ${hour.visits} visita(s)`}
                      >
                        <div
                          className={cn(
                            "w-full rounded-sm transition-all",
                            isPeak ? "bg-emerald-400" : "bg-emerald-500/35",
                          )}
                          style={{
                            height: `${(hour.visits / maxHourly) * 100}%`,
                            minHeight: hour.visits > 0 ? "3px" : "1px",
                          }}
                        />
                        <span className="text-[8px] leading-none text-[var(--color-text-muted)]">
                          {Number(hour.hour) % 3 === 0 ? hour.hour : ""}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Temperatura preferida (Open-Meteo) */}
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
                  <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    <Thermometer className="h-3 w-3" />
                    Temperatura preferida
                  </p>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-[var(--color-text-primary)]">
                    <span className="inline-flex items-center gap-1.5">
                      <Flame className="h-3.5 w-3.5 text-amber-300" />
                      média {formatTemperature(profile.avg_temperature)}
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[var(--color-text-muted)]">
                      <Snowflake className="h-3.5 w-3.5 text-sky-300" />
                      mín {formatTemperature(profile.min_temperature)}
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[var(--color-text-muted)]">
                      <Thermometer className="h-3.5 w-3.5 text-rose-300" />
                      máx {formatTemperature(profile.max_temperature)}
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-[var(--color-text-muted)]">
                      <Droplets className="h-3.5 w-3.5 text-sky-300" />
                      {formatHumidity(profile.avg_humidity)}
                    </span>
                  </div>
                </div>
                <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
                  <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                    <CloudSun className="h-3 w-3" />
                    Visitas por clima
                  </p>
                  {profile.weather_distribution.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {profile.weather_distribution.map((item) => (
                        <span
                          key={item.condition}
                          className="rounded-md bg-dark-700 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-text-primary)]"
                          title={`${item.visits} visita(s) · média ${formatTemperature(item.avg_temperature)}`}
                        >
                          {weatherEmoji(item.condition)} {item.condition} ·{" "}
                          {item.visits}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Sem dados meteorológicos registrados.
                    </p>
                  )}
                </div>
              </div>

              {/* Histórico de avistagens */}
              <div>
                <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  <Bird className="h-3 w-3" />
                  Histórico de avistagens
                </p>
                {profile.recent_sightings.length > 0 ? (
                  <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
                    {profile.recent_sightings.map((sighting) => {
                      const thumb =
                        sighting.crop_url ??
                        sighting.thumbnail_url ??
                        visitCropUrl(sighting.visit_id);
                      return (
                        <figure
                          key={sighting.visit_id}
                          className="group overflow-hidden rounded-lg border border-dark-700 bg-dark-900"
                          title={`${formatDateTime(sighting.detected_at)} · ${formatTemperature(sighting.temperature)}`}
                        >
                          <div className="relative aspect-square">
                            <img
                              src={thumb}
                              alt={`Avistagem em ${formatDateTime(sighting.detected_at)}`}
                              className="h-full w-full object-cover transition group-hover:scale-105"
                            />
                            {sighting.weather_code ? (
                              <span className="absolute right-1 top-1 rounded bg-black/60 px-1 text-[10px]">
                                {weatherEmoji(sighting.weather_code)}
                              </span>
                            ) : null}
                          </div>
                          <figcaption className="truncate px-1.5 py-1 text-[9px] text-[var(--color-text-muted)]">
                            {formatDateTime(sighting.detected_at)}
                          </figcaption>
                        </figure>
                      );
                    })}
                  </div>
                ) : (
                  <p className="flex items-center gap-2 rounded-xl border border-dashed border-dark-700 px-4 py-6 text-xs text-[var(--color-text-muted)]">
                    <Moon className="h-4 w-4" />
                    Nenhuma avistagem associada a esta espécie ainda.
                  </p>
                )}
              </div>
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}

/** Bloco compacto de estatística (rótulo + valor). */
function StatTile({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
        {icon}
        {label}
      </p>
      <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-[var(--color-text-primary)]">
        {value}
      </p>
    </div>
  );
}
