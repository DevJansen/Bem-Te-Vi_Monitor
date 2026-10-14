import { useEffect, useRef, useState } from "react";
import { Box, Gauge, VideoOff } from "lucide-react";
import type { Camera } from "@/types";
import { videoFeedUrl } from "@/services/api";
import { cn } from "@/utils/cn";
import { StatusDot } from "@/components/common/StatusDot";

type Props = {
  cameras: Camera[];
};

type StreamConnection = "connected" | "reconnecting" | "offline";

export function LiveStreamView({ cameras }: Props) {
  const enabled = cameras.filter((c) => c.enabled);
  const [selectedId, setSelectedId] = useState<string>("");
  const [showBoxes, setShowBoxes] = useState(true);
  const [fps, setFps] = useState(0);
  const [streamKey, setStreamKey] = useState(0);
  const [streamConnection, setStreamConnection] =
    useState<StreamConnection>("reconnecting");
  const lastLoad = useRef<number | null>(null);
  const fpsSamples = useRef<number[]>([]);

  useEffect(() => {
    if (!selectedId && enabled[0]) {
      setSelectedId(enabled[0].id);
    } else if (selectedId && !enabled.some((c) => c.id === selectedId)) {
      setSelectedId(enabled[0]?.id ?? "");
    }
  }, [enabled, selectedId]);

  const selected = enabled.find((c) => c.id === selectedId) ?? null;

  const feedSrc = selected
    ? `${videoFeedUrl(selected.id, showBoxes)}&k=${streamKey}`
    : null;

  useEffect(() => {
    setStreamConnection("reconnecting");
    lastLoad.current = null;
    fpsSamples.current = [];
    setFps(0);
  }, [feedSrc]);

  const cameraStatus = String(selected?.status ?? "").toLowerCase();
  const connection: StreamConnection =
    ["error", "stopped", "disabled"].includes(cameraStatus)
      ? "offline"
      : ["connecting", "reconnecting", "idle"].includes(cameraStatus)
        ? "reconnecting"
        : streamConnection;
  const connectionLabel =
    connection === "connected"
      ? "Conectado"
      : connection === "reconnecting"
        ? "Reconectando..."
        : "Câmera Offline";

  const onImgLoad = () => {
    setStreamConnection("connected");
    const now = performance.now();
    if (lastLoad.current != null) {
      const dt = now - lastLoad.current;
      if (dt > 0 && dt < 2000) {
        const instant = 1000 / dt;
        fpsSamples.current = [...fpsSamples.current.slice(-12), instant];
        const avg =
          fpsSamples.current.reduce((a, b) => a + b, 0) /
          fpsSamples.current.length;
        setFps(Math.round(avg));
      }
    }
    lastLoad.current = now;
  };

  return (
    <section className="overflow-hidden rounded-xl border border-dark-700 bg-dark-800">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-dark-700 px-4 py-3">
        <div>
          <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
            Transmissão ao vivo
          </h2>
          <p className="text-xs text-[var(--color-text-muted)]">
            Stream MJPEG local · YOLOv8
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 rounded-lg border border-dark-700 bg-dark-900 px-2.5 py-1.5 text-xs text-[var(--color-text-muted)]">
            <span className="sr-only">Selecionar câmera</span>
            <select
              value={selectedId}
              onChange={(e) => {
                setSelectedId(e.target.value);
                setStreamKey((k) => k + 1);
                fpsSamples.current = [];
                setFps(0);
              }}
              className="bg-transparent text-[var(--color-text-primary)] outline-none"
            >
              {enabled.length === 0 ? (
                <option value="">Nenhuma câmera</option>
              ) : (
                enabled.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))
              )}
            </select>
          </label>

          <button
            type="button"
            onClick={() => setShowBoxes((v) => !v)}
            aria-pressed={showBoxes}
            aria-label={`Bounding boxes ${showBoxes ? "ligadas" : "desligadas"}`}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition",
              showBoxes
                ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-400"
                : "border-dark-700 bg-dark-900 text-[var(--color-text-muted)]",
            )}
          >
            <Box className="h-3.5 w-3.5" />
            Bounding boxes
          </button>

          <div className="inline-flex items-center gap-1.5 rounded-lg border border-dark-700 bg-dark-900 px-2.5 py-1.5 text-xs text-[var(--color-text-muted)]">
            <Gauge className="h-3.5 w-3.5 text-emerald-400" />
            <span className="tabular-nums text-[var(--color-text-primary)]">{fps}</span>{" "}
            FPS
          </div>
        </div>
      </div>

      <div className="relative aspect-video bg-dark-900">
        {!selected || !feedSrc ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-[var(--color-text-muted)]">
            <VideoOff className="h-8 w-8 opacity-50" />
            <p className="text-sm">Nenhuma câmera ativa para exibir.</p>
          </div>
        ) : (
          <>
            <img
              key={feedSrc}
              src={feedSrc}
              alt={`Stream ${selected.name}`}
              className="h-full w-full object-contain"
              onLoad={onImgLoad}
              onError={() => setStreamConnection("offline")}
            />
            <div className="absolute left-3 top-3 flex items-center gap-2 rounded-md bg-dark-900/80 px-2 py-1 text-xs backdrop-blur">
              <StatusDot
                status={
                  connection === "connected"
                    ? "online"
                    : connection === "reconnecting"
                      ? "reconnecting"
                      : "error"
                }
              />
              <span>{selected.name}</span>
              <span
                className={
                  connection === "offline"
                    ? "text-red-300"
                    : connection === "reconnecting"
                      ? "text-amber-300"
                      : "text-emerald-300"
                }
                role="status"
                aria-live="polite"
              >
                {connectionLabel}
              </span>
            </div>
            {showBoxes ? (
              <div className="absolute bottom-3 left-3 rounded-md bg-emerald-500/90 px-2 py-1 text-[10px] font-semibold text-dark-900">
                YOLOv8 · caixas ativas
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
