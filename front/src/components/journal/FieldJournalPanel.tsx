import { useCallback, useEffect, useState } from "react";
import {
  Bird,
  CalendarDays,
  CloudSun,
  Download,
  Droplets,
  FileText,
  Film,
  LoaderCircle,
  MapPin,
  RefreshCw,
  Sparkles,
  Thermometer,
  Wind,
} from "lucide-react";

import type { Camera, FieldJournal, FieldJournalSpecies } from "@/types";
import {
  fetchFieldJournal,
  fieldJournalCsvUrl,
  fieldJournalEbirdUrl,
  getErrorMessage,
} from "@/services/api";
import { formatPercent } from "@/utils/format";
import { cn } from "@/utils/cn";

type Props = {
  /** Câmeras cadastradas, usadas no filtro por jardim. */
  cameras: Camera[];
};

function todayLocal(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function WeatherChip({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-dark-600 bg-dark-900/70 px-2.5 py-1 text-[11px] text-[var(--color-text-muted)]">
      {icon}
      {children}
    </span>
  );
}

function SpeciesCard({ item }: { item: FieldJournalSpecies }) {
  const cover =
    item.media.find((media) => media.kind === "photo")?.url ??
    item.sightings.find((sighting) => sighting.thumbnail_url)?.thumbnail_url ??
    null;

  return (
    <article className="overflow-hidden rounded-2xl border border-dark-700 bg-dark-800/80 shadow-[0_10px_40px_-28px_rgba(16,185,129,0.55)]">
      <div className="relative h-36 bg-dark-900">
        {cover ? (
          <img
            src={cover}
            alt={`Registro de ${item.species}`}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[var(--color-text-muted)]">
            <Bird className="h-10 w-10 opacity-40" />
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-dark-950/95 via-dark-950/40 to-transparent px-3 pb-2 pt-8">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">
              {item.species}
            </p>
            <p className="truncate text-[10px] italic text-slate-300">
              {item.scientific_name || "Nome científico não identificado"}
            </p>
          </div>
          <span className="shrink-0 rounded-full border border-emerald-400/30 bg-emerald-400/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-100">
            {item.count} ind.
          </span>
        </div>
      </div>

      <div className="space-y-2.5 p-3">
        <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
          <span className="rounded-full border border-dark-600 bg-dark-900 px-2 py-0.5 text-[var(--color-text-muted)]">
            {item.first_time_label}
            {item.last_time_label !== item.first_time_label
              ? `–${item.last_time_label}`
              : ""}
          </span>
          <span className="rounded-full border border-sky-400/20 bg-sky-400/10 px-2 py-0.5 text-sky-200">
            {formatPercent(item.max_confidence)} confiança
          </span>
          {item.ecological_label ? (
            <span className="rounded-full border border-amber-400/20 bg-amber-400/10 px-2 py-0.5 text-amber-200">
              {item.ecological_label}
            </span>
          ) : null}
        </div>

        {item.behavior_summary ? (
          <p className="flex items-start gap-1.5 text-xs text-[var(--color-text-muted)]">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300" />
            {item.behavior_summary}
          </p>
        ) : null}

        <p className="text-[11px] text-[var(--color-text-muted)]">
          {item.visits} registro(s) no dia
        </p>

        {item.media.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {item.media.slice(0, 5).map((media) =>
              media.kind === "clip" ? (
                <a
                  key={media.url}
                  href={media.url}
                  target="_blank"
                  rel="noreferrer"
                  title={media.label ?? "Abrir clipe"}
                  className="inline-flex items-center gap-1 rounded-md border border-violet-400/25 bg-violet-400/10 px-2 py-1 text-[10px] text-violet-200 transition hover:bg-violet-400/20"
                >
                  <Film className="h-3 w-3" />
                  Clipe
                </a>
              ) : (
                <a
                  key={media.url}
                  href={media.url}
                  target="_blank"
                  rel="noreferrer"
                  title={media.label ?? "Abrir foto"}
                  className="h-10 w-10 overflow-hidden rounded-md border border-dark-600 bg-dark-900 transition hover:border-emerald-400/40"
                >
                  <img
                    src={media.url}
                    alt={media.label ?? item.species}
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                </a>
              ),
            )}
          </div>
        ) : null}
      </div>
    </article>
  );
}

/**
 * Aba **Diário de Campo**.
 *
 * Compila o relatório do dia (clima Open-Meteo, coordenadas do jardim, fotos e
 * clipes) e oferece os dois downloads pedidos por biólogos e observadores:
 * o checklist no padrão **eBird** e uma planilha CSV limpa em pt-BR.
 */
export function FieldJournalPanel({ cameras }: Props) {
  const [day, setDay] = useState(todayLocal);
  const [cameraId, setCameraId] = useState("");
  const [report, setReport] = useState<FieldJournal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchFieldJournal(day, cameraId || undefined);
      setReport(data);
    } catch (cause) {
      setError(
        getErrorMessage(cause, "Não foi possível carregar o Diário de Campo."),
      );
    } finally {
      setLoading(false);
    }
  }, [day, cameraId]);

  useEffect(() => {
    void load();
  }, [load]);

  const ebirdUrl = fieldJournalEbirdUrl(day, cameraId || undefined);
  const csvUrl = fieldJournalCsvUrl(day, cameraId || undefined);

  return (
    <section className="space-y-4">
      {/* Cabeçalho e controles do relatório */}
      <div className="rounded-2xl border border-dark-700 bg-dark-800/80 p-4 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="rounded-xl bg-emerald-500/15 p-2.5 text-emerald-300">
              <CalendarDays className="h-5 w-5" />
            </span>
            <div>
              <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
                Diário de Campo
              </h2>
              <p className="text-xs text-[var(--color-text-muted)]">
                Relatório geolocalizado do dia · exportação para eBird e CSV
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              Data
              <input
                type="date"
                value={day}
                onChange={(event) => setDay(event.target.value || todayLocal())}
                className="rounded-lg border border-dark-700 bg-dark-900 px-2.5 py-1.5 text-xs text-[var(--color-text-primary)]"
              />
            </label>
            <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
              Jardim
              <select
                value={cameraId}
                onChange={(event) => setCameraId(event.target.value)}
                className="min-w-40 rounded-lg border border-dark-700 bg-dark-900 px-2.5 py-1.5 text-xs text-[var(--color-text-primary)]"
              >
                <option value="">Todos os jardins</option>
                {cameras.map((camera) => (
                  <option key={camera.id} value={camera.id}>
                    {camera.location_label || camera.name || "Jardim sem nome"}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-dark-600 px-3 py-2 text-xs font-medium text-[var(--color-text-muted)] transition hover:border-emerald-400/40 hover:text-emerald-200 disabled:opacity-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              Atualizar
            </button>
          </div>
        </div>

        {/* Exportações: eBird (ciência cidadã) e CSV limpo */}
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-dark-700 pt-3">
          <a
            href={ebirdUrl}
            download
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/35 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/20"
          >
            <Download className="h-3.5 w-3.5" />
            Exportar checklist eBird
          </a>
          <a
            href={csvUrl}
            download
            className="inline-flex items-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-xs font-medium text-sky-200 transition hover:bg-sky-500/20"
          >
            <FileText className="h-3.5 w-3.5" />
            Baixar CSV limpo
          </a>
          <p className="text-[10px] text-[var(--color-text-muted)]">
            eBird Record Format: CSV sem cabeçalho, data mês/dia/ano. Importe em{" "}
            <em>Submit → Import Data → Record Format</em>.
          </p>
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300"
        >
          {error}
        </p>
      ) : null}

      {loading && !report ? (
        <p className="flex items-center gap-2 rounded-xl border border-dark-700 bg-dark-800 p-6 text-sm text-[var(--color-text-muted)]">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Compilando o diário do dia…
        </p>
      ) : report ? (
        <>
          {/* Resumo do dia */}
          <div className="rounded-2xl border border-dark-700 bg-dark-800/80 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
                  {report.title}
                </h3>
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                  {report.subtitle}
                </p>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-400/25 bg-sky-400/10 px-3 py-1 text-xs text-sky-100">
                <CloudSun className="h-4 w-4" />
                {report.weather.summary}
              </span>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <WeatherChip icon={<Bird className="h-3.5 w-3.5" />}>
                {report.summary.total_visits} visita(s)
              </WeatherChip>
              <WeatherChip icon={<Sparkles className="h-3.5 w-3.5" />}>
                {report.summary.total_species} espécie(s)
              </WeatherChip>
              <WeatherChip icon={<MapPin className="h-3.5 w-3.5" />}>
                {report.summary.total_gardens} jardim(ns)
              </WeatherChip>
              {report.summary.first_observation_at ? (
                <WeatherChip icon={<CalendarDays className="h-3.5 w-3.5" />}>
                  {report.summary.first_time_label}–{report.summary.last_time_label}
                </WeatherChip>
              ) : null}
              {report.weather.temperature != null ? (
                <WeatherChip icon={<Thermometer className="h-3.5 w-3.5" />}>
                  {report.weather.temperature.toFixed(1)} °C
                </WeatherChip>
              ) : null}
              {report.weather.humidity != null ? (
                <WeatherChip icon={<Droplets className="h-3.5 w-3.5" />}>
                  {report.weather.humidity.toFixed(0)}% UR
                </WeatherChip>
              ) : null}
              {report.weather.wind_speed != null ? (
                <WeatherChip icon={<Wind className="h-3.5 w-3.5" />}>
                  {report.weather.wind_speed.toFixed(1)} km/h
                </WeatherChip>
              ) : null}
            </div>

            {report.gardens.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-dark-700 pt-3">
                {report.gardens.map((garden) => (
                  <span
                    key={garden.camera_id}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-dark-600 bg-dark-900/60 px-2.5 py-1.5 text-[11px] text-[var(--color-text-muted)]"
                    title={garden.weather.summary}
                  >
                    <MapPin className="h-3 w-3 text-emerald-300" />
                    <span className="text-[var(--color-text-primary)]">
                      {garden.name}
                    </span>
                    {garden.coordinates_label ? (
                      <code className="text-[10px] text-[var(--color-text-muted)]">
                        {garden.coordinates_label}
                      </code>
                    ) : null}
                  </span>
                ))}
              </div>
            ) : null}
          </div>

          {/* Espécies do dia */}
          {report.species.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-dark-700 bg-dark-800/60 px-4 py-10 text-center">
              <Bird className="mx-auto h-8 w-8 text-[var(--color-text-muted)] opacity-50" />
              <p className="mt-2 text-sm font-medium text-[var(--color-text-primary)]">
                Nenhuma ave registrada neste dia
              </p>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Escolha outra data ou deixe o Alaris Core capturar as visitas do jardim.
              </p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {report.species.map((item) => (
                <SpeciesCard
                  key={`${item.species}-${item.scientific_name ?? ""}`}
                  item={item}
                />
              ))}
            </div>
          )}

          {/* Texto do diário, útil para imprimir ou copiar */}
          <details className="rounded-2xl border border-dark-700 bg-dark-800/80 p-4">
            <summary className="cursor-pointer text-sm font-semibold text-[var(--color-text-primary)]">
              Ler o diário completo em texto
            </summary>
            <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border border-dark-700 bg-dark-950/70 p-3 font-mono text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              {report.journal_text}
            </pre>
          </details>
        </>
      ) : null}
    </section>
  );
}
