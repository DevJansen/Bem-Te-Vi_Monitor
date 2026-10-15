import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Eraser, Frame, RefreshCw, Save, Trash2, Undo2, X } from "lucide-react";
import type { Camera, RoiType, RoiZone } from "@/types";
import { fetchRoi, getErrorMessage, saveRoi, videoFeedUrl } from "@/services/api";
import { cn } from "@/utils/cn";
import { abortMjpegStream } from "@/utils/stream";

type Props = {
  camera: Camera | null;
  onClose: () => void;
  onSaved: () => void;
};

/** Retângulo em construção (coordenadas normalizadas 0..1). */
type DraftRect = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

/** Cores usadas no canvas para cada tipo de zona. */
const CORES: Record<RoiType, { linha: string; fundo: string }> = {
  include: { linha: "#34d399", fundo: "rgba(52, 211, 153, 0.22)" },
  exclude: { linha: "#f87171", fundo: "rgba(248, 113, 113, 0.22)" },
};

/**
 * Editor visual de Zonas de Interesse (ROI).
 *
 * O usuário clica e arrasta o mouse sobre o feed para desenhar retângulos.
 * Zonas de inclusão (verde) restringem o monitoramento; zonas de exclusão
 * (vermelho) ignoram falsos positivos (galhos, tráfego, reflexos).
 */
export function RoiEditorModal({ camera, onClose, onSaved }: Props) {
  const [zones, setZones] = useState<RoiZone[]>([]);
  const [mode, setMode] = useState<RoiType>("include");
  const [draft, setDraft] = useState<DraftRect | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamVersion, setStreamVersion] = useState(0);
  const [imageReady, setImageReady] = useState(false);
  const [streamError, setStreamError] = useState(false);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // Espelho do rascunho para ler o valor final sem depender de re-render.
  const draftRef = useRef<DraftRect | null>(null);
  // Referência ao <img> do stream, para abortar a conexão ao fechar o editor.
  const imgRef = useRef<HTMLImageElement | null>(null);

  /* ——— Carregamento das zonas salvas ——— */
  useEffect(() => {
    if (!camera) return;
    let cancelled = false;
    setZones([]);
    setDraft(null);
    draftRef.current = null;
    setDrawing(false);
    setError(null);
    setImageReady(false);
    setStreamError(false);
    setLoading(true);
    fetchRoi(camera.id)
      .then((loaded) => {
        if (!cancelled) setZones(loaded);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(getErrorMessage(err, "Falha ao carregar as zonas de interesse"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [camera]);

  // Encerra a conexão MJPEG ao fechar o editor (ou trocar de câmera),
  // liberando o slot de conexão do navegador para as próximas requisições.
  useEffect(() => {
    const img = imgRef.current;
    return () => abortMjpegStream(img);
  }, [camera?.id]);

  /* ——— Desenho do canvas (zonas salvas + rascunho) ——— */
  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const bounds = container.getBoundingClientRect();
    const width = Math.max(1, bounds.width);
    const height = Math.max(1, bounds.height);
    const dpr = window.devicePixelRatio || 1;

    // Ajusta a resolução do canvas ao tamanho exibido (nitidez em telas HiDPI).
    // O tamanho de exibição é controlado pelas classes CSS (`inset-0`/`h-full`),
    // por isso não definimos `style.width/height` aqui.
    if (
      canvas.width !== Math.round(width * dpr) ||
      canvas.height !== Math.round(height * dpr)
    ) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const paint = (
      rect: DraftRect,
      type: RoiType,
      label?: string,
      dashed = false,
    ) => {
      const cor = CORES[type];
      const x = rect.x1 * width;
      const y = rect.y1 * height;
      const w = (rect.x2 - rect.x1) * width;
      const h = (rect.y2 - rect.y1) * height;

      ctx.fillStyle = cor.fundo;
      ctx.fillRect(x, y, w, h);

      ctx.lineWidth = 2;
      ctx.strokeStyle = cor.linha;
      ctx.setLineDash(dashed ? [6, 4] : []);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);

      if (label) {
        ctx.font = "600 12px system-ui, -apple-system, sans-serif";
        const largura = ctx.measureText(label).width;
        ctx.fillStyle = "rgba(2, 6, 23, 0.72)";
        ctx.fillRect(x + 4, y + 4, largura + 14, 21);
        ctx.fillStyle = cor.linha;
        ctx.fillText(label, x + 11, y + 19);
      }
    };

    zones.forEach((zone) => paint(zone, zone.type, zone.name));
    if (draft) paint(draft, mode, "novo", true);
  }, [zones, draft, mode]);

  useEffect(() => {
    redraw();
  }, [redraw, imageReady]);

  // Redesenha quando o feed muda de tamanho (carregamento da imagem, resize).
  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => redraw());
    observer.observe(container);
    return () => observer.disconnect();
  }, [redraw]);

  if (!camera) return null;

  const pontoNormalizado = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    const y = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
    return { x, y };
  };

  const iniciarDesenho = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!imageReady || loading || saving) return;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Alguns navegadores podem recusar a captura; o arrasto segue funcionando
      // enquanto o ponteiro permanecer sobre o canvas.
    }
    const { x, y } = pontoNormalizado(event);
    const novo = { x1: x, y1: y, x2: x, y2: y };
    draftRef.current = novo;
    setDraft(novo);
    setDrawing(true);
  };

  const atualizarDesenho = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!drawing || !draftRef.current) return;
    const { x, y } = pontoNormalizado(event);
    const novo = { ...draftRef.current, x2: x, y2: y };
    draftRef.current = novo;
    setDraft(novo);
  };

  const finalizarDesenho = () => {
    if (!drawing) return;
    setDrawing(false);
    const atual = draftRef.current;
    draftRef.current = null;
    setDraft(null);
    if (!atual) return;

    const x1 = Math.min(atual.x1, atual.x2);
    const y1 = Math.min(atual.y1, atual.y2);
    const x2 = Math.max(atual.x1, atual.x2);
    const y2 = Math.max(atual.y1, atual.y2);

    // Ignora retângulos muito pequenos (clique acidental).
    if (x2 - x1 < 0.02 || y2 - y1 < 0.02) return;

    setZones((lista) => {
      const total = lista.filter((zona) => zona.type === mode).length + 1;
      return [
        ...lista,
        {
          id: crypto.randomUUID(),
          name: mode === "include" ? `Inclusão ${total}` : `Exclusão ${total}`,
          type: mode,
          x1,
          y1,
          x2,
          y2,
        },
      ];
    });
  };

  const desfazerUltimo = () => {
    setZones((lista) => lista.slice(0, -1));
  };

  const limparTudo = () => {
    setZones([]);
    setDraft(null);
    draftRef.current = null;
  };

  const salvar = async () => {
    if (!camera) return;
    setSaving(true);
    setError(null);
    try {
      await saveRoi(camera.id, zones);
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao salvar as zonas de interesse"));
    } finally {
      setSaving(false);
    }
  };

  const streamSrc = `${videoFeedUrl(camera.id, false)}&k=${streamVersion}`;
  const desenhavel = imageReady && !loading && !saving;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6">
      <button
        type="button"
        className="absolute inset-0 bg-black/75"
        aria-label="Fechar editor de zonas de interesse"
        onClick={onClose}
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="roi-editor-title"
        className="relative z-10 flex max-h-[95vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-dark-700 bg-dark-800 shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-dark-700 px-4 py-3 sm:px-5">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 rounded-lg bg-emerald-500/10 p-1.5 text-emerald-300">
              <Frame className="h-4 w-4" />
            </span>
            <div>
              <h2 id="roi-editor-title" className="font-display text-lg font-semibold">
                Zonas de Interesse (ROI) · {camera.name}
              </h2>
              <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                Clique e arraste sobre o vídeo para desenhar um retângulo. As coordenadas são
                normalizadas (0 a 1).
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-dark-700"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="grid min-h-0 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
          {/* ——— Feed com o canvas sobreposto ——— */}
          <div>
            <div
              ref={containerRef}
              className="relative overflow-hidden rounded-lg bg-black"
            >
              <img
                ref={imgRef}
                src={streamSrc}
                alt={`Stream ao vivo de ${camera.name}`}
                className="block h-auto w-full select-none"
                draggable={false}
                onLoad={() => {
                  setImageReady(true);
                  setStreamError(false);
                }}
                onError={() => {
                  setImageReady(false);
                  setStreamError(true);
                }}
              />
              <canvas
                ref={canvasRef}
                onPointerDown={iniciarDesenho}
                onPointerMove={atualizarDesenho}
                onPointerUp={finalizarDesenho}
                onPointerCancel={finalizarDesenho}
                className={cn(
                  "absolute inset-0 h-full w-full touch-none",
                  desenhavel ? "cursor-crosshair" : "pointer-events-none",
                )}
                aria-label="Área de desenho das zonas de interesse"
              />

              {loading ? (
                <div className="absolute inset-0 flex items-center justify-center bg-dark-900/80 text-sm text-[var(--color-text-muted)]">
                  Carregando zonas…
                </div>
              ) : null}
              {streamError ? (
                <div className="absolute inset-0 flex items-center justify-center bg-dark-900/80 px-4 text-center text-sm text-amber-200">
                  Stream indisponível. Verifique se a câmera está ativa e reconecte.
                </div>
              ) : null}

              {/* Barra flutuante de ações rápidas */}
              <div className="absolute inset-x-0 bottom-3 flex justify-center px-3">
                <div className="flex items-center gap-1 rounded-full border border-dark-700/80 bg-dark-900/85 p-1 shadow-lg backdrop-blur">
                  <button
                    type="button"
                    onClick={desfazerUltimo}
                    disabled={zones.length === 0 || saving}
                    className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium text-[var(--color-text-muted)] hover:bg-dark-700 disabled:opacity-40"
                  >
                    <Undo2 className="h-3.5 w-3.5" />
                    Desfazer Último
                  </button>
                  <button
                    type="button"
                    onClick={limparTudo}
                    disabled={zones.length === 0 || saving}
                    className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium text-[var(--color-text-muted)] hover:bg-dark-700 disabled:opacity-40"
                  >
                    <Eraser className="h-3.5 w-3.5" />
                    Limpar Tudo
                  </button>
                  <button
                    type="button"
                    onClick={() => void salvar()}
                    disabled={saving || loading}
                    className="inline-flex items-center gap-1 rounded-full bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-dark-900 hover:bg-emerald-400 disabled:opacity-50"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {saving ? "Salvando…" : "Salvar Zonas"}
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-[var(--color-text-muted)]">
                {desenhavel
                  ? "🟢 Inclusão: monitorar · 🔴 Exclusão: ignorar"
                  : "Aguardando imagem da câmera…"}
              </p>
              <button
                type="button"
                onClick={() => {
                  setImageReady(false);
                  setStreamError(false);
                  setStreamVersion((version) => version + 1);
                }}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[var(--color-text-muted)] hover:bg-dark-700"
              >
                <RefreshCw className="h-3 w-3" />
                Reconectar stream
              </button>
            </div>
          </div>

          {/* ——— Painel lateral ——— */}
          <aside className="space-y-4">
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Modo de desenho
              </h3>
              <button
                type="button"
                onClick={() => setMode("include")}
                aria-pressed={mode === "include"}
                className={cn(
                  "flex w-full items-start gap-2 rounded-lg border px-3 py-2 text-left transition",
                  mode === "include"
                    ? "border-emerald-500/60 bg-emerald-500/10"
                    : "border-dark-700 bg-dark-900 hover:bg-dark-700/60",
                )}
              >
                <span aria-hidden className="text-base leading-none">
                  🟢
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-emerald-200">
                    Zona de Inclusão (Monitorar)
                  </span>
                  <span className="mt-0.5 block text-[11px] text-[var(--color-text-muted)]">
                    Só registra visitas e fotos se o passarinho aparecer dentro do quadrado.
                  </span>
                </span>
              </button>
              <button
                type="button"
                onClick={() => setMode("exclude")}
                aria-pressed={mode === "exclude"}
                className={cn(
                  "flex w-full items-start gap-2 rounded-lg border px-3 py-2 text-left transition",
                  mode === "exclude"
                    ? "border-red-500/60 bg-red-500/10"
                    : "border-dark-700 bg-dark-900 hover:bg-dark-700/60",
                )}
              >
                <span aria-hidden className="text-base leading-none">
                  🔴
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-red-200">
                    Zona de Exclusão (Ignorar)
                  </span>
                  <span className="mt-0.5 block text-[11px] text-[var(--color-text-muted)]">
                    Ignora qualquer detecção dentro do quadrado (galhos, vento, tráfego).
                  </span>
                </span>
              </button>
            </div>

            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Zonas ativas ({zones.length})
              </h3>
              {zones.length === 0 ? (
                <p className="rounded-lg border border-dashed border-dark-700 p-3 text-xs text-[var(--color-text-muted)]">
                  Sem zonas: o sistema monitora o quadro inteiro.
                </p>
              ) : (
                <ul className="space-y-2">
                  {zones.map((zone) => (
                    <li
                      key={zone.id}
                      className="flex items-center justify-between gap-2 rounded-lg bg-dark-900 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium">{zone.name}</p>
                        <p className="text-[10px] text-[var(--color-text-muted)]">
                          {zone.type === "exclude" ? "🔴 Exclusão" : "🟢 Inclusão"} ·{" "}
                          {Math.round((zone.x2 - zone.x1) * 100)}% ×{" "}
                          {Math.round((zone.y2 - zone.y1) * 100)}%
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          setZones((lista) => lista.filter((item) => item.id !== zone.id))
                        }
                        aria-label={`Remover ${zone.name}`}
                        className="rounded-md p-1.5 text-red-300 hover:bg-red-500/10"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>
        </div>

        {error ? (
          <p
            role="alert"
            className="mx-4 mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300"
          >
            {error}
          </p>
        ) : null}

        <footer className="flex justify-end gap-2 border-t border-dark-700 px-4 py-3 sm:px-5">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-dark-700 px-3 py-2 text-sm text-[var(--color-text-muted)] hover:bg-dark-700 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => void salvar()}
            disabled={saving || loading}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-dark-900 hover:bg-emerald-400 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saving ? "Salvando…" : "Salvar Zonas"}
          </button>
        </footer>
      </section>
    </div>
  );
}
