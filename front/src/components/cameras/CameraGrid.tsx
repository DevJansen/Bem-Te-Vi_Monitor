import type { ReactNode } from "react";
import { Crosshair, Plus, Trash2, Wifi, WifiOff } from "lucide-react";
import type { Camera } from "@/types";
import { StatusDot } from "@/components/common/StatusDot";
import { statusLabel } from "@/utils/format";
import { cn } from "@/utils/cn";

type Props = {
  cameras: Camera[];
  loading?: boolean;
  onAdd: () => void;
  onToggle: (camera: Camera, enabled: boolean) => void;
  onDelete: (camera: Camera) => void;
  onEditZones: (camera: Camera) => void;
};

export function CameraGrid({
  cameras,
  loading,
  onAdd,
  onToggle,
  onDelete,
  onEditZones,
}: Props) {
  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
            Câmeras
          </h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            Fontes USB, RTSP e ONVIF com credenciais locais criptografadas
          </p>
        </div>
        <button
          type="button"
          onClick={onAdd}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400"
        >
          <Plus className="h-4 w-4" />
          Nova câmera
        </button>
      </div>

      {loading && cameras.length === 0 ? (
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
                    </p>
                  </div>
                  {online ? (
                    <Wifi className="h-4 w-4 shrink-0 text-emerald-400" />
                  ) : (
                    <WifiOff className="h-4 w-4 shrink-0 text-[var(--color-text-muted)]" />
                  )}
                </div>

                <p className="mt-3 truncate rounded-lg bg-dark-900 px-2 py-1.5 font-mono text-[11px] text-[var(--color-text-muted)]">
                  {camera.source_uri}
                </p>

                <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
                  <Badge tone={camera.enabled ? "ok" : "muted"}>
                    {camera.enabled ? "Monitorando" : "Pausada"}
                  </Badge>
                  {camera.has_credentials ? (
                    <Badge tone="ok">Credenciais OK</Badge>
                  ) : (
                    <Badge tone="muted">Sem credenciais</Badge>
                  )}
                  <Badge tone="muted">{camera.zones.length} zona(s)</Badge>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-dark-700 pt-3">
                  <label className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                    <input
                      type="checkbox"
                      checked={camera.enabled}
                      onChange={(e) => onToggle(camera, e.target.checked)}
                      className="accent-emerald-500"
                    />
                    Ativa
                  </label>
                  <div className="flex items-center gap-1">
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
  tone: "ok" | "muted";
}) {
  return (
    <span
      className={cn(
        "rounded-md px-2 py-0.5",
        tone === "ok" && "bg-emerald-500/15 text-emerald-400",
        tone === "muted" && "bg-dark-700 text-[var(--color-text-muted)]",
      )}
    >
      {children}
    </span>
  );
}
