import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import {
  Clock,
  Crosshair,
  Frame,
  Globe2,
  LayoutGrid,
  Moon,
  Plus,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";
import type { Camera, CameraWeather } from "@/types";
import { getCameraWeather } from "@/services/api";
import { StatusDot } from "@/components/common/StatusDot";
import { statusLabel } from "@/utils/format";
import { CameraControlToolbar } from "@/components/dashboard/CameraControlToolbar";
import { cn } from "@/utils/cn";

// O mapa-múndi (Natural Earth embutido) fica em um chunk separado: a grade de
// câmeras abre instantaneamente e o Radar Global só é baixado ao ser aberto.
const GardenRadarMap = lazy(() =>
  import("@/components/cameras/GardenRadarMap").then((module) => ({
    default: module.GardenRadarMap,
  })),
);

type Props = {
  cameras: Camera[];
  loading?: boolean;
  onAdd: () => void;
  onToggle: (camera: Camera, enabled: boolean) => void;
  onDelete: (camera: Camera) => void;
  onEditZones: (camera: Camera) => void;
  onEditRoi: (camera: Camera) => void;
  onCameraUpdated?: (camera: Camera) => void;
};

export function CameraGrid({
  cameras,
  loading,
  onAdd,
  onToggle,
  onDelete,
  onEditZones,
  onEditRoi,
  onCameraUpdated,
}: Props) {
  const [view, setView] = useState<"grid" | "radar">("grid");

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
            Câmeras
          </h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            Fontes USB, RTSP, HLS, HTTP e WebRTC · credenciais criptografadas
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div
            role="tablist"
            aria-label="Visualização da central de câmeras"
            className="inline-flex gap-1 rounded-lg border border-dark-700 bg-dark-800 p-1"
          >
            <button
              type="button"
              role="tab"
              aria-selected={view === "grid"}
              onClick={() => setView("grid")}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition",
                view === "grid"
                  ? "bg-emerald-500/15 text-emerald-300"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
              )}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              Grade
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "radar"}
              onClick={() => setView("radar")}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition",
                view === "radar"
                  ? "bg-sky-500/15 text-sky-300"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
              )}
            >
              <Globe2 className="h-3.5 w-3.5" />
              Radar Global
            </button>
          </div>
          <button
            type="button"
            onClick={onAdd}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400"
          >
            <Plus className="h-4 w-4" />
            Adicionar câmera externa
          </button>
        </div>
      </div>

      {view === "radar" ? (
        <Suspense
          fallback={
            <div className="flex min-h-[320px] items-center justify-center rounded-2xl border border-dark-700 bg-dark-800">
              <p className="text-sm text-[var(--color-text-muted)]">
                Carregando Radar Global…
              </p>
            </div>
          }
        >
          <GardenRadarMap />
        </Suspense>
      ) : loading && cameras.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">Carregando câmeras…</p>
      ) : cameras.length === 0 ? (
        <div className="rounded-xl border border-dashed border-dark-700 bg-dark-800 px-6 py-12 text-center">
          <WifiOff className="mx-auto h-8 w-8 text-[var(--color-text-muted)]" />
          <p className="mt-3 text-sm text-[var(--color-text-muted)]">
            Nenhuma câmera cadastrada. Adicione uma webcam ou stream RTSP.
          </p>
          <button
            type="button"
            onClick={onAdd}
            className="mt-4 text-sm font-medium text-emerald-400 hover:text-emerald-500"
          >
            Adicionar a primeira câmera
          </button>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {cameras.map((camera) => {
            const online = camera.status === "online";
            return (
              <article
                key={camera.id}
                className="rounded-xl border border-dark-700 bg-dark-800 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <StatusDot status={String(camera.status)} />
                      <h3 className="truncate font-display text-base font-semibold text-[var(--color-text-primary)]">
                        {camera.name}
                      </h3>
                    </div>
                    <p className="mt-1 text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
                      {camera.source_type} · {statusLabel(String(camera.status))}
                      {camera.location_label ? ` · ${camera.location_label}` : ""}
                    </p>
                  </div>
                  {online ? (
                    <Wifi className="h-4 w-4 shrink-0 text-emerald-400" />
                  ) : (
                    <WifiOff className="h-4 w-4 shrink-0 text-[var(--color-text-muted)]" />
                  )}
                </div>

                <p className="mt-3 truncate rounded-lg bg-dark-900 px-2 py-1.5 font-mono text-[11px] text-[var(--color-text-muted)]">
                  {camera.stream_url}
                </p>

                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                  <Badge tone={camera.is_active ? "ok" : "muted"}>
                    {camera.is_active ? "Ativa" : "Desativada"}
                  </Badge>
                  <Badge tone={camera.ai_enabled !== false ? "ok" : "muted"}>
                    {camera.ai_enabled !== false ? "Bem-Te-Vi Core Ativo" : "Bem-Te-Vi Core Pausado"}
                  </Badge>
                  {camera.audio_enabled ? (
                    <Badge tone="ok">BirdNET Ativo</Badge>
                  ) : null}
                  {camera.has_credentials ? (
                    <Badge tone="ok">Credenciais OK</Badge>
                  ) : (
                    <Badge tone="muted">Sem credenciais</Badge>
                  )}
                  <Badge tone="muted">{camera.zones.length} zona(s)</Badge>
                  {camera.night_mode ? (
                    <Badge tone="night">
                      <Moon className="mr-1 inline h-3 w-3" />
                      Visão noturna
                    </Badge>
                  ) : null}
                </div>

                {/* Clima e horário locais do jardim (câmeras globais/remotas). */}
                <CameraLocalWeather camera={camera} />

                {/* Barra de Controles Operacionais em Tempo Real */}
                <div className="mt-3">
                  <CameraControlToolbar
                    camera={camera}
                    onCameraUpdated={onCameraUpdated}
                  />
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-dark-700 pt-3">
                  <label className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                    <input
                      type="checkbox"
                      checked={camera.is_active}
                      onChange={(e) => onToggle(camera, e.target.checked)}
                      className="accent-emerald-500"
                    />
                    Ativa
                  </label>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => onEditRoi(camera)}
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-sky-300 transition hover:bg-sky-500/10"
                    >
                      <Frame className="h-3.5 w-3.5" />
                      Zonas ROI
                    </button>
                    <button
                      type="button"
                      onClick={() => onEditZones(camera)}
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-emerald-300 transition hover:bg-emerald-500/10"
                    >
                      <Crosshair className="h-3.5 w-3.5" />
                      Editar área
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(camera)}
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-red-300 transition hover:bg-red-500/10"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Remover
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Badge({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "ok" | "muted" | "night";
}) {
  return (
    <span
      className={cn(
        "rounded-md px-2 py-0.5",
        tone === "ok" && "bg-emerald-500/15 text-emerald-400",
        tone === "muted" && "bg-dark-700 text-[var(--color-text-muted)]",
        tone === "night" && "bg-indigo-500/15 text-indigo-300",
      )}
    >
      {children}
    </span>
  );
}

/**
 * Faixa de clima/horário **locais** do jardim de uma câmera remota.
 *
 * Só aparece quando a câmera tem coordenadas cadastradas. Busca o clima da
 * Open-Meteo (temperatura, condição e a hora local exata) — se a câmera ainda
 * não tiver clima disponível (offline), mostra apenas a localidade e o fuso.
 */
function CameraLocalWeather({ camera }: { camera: Camera }) {
  const [weather, setWeather] = useState<CameraWeather | null>(null);
  const temCoordenadas =
    camera.latitude != null && camera.longitude != null;

  useEffect(() => {
    if (!temCoordenadas) return;
    let ativo = true;
    void (async () => {
      try {
        const dados = await getCameraWeather(camera.id);
        if (ativo) setWeather(dados);
      } catch {
        // Silencioso: o widget apenas não exibe o clima (a câmera segue normal).
      }
    })();
    return () => {
      ativo = false;
    };
  }, [camera.id, camera.latitude, camera.longitude, temCoordenadas]);

  if (!temCoordenadas) return null;

  if (!weather || !weather.available) {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-lg border border-dark-700 bg-dark-900 px-2.5 py-1.5 text-[11px] text-[var(--color-text-muted)]">
        <Globe2 className="h-3.5 w-3.5 shrink-0 text-sky-400" />
        <span className="min-w-0 truncate">
          {camera.location_label || camera.country || "Local remoto"}
        </span>
        {camera.timezone ? (
          <span className="ml-auto shrink-0 font-mono text-[10px]">
            {camera.timezone}
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-sky-500/20 bg-sky-500/5 px-2.5 py-1.5 text-[11px] text-sky-100">
      <span className="inline-flex items-center gap-1 font-medium">
        <span className="text-sm leading-none">
          {weather.is_day === false ? "🌙" : weather.icon}
        </span>
        {weather.temperature != null
          ? `${Math.round(weather.temperature)}°C`
          : "—"}
      </span>
      <span className="min-w-0 truncate">{weather.condition}</span>
      {weather.local_time_label ? (
        <span className="inline-flex items-center gap-1 font-mono">
          <Clock className="h-3 w-3" />
          {weather.local_time_label} local
        </span>
      ) : null}
      {camera.timezone ? (
        <span className="ml-auto shrink-0 font-mono text-[10px] text-sky-300/80">
          {camera.timezone}
        </span>
      ) : null}
    </div>
  );
}
