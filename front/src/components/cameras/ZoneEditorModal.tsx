import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Check, Minus, Plus, RefreshCw, Save, Trash2, Undo2, X } from "lucide-react";
import type { Camera, Zone, ZoneMode, ZonePoint } from "@/types";
import {
  getCameraZones,
  getErrorMessage,
  saveCameraZones,
  videoFeedUrl,
} from "@/services/api";
import { abortMjpegStream } from "@/utils/stream";

type Props = {
  camera: Camera | null;
  onClose: () => void;
  onSaved: () => void;
};

type DraftZone = {
  mode: ZoneMode;
  points: ZonePoint[];
};

export function ZoneEditorModal({ camera, onClose, onSaved }: Props) {
  const [zones, setZones] = useState<Zone[]>([]);
  const [draft, setDraft] = useState<DraftZone | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamVersion, setStreamVersion] = useState(0);
  const [imageReady, setImageReady] = useState(false);
  const [streamError, setStreamError] = useState(false);
  // Referência ao <img> do stream, para abortar a conexão ao fechar o editor.
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!camera) return;
    let cancelled = false;
    setZones([]);
    setDraft(null);
    setError(null);
    setImageReady(false);
    setStreamError(false);
    setLoading(true);
    getCameraZones(camera.id)
      .then((loaded) => {
        if (!cancelled) setZones(loaded);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getErrorMessage(err, "Falha ao carregar as áreas"));
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

  if (!camera) return null;

  const addPoint = (event: MouseEvent<SVGSVGElement>) => {
    if (!draft) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    const y = Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
    setDraft({ ...draft, points: [...draft.points, { x, y }] });
  };

  const finishDraft = () => {
    if (!draft || draft.points.length < 3) return;
    const isInclusion = draft.mode === "include";
    setZones((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        name: isInclusion ? "Área de inclusão" : "Máscara de exclusão",
        points: draft.points,
        mode: draft.mode,
        min_dwell_seconds: 2,
        cooldown_seconds: 30,
        absence_tolerance_seconds: 1,
        enabled: true,
      },
    ]);
    setDraft(null);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveCameraZones(camera.id, zones);
      onSaved();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao salvar as áreas"));
    } finally {
      setSaving(false);
    }
  };

  const streamSrc = `${videoFeedUrl(camera.id, false)}&k=${streamVersion}`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6">
      <button
        type="button"
        className="absolute inset-0 bg-black/75"
        aria-label="Fechar editor de áreas"
        onClick={onClose}
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="zone-editor-title"
        className="relative z-10 flex max-h-[95vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-dark-700 bg-dark-800 shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-dark-700 px-4 py-3 sm:px-5">
          <div>
            <h2 id="zone-editor-title" className="font-display text-lg font-semibold">
              Áreas de leitura · {camera.name}
            </h2>
            <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
              Clique na imagem para adicionar vértices; as coordenadas são normalizadas.
            </p>
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

        <div className="grid min-h-0 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_17rem]">
          <div>
            <div className="relative overflow-hidden rounded-lg bg-black">
              <img
                ref={imgRef}
                src={streamSrc}
                alt={`Stream ao vivo de ${camera.name}`}
                className="block h-auto w-full"
                onLoad={() => {
                  setImageReady(true);
                  setStreamError(false);
                }}
                onError={() => {
                  setImageReady(false);
                  setStreamError(true);
                }}
              />
              <svg
                viewBox="0 0 1 1"
                preserveAspectRatio="none"
                onClick={addPoint}
                className={`absolute inset-0 h-full w-full ${
                  draft && imageReady ? "cursor-crosshair" : "pointer-events-none"
                }`}
                aria-label="Desenho de áreas sobre o vídeo"
              >
                {zones.map((zone) => {
                  const color = zone.mode === "exclude" ? "#f87171" : "#34d399";
                  return (
                    <g key={zone.id}>
                      <polygon
                        points={zone.points.map((point) => `${point.x},${point.y}`).join(" ")}
                        fill={color}
                        fillOpacity="0.2"
                        stroke={color}
                        strokeWidth="0.004"
                        vectorEffect="non-scaling-stroke"
                      />
                    </g>
                  );
                })}
                {draft ? (
                  <g>
                    {draft.points.length > 1 ? (
                      <polyline
                        points={draft.points.map((point) => `${point.x},${point.y}`).join(" ")}
                        fill="none"
                        stroke={draft.mode === "exclude" ? "#f87171" : "#34d399"}
                        strokeWidth="0.004"
                        vectorEffect="non-scaling-stroke"
                      />
                    ) : null}
                    {draft.points.map((point, index) => (
                      <circle
                        key={index}
                        cx={point.x}
                        cy={point.y}
                        r="0.009"
                        fill={draft.mode === "exclude" ? "#f87171" : "#34d399"}
                        stroke="#0a0f0d"
                        strokeWidth="0.002"
                      />
                    ))}
                  </g>
                ) : null}
              </svg>
              {loading ? (
                <div className="absolute inset-0 flex items-center justify-center bg-dark-900/80 text-sm text-[var(--color-text-muted)]">
                  Carregando áreas…
                </div>
              ) : null}
              {streamError ? (
                <div className="absolute inset-0 flex items-center justify-center bg-dark-900/80 px-4 text-center text-sm text-amber-200">
                  Stream indisponível. Verifique se a câmera está ativa e atualize a imagem.
                </div>
              ) : null}
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs text-[var(--color-text-muted)]">
                {imageReady
                  ? "Stream ao vivo · Verde: inclusão · Vermelho: exclusão"
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

          <aside className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                disabled={loading || saving || !imageReady}
                onClick={() => setDraft({ mode: "include", points: [] })}
                className="inline-flex items-center justify-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2 py-2 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50"
              >
                <Plus className="h-3.5 w-3.5" />
                Incluir
              </button>
              <button
                type="button"
                disabled={loading || saving || !imageReady}
                onClick={() => setDraft({ mode: "exclude", points: [] })}
                className="inline-flex items-center justify-center gap-1 rounded-lg border border-red-500/40 bg-red-500/10 px-2 py-2 text-xs font-medium text-red-300 hover:bg-red-500/20 disabled:opacity-50"
              >
                <Minus className="h-3.5 w-3.5" />
                Excluir
              </button>
            </div>

            {draft ? (
              <div className="space-y-2 rounded-lg border border-dark-700 bg-dark-900 p-3">
                <p className="text-xs text-[var(--color-text-muted)]">
                  {draft.mode === "include" ? "Desenhando inclusão" : "Desenhando exclusão"} ·{" "}
                  {draft.points.length} ponto(s)
                </p>
                <div className="flex flex-wrap gap-1">
                  <button
                    type="button"
                    onClick={() =>
                      setDraft({ ...draft, points: draft.points.slice(0, -1) })
                    }
                    disabled={draft.points.length === 0}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[var(--color-text-muted)] hover:bg-dark-700 disabled:opacity-40"
                  >
                    <Undo2 className="h-3 w-3" />
                    Desfazer ponto
                  </button>
                  <button
                    type="button"
                    onClick={finishDraft}
                    disabled={draft.points.length < 3}
                    className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-40"
                  >
                    <Check className="h-3 w-3" />
                    Concluir área
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraft(null)}
                    className="rounded-md px-2 py-1 text-xs text-[var(--color-text-muted)] hover:bg-dark-700"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            ) : null}

            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Áreas configuradas ({zones.length})
              </h3>
              {zones.length === 0 ? (
                <p className="rounded-lg border border-dashed border-dark-700 p-3 text-xs text-[var(--color-text-muted)]">
                  Sem áreas configuradas: o sistema monitora o quadro inteiro.
                </p>
              ) : (
                zones.map((zone) => (
                  <div
                    key={zone.id}
                    className="flex items-center justify-between gap-2 rounded-lg bg-dark-900 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium">{zone.name}</p>
                      <p className="text-[10px] text-[var(--color-text-muted)]">
                        {zone.mode === "exclude" ? "Exclusão" : "Inclusão"} · {zone.points.length} pontos
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setZones((current) => current.filter((item) => item.id !== zone.id))}
                      aria-label={`Remover ${zone.name}`}
                      className="rounded-md p-1.5 text-red-300 hover:bg-red-500/10"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </aside>
        </div>

        {error ? (
          <p role="alert" className="mx-4 mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
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
            onClick={() => void save()}
            disabled={loading || saving || draft !== null}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-dark-900 hover:bg-emerald-400 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saving ? "Salvando…" : "Salvar áreas"}
          </button>
        </footer>
      </section>
    </div>
  );
}
