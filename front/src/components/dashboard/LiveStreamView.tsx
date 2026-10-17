import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Crosshair, Frame, Gauge, Moon, Trash2, VideoOff } from "lucide-react";
import type { Camera } from "@/types";
import { videoFeedUrl } from "@/services/api";
import { cn } from "@/utils/cn";
import { abortMjpegStream } from "@/utils/stream";
import { StatusDot } from "@/components/common/StatusDot";

type Props = {
  cameras: Camera[];
  /** Abre o editor de áreas poligonais da câmera selecionada. */
  onEditZones: (camera: Camera) => void;
  /** Abre o editor de Zonas de Interesse (ROI) da câmera selecionada. */
  onEditRoi: (camera: Camera) => void;
  /** Remove a câmera selecionada (com confirmação). */
  onDelete: (camera: Camera) => void;
};

type StreamConnection = "connected" | "reconnecting" | "offline";

export function LiveStreamView({
  cameras,
  onEditZones,
  onEditRoi,
  onDelete,
}: Props) {
  const enabled = cameras.filter((c) => c.is_active);
  const [selectedId, setSelectedId] = useState<string>("");
  const [showBoxes, setShowBoxes] = useState(true);
  const [fps, setFps] = useState(0);
  // Cada mudança de versão gera uma URL nova, forçando o navegador a abrir uma
  // conexão MJPEG limpa (sem reaproveitar conexões antigas ou zumbis).
  const [streamVersion, setStreamVersion] = useState<number>(() => Date.now());
  const [streamConnection, setStreamConnection] =
    useState<StreamConnection>("reconnecting");

  const imgRef = useRef<HTMLImageElement | null>(null);
  const lastLoad = useRef<number | null>(null);
  const fpsSamples = useRef<number[]>([]);
  const retryRef = useRef<number | null>(null);
  const reconnectAttempts = useRef(0);
  const estavaOffline = useRef(false);

  useEffect(() => {
    if (!selectedId && enabled[0]) {
      setSelectedId(enabled[0].id);
    } else if (selectedId && !enabled.some((c) => c.id === selectedId)) {
      setSelectedId(enabled[0]?.id ?? "");
    }
  }, [enabled, selectedId]);

  const selected = enabled.find((c) => c.id === selectedId) ?? null;
  const cameraStatus = String(selected?.status ?? "").toLowerCase();
  const cameraOffline = ["error", "stopped", "disabled"].includes(cameraStatus);
  // Visão noturna ativa nesta câmera (informado pelo backend a cada polling).
  const nightActive = Boolean(selected?.night_mode);

  const feedSrc = selected
    ? `${videoFeedUrl(selected.id, showBoxes)}&v=${streamVersion}`
    : null;

  /** Cancela uma reconexão agendada. */
  const clearRetry = useCallback(() => {
    if (retryRef.current !== null) {
      window.clearTimeout(retryRef.current);
      retryRef.current = null;
    }
  }, []);

  /** Reinicia a transmissão abrindo uma nova conexão MJPEG. */
  const reconnect = useCallback(() => {
    clearRetry();
    setStreamVersion(Date.now());
  }, [clearRetry]);

  // Reinicia o estado da transmissão sempre que a fonte muda.
  useEffect(() => {
    setStreamConnection("reconnecting");
    lastLoad.current = null;
    fpsSamples.current = [];
    setFps(0);
    return clearRetry;
  }, [feedSrc, clearRetry]);

  // Gerencia a conexão MJPEG imperativamente. Ao trocar a fonte — ou ao
  // desmontar o painel numa troca de aba — a conexão anterior é encerrada na
  // hora; ao (re)montar, uma nova conexão é aberta. Isso libera o slot de
  // conexão do navegador e evita o acúmulo de transmissões (o "precisa dar F5").
  // No StrictMode (dev) o efeito é reexecutado e reabre a conexão sozinho.
  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    if (!feedSrc) {
      abortMjpegStream(img);
      return;
    }
    img.src = feedSrc;
    return () => abortMjpegStream(img);
  }, [feedSrc]);

  // Ao recuperar o foco da aba do navegador, garante uma transmissão ativa.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "visible") reconnect();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [reconnect]);

  // Quando a câmera volta a ficar online, reabre a transmissão.
  useEffect(() => {
    if (estavaOffline.current && !cameraOffline && feedSrc) {
      setStreamConnection("reconnecting");
      reconnect();
    }
    estavaOffline.current = cameraOffline;
  }, [cameraOffline, feedSrc, reconnect]);

  const connection: StreamConnection = cameraOffline
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
    reconnectAttempts.current = 0;
    clearRetry();
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

  const onImgError = () => {
    setStreamConnection("offline");
    // Backoff exponencial (até 10s) para não sobrecarregar o servidor.
    const attempt = reconnectAttempts.current;
    reconnectAttempts.current = Math.min(attempt + 1, 6);
    clearRetry();
    retryRef.current = window.setTimeout(() => {
      retryRef.current = null;
      setStreamConnection("reconnecting");
      reconnect();
    }, Math.min(1_500 * 2 ** attempt, 10_000));
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
                fpsSamples.current = [];
                setFps(0);
                reconnect();
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

          <span className="hidden h-5 w-px bg-dark-700 sm:block" aria-hidden />

          <button
            type="button"
            onClick={() => selected && onEditRoi(selected)}
            disabled={!selected}
            className="inline-flex items-center gap-1.5 rounded-lg border border-dark-700 bg-dark-900 px-2.5 py-1.5 text-xs font-medium text-sky-300 transition hover:bg-sky-500/10 disabled:opacity-40"
          >
            <Frame className="h-3.5 w-3.5" />
            Zonas ROI
          </button>
          <button
            type="button"
            onClick={() => selected && onEditZones(selected)}
            disabled={!selected}
            className="inline-flex items-center gap-1.5 rounded-lg border border-dark-700 bg-dark-900 px-2.5 py-1.5 text-xs font-medium text-emerald-300 transition hover:bg-emerald-500/10 disabled:opacity-40"
          >
            <Crosshair className="h-3.5 w-3.5" />
            Editar área
          </button>
          <button
            type="button"
            onClick={() => selected && onDelete(selected)}
            disabled={!selected}
            className="inline-flex items-center gap-1.5 rounded-lg border border-dark-700 bg-dark-900 px-2.5 py-1.5 text-xs font-medium text-red-300 transition hover:bg-red-500/10 disabled:opacity-40"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Remover
          </button>
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
              ref={imgRef}
              alt={`Stream ${selected.name}`}
              className="h-full w-full object-contain"
              onLoad={onImgLoad}
              onError={onImgError}
            />
            {nightActive ? (
              <div
                aria-hidden
                className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,rgba(30,27,75,0.55))] mix-blend-multiply"
              />
            ) : null}
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
              {nightActive ? (
                <span
                  className="flex items-center gap-1 text-indigo-300"
                  title="Visão noturna ativa"
                >
                  <Moon className="h-3.5 w-3.5" />
                </span>
              ) : null}
            </div>
            {showBoxes ? (
              <div className="absolute bottom-3 left-3 rounded-md bg-emerald-500/90 px-2 py-1 text-[10px] font-semibold text-dark-900">
                YOLOv8 · caixas ativas
              </div>
            ) : null}
            {nightActive ? (
              <div className="absolute bottom-3 right-3 flex items-center gap-1.5 rounded-md bg-indigo-500/90 px-2 py-1 text-[10px] font-semibold text-white">
                <Moon className="h-3 w-3" />
                Visão noturna
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
