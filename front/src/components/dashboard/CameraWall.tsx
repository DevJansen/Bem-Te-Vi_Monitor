import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bird,
  Grid2x2,
  LayoutGrid,
  Maximize2,
  Square,
  Wifi,
  WifiOff,
  Zap,
} from "lucide-react";
import type { Camera, StreamStats } from "@/types";
import { fetchStreams, streamProxyUrl } from "@/services/api";
import { cn } from "@/utils/cn";
import { abortMjpegStream } from "@/utils/stream";

type GridMode = 1 | 2 | 4;

const MODES: Array<{ value: GridMode; label: string; icon: typeof Square }> = [
  { value: 1, label: "Foco", icon: Square },
  { value: 2, label: "2 câmeras", icon: Grid2x2 },
  { value: 4, label: "4 câmeras", icon: LayoutGrid },
];

/**
 * "Mural de Câmeras" — grid multi-câmera em tempo real (1, 2 ou 4 lado a lado).
 *
 * Cada feed usa o **proxy seguro** do backend (`/api/streams/proxy/{id}`), então
 * a URL e as credenciais da câmera externa nunca chegam ao navegador. Sobre cada
 * vídeo exibimos os selos em tempo real do **Alaris Core**: status de conexão
 * (Online 🟢 / Reconectando 🟡), FPS e a contagem de aves ativas no
 * bebedouro/comedouro.
 */
export function CameraWall({ cameras }: { cameras: Camera[] }) {
  const ativas = useMemo(() => cameras.filter((c) => c.is_active), [cameras]);
  const [mode, setMode] = useState<GridMode>(4);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [stats, setStats] = useState<Record<string, StreamStats>>({});

  // Polling do estado em tempo real do Alaris Core por stream.
  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const lista = await fetchStreams();
        if (!active) return;
        setStats(Object.fromEntries(lista.map((s) => [s.camera_id, s])));
      } catch {
        /* silencioso: mantém o último estado conhecido */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 3_000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  const visiveis = useMemo(() => {
    if (focusedId) {
      const alvo = ativas.find((c) => c.id === focusedId);
      return alvo ? [alvo] : ativas.slice(0, mode);
    }
    return ativas.slice(0, mode);
  }, [ativas, focusedId, mode]);

  const colunas =
    focusedId || mode === 1
      ? "grid-cols-1"
      : mode === 2
        ? "grid-cols-1 md:grid-cols-2"
        : "grid-cols-1 md:grid-cols-2";

  if (ativas.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-dark-700 bg-dark-800 px-6 py-10 text-center">
        <WifiOff className="mx-auto h-8 w-8 text-[var(--color-text-muted)]" />
        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
          Nenhuma câmera ativa. Ative uma câmera na Central de Câmeras para ver o
          mural ao vivo.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-[var(--color-text-primary)]">
            <LayoutGrid className="h-4 w-4 text-emerald-400" />
            Mural de Câmeras
          </h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            Alaris Core ativo e independente em cada fluxo
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-dark-700 bg-dark-800 p-1">
          {MODES.map((m) => {
            const Icon = m.icon;
            const selectedMode = !focusedId && mode === m.value;
            return (
              <button
                key={m.value}
                type="button"
                title={m.label}
                aria-pressed={selectedMode}
                onClick={() => {
                  setFocusedId(null);
                  setMode(m.value);
                }}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition",
                  selectedMode
                    ? "bg-emerald-500/15 text-emerald-400"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className={cn("grid gap-3", colunas)}>
        {visiveis.map((camera) => (
          <CameraTile
            key={camera.id}
            camera={camera}
            stats={stats[camera.id]}
            focused={focusedId === camera.id}
            onToggleFocus={() =>
              setFocusedId((atual) => (atual === camera.id ? null : camera.id))
            }
          />
        ))}
      </div>
    </section>
  );
}

type TileProps = {
  camera: Camera;
  stats?: StreamStats;
  focused: boolean;
  onToggleFocus: () => void;
};

function CameraTile({ camera, stats, focused, onToggleFocus }: TileProps) {
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [erro, setErro] = useState(false);

  // Ciclo de vida da transmissão MJPEG via proxy seguro (zero-leak).
  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    setErro(false);
    img.src = `${streamProxyUrl(camera.id)}?v=${Date.now()}`;
    return () => abortMjpegStream(img);
  }, [camera.id]);

  const status = (stats?.status ?? String(camera.status)).toLowerCase();
  const online = status === "online";
  const reconectando = ["connecting", "reconnecting", "idle"].includes(status);
  const offline = ["error", "stopped", "disabled"].includes(status);
  const avesAtivas = stats?.active_birds ?? 0;

  const connLabel = online ? "Online" : reconectando ? "Reconectando" : "Offline";
  const connTone = online
    ? "text-emerald-400"
    : reconectando
      ? "text-amber-300"
      : "text-red-300";
  const dotTone = online
    ? "bg-emerald-400"
    : reconectando
      ? "bg-amber-400 animate-pulse-soft"
      : "bg-red-400";

  return (
    <article
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-black",
        online ? "border-emerald-500/25" : "border-dark-700",
        focused && "ring-1 ring-emerald-500/40",
      )}
    >
      <div className="relative aspect-video w-full">
        <img
          ref={imgRef}
          alt={`Vídeo ao vivo: ${camera.name}`}
          onError={() => setErro(true)}
          onLoad={() => setErro(false)}
          className="h-full w-full object-cover"
        />

        {erro || offline ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-dark-900/80">
            <WifiOff className="h-6 w-6 text-[var(--color-text-muted)]" />
            <span className="text-xs text-[var(--color-text-muted)]">
              {offline ? "Câmera offline" : "Sem sinal — reconectando…"}
            </span>
          </div>
        ) : null}

        {/* Selo de conexão (Alaris Core) */}
        <div className="absolute left-2 top-2 flex items-center gap-1.5 rounded-md bg-black/60 px-2 py-1 backdrop-blur-sm">
          <span className={cn("h-1.5 w-1.5 rounded-full", dotTone)} />
          <span className={cn("text-[11px] font-semibold", connTone)}>
            {connLabel}
          </span>
        </div>

        {/* Foco individual */}
        <button
          type="button"
          onClick={onToggleFocus}
          title={focused ? "Sair do foco" : "Focar nesta câmera"}
          className="absolute right-2 top-2 rounded-md bg-black/60 p-1.5 text-white/70 opacity-0 backdrop-blur-sm transition group-hover:opacity-100 hover:text-emerald-400"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>

        {/* Selos inferiores: FPS + aves ativas no comedouro */}
        <div className="absolute inset-x-2 bottom-2 flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-md bg-black/60 px-2 py-1 text-[10px] font-medium text-cyan-300 backdrop-blur-sm">
            <Zap className="h-3 w-3" />
            {online ? `${(stats?.fps ?? 0).toFixed(1)} FPS` : "— FPS"}
          </span>
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium backdrop-blur-sm",
              avesAtivas > 0
                ? "bg-emerald-500/25 text-emerald-200"
                : "bg-black/60 text-[var(--color-text-muted)]",
            )}
          >
            <Bird className="h-3 w-3" />
            {avesAtivas} {avesAtivas === 1 ? "ave" : "aves"}
          </span>
          {stats?.backend ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-black/60 px-2 py-1 text-[10px] font-medium uppercase text-[var(--color-text-muted)] backdrop-blur-sm">
              {stats.backend}
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-dark-700 bg-dark-800 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
            {camera.name}
          </p>
          <p className="truncate text-[11px] text-[var(--color-text-muted)]">
            {camera.location_label || camera.source_type.toUpperCase()}
          </p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-emerald-400/80">
          <Wifi className="h-3 w-3" />
          Alaris
        </span>
      </div>
    </article>
  );
}
