import { useEffect, useMemo, useState } from "react";
import {
  AudioLines,
  Bird,
  CloudSun,
  Globe2,
  MapPin,
  Radio,
  RefreshCw,
  Video,
  WifiOff,
} from "lucide-react";
import type { GardenRadarGarden } from "@/types";
import {
  cameraAudioUrl,
  fetchGardenRadar,
  getErrorMessage,
  videoFeedUrl,
} from "@/services/api";
import { usePolling } from "@/hooks/usePolling";
import { formatSpeciesLabel } from "@/utils/format";
import { cn } from "@/utils/cn";
import { WORLD_LAND_PATH } from "@/components/cameras/worldMapPath";

const MAP_W = 1000;
const MAP_H = 500;

function project(latitude: number, longitude: number) {
  const x = ((longitude + 180) / 360) * MAP_W;
  const y = ((90 - latitude) / 180) * MAP_H;
  return {
    x: Math.max(2, Math.min(MAP_W - 2, x)),
    y: Math.max(2, Math.min(MAP_H - 2, y)),
  };
}

function statusTone(status: string) {
  if (status === "online") return "text-emerald-400";
  if (status === "error" || status === "disabled") return "text-red-400";
  if (status === "connecting" || status === "reconnecting") return "text-amber-300";
  return "text-slate-400";
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    online: "Ao vivo",
    idle: "Ociosa",
    connecting: "Conectando",
    reconnecting: "Reconectando",
    error: "Com erro",
    stopped: "Parada",
    disabled: "Desativada",
  };
  return labels[status] ?? status;
}

/**
 * Radar Global Interativo de Jardins.
 *
 * Mapa-múndi minimalista desenhado em SVG (Natural Earth 1:110m embutido no
 * bundle — funciona offline, sem tiles externos). Cada jardim com coordenadas
 * vira um marcador pulsante; ao clicar, o painel abaixo exibe o clima local, o
 * vídeo ao vivo, o áudio (quando habilitado), as estatísticas de hoje e as
 * espécies daquele jardim.
 */
export function GardenRadarMap() {
  const query = usePolling(fetchGardenRadar, 60_000, true);
  const gardens = query.data?.gardens ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [videoFailed, setVideoFailed] = useState(false);
  const [audioOn, setAudioOn] = useState(false);

  useEffect(() => {
    if (!gardens.length) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !gardens.some((item) => item.camera_id === selectedId)) {
      // Prioriza um jardim online; senão, o primeiro da lista.
      const online = gardens.find((item) => item.status === "online");
      setSelectedId((online ?? gardens[0]).camera_id);
    }
  }, [gardens, selectedId]);

  const selected = useMemo(
    () => gardens.find((item) => item.camera_id === selectedId) ?? null,
    [gardens, selectedId],
  );

  useEffect(() => {
    setVideoFailed(false);
    setAudioOn(false);
  }, [selectedId]);

  const ordered = useMemo(
    () =>
      [...gardens].sort((a, b) => {
        if (a.camera_id === selectedId) return 1;
        if (b.camera_id === selectedId) return -1;
        return a.garden.localeCompare(b.garden, "pt-BR");
      }),
    [gardens, selectedId],
  );

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/10 text-sky-300">
            <Globe2 className="h-5 w-5" />
          </span>
          <div>
            <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
              Radar Global de Jardins
            </h2>
            <p className="text-sm text-[var(--color-text-muted)]">
              Clique em um marcador para abrir o clima, o vídeo e as espécies
              daquele jardim.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void query.refresh()}
          disabled={query.loading}
          className="inline-flex items-center gap-2 rounded-lg border border-dark-700 px-3 py-2 text-xs font-medium text-[var(--color-text-muted)] transition hover:border-sky-400/40 hover:text-sky-300 disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", query.loading && "animate-spin")} />
          Atualizar radar
        </button>
      </div>

      {query.error && !query.data ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {getErrorMessage(query.error, "Não foi possível carregar o Radar Global.")}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        {/* ——— Mapa ——— */}
        <div className="relative overflow-hidden rounded-2xl border border-dark-700 bg-[#07110d]">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_20%,rgba(16,185,129,0.10),transparent_60%)]" />
          <svg
            viewBox={`0 0 ${MAP_W} ${MAP_H}`}
            role="img"
            aria-label="Mapa-múndi com os jardins monitorados"
            className="relative block h-auto w-full"
          >
            <defs>
              <pattern
                id="radar-grid"
                width="50"
                height="50"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M 50 0 L 0 0 0 50"
                  fill="none"
                  stroke="#163027"
                  strokeWidth="0.6"
                />
              </pattern>
              <radialGradient id="radar-ocean" cx="50%" cy="15%" r="90%">
                <stop offset="0%" stopColor="#0b1a14" />
                <stop offset="100%" stopColor="#050c09" />
              </radialGradient>
              <filter
                id="radar-glow"
                x="-200%"
                y="-200%"
                width="400%"
                height="400%"
              >
                <feGaussianBlur stdDeviation="3.2" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <rect width={MAP_W} height={MAP_H} fill="url(#radar-ocean)" />
            <rect width={MAP_W} height={MAP_H} fill="url(#radar-grid)" opacity="0.55" />
            {/* Linha do Equador */}
            <line
              x1="0"
              y1={MAP_H / 2}
              x2={MAP_W}
              y2={MAP_H / 2}
              stroke="#1c3a2f"
              strokeWidth="0.8"
              strokeDasharray="4 6"
              opacity="0.7"
            />
            <path
              d={WORLD_LAND_PATH}
              fill="#12241d"
              stroke="#25453a"
              strokeWidth="0.65"
              strokeLinejoin="round"
            />

            {ordered.map((garden, index) => {
              const { x, y } = project(garden.latitude, garden.longitude);
              const active = garden.camera_id === selectedId;
              const hovered = garden.camera_id === hoveredId;
              const online = garden.status === "online";
              const color = online
                ? "#34d399"
                : garden.status === "error"
                  ? "#f87171"
                  : "#94a3b8";
              return (
                <g
                  key={garden.camera_id}
                  role="button"
                  tabIndex={0}
                  aria-label={`Abrir jardim ${garden.garden}`}
                  onClick={() => setSelectedId(garden.camera_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedId(garden.camera_id);
                    }
                  }}
                  onMouseEnter={() => setHoveredId(garden.camera_id)}
                  onMouseLeave={() => setHoveredId(null)}
                  className="cursor-pointer outline-none"
                >
                  <title>
                    {garden.garden}
                    {garden.country ? ` · ${garden.country}` : ""} —{" "}
                    {garden.visits_today} visita(s) hoje
                  </title>
                  <circle
                    cx={x}
                    cy={y}
                    r="18"
                    fill="transparent"
                    stroke={active ? "rgba(52,211,153,0.45)" : "transparent"}
                    strokeWidth="1"
                  />
                  {online ? (
                    <circle cx={x} cy={y} r="5" fill="none" stroke={color} strokeWidth="1.4">
                      <animate
                        attributeName="r"
                        values="5;17"
                        dur="2.6s"
                        begin={`${(index % 5) * 0.35}s`}
                        repeatCount="indefinite"
                      />
                      <animate
                        attributeName="opacity"
                        values="0.85;0"
                        dur="2.6s"
                        begin={`${(index % 5) * 0.35}s`}
                        repeatCount="indefinite"
                      />
                    </circle>
                  ) : null}
                  <circle
                    cx={x}
                    cy={y}
                    r={active || hovered ? 6 : 4.4}
                    fill={color}
                    stroke="#04110c"
                    strokeWidth="1.6"
                    filter="url(#radar-glow)"
                  />
                  {garden.weather?.available ? (
                    <text
                      x={x + 9}
                      y={y + 3.5}
                      fontSize="9"
                      fill="#c8d8d1"
                      className="pointer-events-none select-none"
                      opacity={active || hovered ? 1 : 0.0}
                    >
                      {Math.round(garden.weather.temperature ?? 0)}°C
                    </text>
                  ) : null}
                  <text
                    x={x}
                    y={y - 11}
                    textAnchor="middle"
                    fontSize="10"
                    fontWeight="600"
                    fill="#e8f5ef"
                    className="pointer-events-none select-none"
                    opacity={active || hovered ? 1 : 0}
                    style={{ paintOrder: "stroke", stroke: "#04110c", strokeWidth: 3 }}
                  >
                    {garden.garden.length > 22
                      ? `${garden.garden.slice(0, 21)}…`
                      : garden.garden}
                  </text>
                </g>
              );
            })}
          </svg>

          <div className="absolute left-3 top-3 flex items-center gap-2 rounded-full border border-emerald-400/20 bg-black/40 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-emerald-300 backdrop-blur">
            <Radio className="h-3 w-3 animate-pulse" />
            Radar Bem-Te-Vi Core
          </div>
          <div className="absolute bottom-3 left-3 flex flex-wrap items-center gap-3 rounded-lg border border-dark-700/80 bg-black/45 px-3 py-1.5 text-[10px] text-[var(--color-text-muted)] backdrop-blur">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              {gardens.filter((item) => item.status === "online").length} online
            </span>
            <span className="inline-flex items-center gap-1.5">
              <MapPin className="h-3 w-3" />
              {gardens.length} jardim(ns)
            </span>
            {query.data && query.data.without_location > 0 ? (
              <span className="text-amber-300/80">
                {query.data.without_location} sem localização
              </span>
            ) : null}
          </div>
        </div>

        {/* ——— Detalhe do jardim selecionado ——— */}
        <div className="rounded-2xl border border-dark-700 bg-dark-800 p-4">
          {query.loading && !query.data ? (
            <div className="space-y-3">
              <div className="aspect-video animate-pulse rounded-xl bg-dark-700" />
              <div className="h-4 w-2/3 animate-pulse rounded bg-dark-700" />
              <div className="h-4 w-1/2 animate-pulse rounded bg-dark-700" />
            </div>
          ) : selected ? (
            <GardenDetail
              garden={selected}
              videoFailed={videoFailed}
              onVideoError={() => setVideoFailed(true)}
              audioOn={audioOn}
              onToggleAudio={() => setAudioOn((current) => !current)}
            />
          ) : (
            <div className="flex h-full min-h-[260px] flex-col items-center justify-center text-center">
              <WifiOff className="h-7 w-7 text-[var(--color-text-muted)]" />
              <p className="mt-3 text-sm text-[var(--color-text-muted)]">
                Nenhum jardim com localização cadastrada. Informe latitude e
                longitude ao adicionar uma câmera para vê-la no radar.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function GardenDetail({
  garden,
  videoFailed,
  onVideoError,
  audioOn,
  onToggleAudio,
}: {
  garden: GardenRadarGarden;
  videoFailed: boolean;
  onVideoError: () => void;
  audioOn: boolean;
  onToggleAudio: () => void;
}) {
  const weather = garden.weather;
  const maxSpecies = Math.max(
    1,
    ...garden.top_species.map((item) => item.visits),
  );
  const live = garden.is_active && !videoFailed;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
            {garden.country || "Jardim remoto"}
          </p>
          <h3 className="truncate font-display text-base font-semibold text-[var(--color-text-primary)]">
            {garden.garden}
          </h3>
          <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
            <span className={cn("h-1.5 w-1.5 rounded-full bg-current", statusTone(garden.status))} />
            {statusLabel(garden.status)}
            {garden.timezone ? ` · ${garden.timezone}` : ""}
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-md border border-dark-600 bg-dark-900/60 px-2 py-1 text-[11px] text-[var(--color-text-muted)]">
          <MapPin className="h-3 w-3 text-sky-300" />
          {garden.latitude.toFixed(1)}, {garden.longitude.toFixed(1)}
        </span>
      </div>

      {/* Player ao vivo */}
      <div className="relative overflow-hidden rounded-xl border border-dark-700 bg-black">
        <div className="aspect-video">
          {live ? (
            <img
              key={garden.camera_id}
              src={videoFeedUrl(garden.camera_id)}
              alt={`Transmissão ao vivo de ${garden.garden}`}
              className="h-full w-full object-cover"
              onError={onVideoError}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <Video className="h-7 w-7 text-[var(--color-text-muted)]" />
              <p className="px-4 text-xs text-[var(--color-text-muted)]">
                {videoFailed
                  ? "Não foi possível abrir o vídeo agora."
                  : "Câmera desativada neste jardim."}
              </p>
            </div>
          )}
        </div>
        <span className="absolute left-2 top-2 inline-flex items-center gap-1.5 rounded-md bg-black/60 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-300 backdrop-blur">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
          {live ? "Ao vivo" : "Offline"}
        </span>
        {garden.audio_enabled ? (
          <button
            type="button"
            onClick={onToggleAudio}
            className={cn(
              "absolute bottom-2 right-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-semibold backdrop-blur transition",
              audioOn
                ? "bg-emerald-500/85 text-dark-900"
                : "bg-black/60 text-emerald-200 hover:bg-black/80",
            )}
          >
            <AudioLines className="h-3.5 w-3.5" />
            {audioOn ? "Ouvindo" : "Ouvir áudio"}
          </button>
        ) : null}
        {audioOn ? (
          <audio
            key={garden.camera_id}
            src={cameraAudioUrl(garden.camera_id)}
            autoPlay
            controls
            className="absolute inset-x-2 bottom-10 h-8 w-[calc(100%-1rem)]"
          />
        ) : null}
      </div>

      {/* Clima local */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-sky-500/20 bg-sky-500/5 px-3 py-2 text-xs text-sky-100">
        <span className="inline-flex items-center gap-1.5 font-semibold">
          <CloudSun className="h-3.5 w-3.5" />
          {weather.available
            ? `${weather.is_day === false ? "🌙" : weather.icon} ${
                weather.temperature != null
                  ? `${Math.round(weather.temperature)}°C`
                  : "—"
              }`
            : "Clima indisponível"}
        </span>
        {weather.available ? (
          <>
            <span className="min-w-0 truncate">{weather.condition}</span>
            {weather.local_time_label ? (
              <span className="font-mono text-[11px] text-sky-300/90">
                {weather.local_time_label} local
              </span>
            ) : null}
            {weather.humidity != null ? (
              <span className="text-sky-300/80">
                {Math.round(weather.humidity)}% umidade
              </span>
            ) : null}
          </>
        ) : null}
      </div>

      {/* Estatísticas de hoje */}
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Hoje" value={garden.visits_today} />
        <Stat label="Espécies" value={garden.species_today} />
        <Stat label="No total" value={garden.total_visits} />
      </div>

      {/* Espécies do jardim */}
      <div>
        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-primary)]">
          <Bird className="h-3.5 w-3.5 text-emerald-400" />
          Espécies de hoje
        </p>
        {garden.top_species.length ? (
          <ul className="space-y-1.5">
            {garden.top_species.map((item) => (
              <li key={item.species} className="text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[var(--color-text-primary)]">
                    {formatSpeciesLabel(item.species)}
                  </span>
                  <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                    {item.visits}
                  </span>
                </div>
                <div className="mt-1 h-1 overflow-hidden rounded-full bg-dark-700">
                  <div
                    className="h-full rounded-full bg-emerald-400/80"
                    style={{ width: `${(item.visits / maxSpecies) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-lg border border-dashed border-dark-600 px-3 py-3 text-center text-[11px] text-[var(--color-text-muted)]">
            Nenhuma ave registrada hoje neste jardim.
          </p>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-dark-700 bg-dark-900/60 px-2.5 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
        {label}
      </p>
      <p className="mt-0.5 font-display text-lg font-semibold text-[var(--color-text-primary)]">
        {new Intl.NumberFormat("pt-BR").format(value)}
      </p>
    </div>
  );
}
