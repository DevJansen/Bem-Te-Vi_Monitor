import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  ChevronDown,
  Eye,
  EyeOff,
  KeyRound,
  Link2,
  Lock,
  MapPin,
  Plus,
  Webcam,
  X,
} from "lucide-react";
import type { CameraCreatePayload, SourceType } from "@/types";
import { cn } from "@/utils/cn";

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: CameraCreatePayload) => Promise<void>;
};

type Modo = "stream" | "usb";

/** Detecta o tipo de fonte a partir do link colado (Smart Stream Resolver). */
function detectarTipo(url: string): SourceType {
  const v = url.trim().toLowerCase();
  if (!v) return "rtsp";
  if (v.startsWith("rtsp://") || v.startsWith("rtsps://")) return "rtsp";
  if (v.startsWith("ws://") || v.startsWith("wss://")) return "webrtc";
  if (v.includes(".m3u8")) return "hls";
  if (v.startsWith("http://") || v.startsWith("https://")) return "http";
  return "rtsp";
}

const TIPO_LABEL: Record<SourceType, string> = {
  usb: "Webcam / USB",
  rtsp: "RTSP",
  hls: "HLS",
  http: "HTTP / MJPEG",
  webrtc: "WebRTC",
  onvif: "ONVIF",
};

export function AddCameraModal({ open, onClose, onSubmit }: Props) {
  const [modo, setModo] = useState<Modo>("stream");
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [url, setUrl] = useState("");
  const [usbIndex, setUsbIndex] = useState("0");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mostrarCredenciais, setMostrarCredenciais] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tipoDetectado = useMemo(() => detectarTipo(url), [url]);
  const linkComCredenciais = /\/\/[^/@\s]+:[^/@\s]+@/.test(url);

  if (!open) return null;

  const reset = () => {
    setModo("stream");
    setName("");
    setLocation("");
    setUrl("");
    setUsbIndex("0");
    setUsername("");
    setPassword("");
    setShowPassword(false);
    setMostrarCredenciais(false);
    setEnabled(true);
    setError(null);
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const usarCredenciais =
        modo === "stream" && mostrarCredenciais && (username || password);
      const payload: CameraCreatePayload = {
        name: name.trim(),
        location_label: location.trim() || undefined,
        enabled,
        source_type: modo === "usb" ? "usb" : tipoDetectado,
        stream_url: modo === "usb" ? usbIndex.trim() : url.trim(),
        username: usarCredenciais && username ? username : null,
        password: usarCredenciais && password ? password : null,
      };
      await onSubmit(payload);
      reset();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao cadastrar câmera");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/70"
        aria-label="Fechar"
        onClick={handleClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-camera-title"
        className="relative z-10 w-full max-w-lg overflow-hidden rounded-xl border border-dark-700 bg-dark-800 shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-dark-700 px-5 py-4">
          <div>
            <h2
              id="add-camera-title"
              className="font-display text-lg font-semibold text-[var(--color-text-primary)]"
            >
              <span className="inline-flex items-center gap-2">
                <Link2 className="h-4 w-4 text-emerald-400" />
                Adicionar câmera
              </span>
            </h2>
            <p className="mt-0.5 flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
              <Lock className="h-3 w-3 text-emerald-400" />
              Cole o link e conecte — credenciais são opcionais
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-5 py-4">
          {/* Seletor de origem: stream externo (URL) x webcam local */}
          <div className="flex gap-1 rounded-lg border border-dark-700 bg-dark-900 p-1">
            <button
              type="button"
              onClick={() => setModo("stream")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition",
                modo === "stream"
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
              )}
            >
              <Link2 className="h-3.5 w-3.5" />
              Câmera externa (URL)
            </button>
            <button
              type="button"
              onClick={() => setModo("usb")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition",
                modo === "usb"
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
              )}
            >
              <Webcam className="h-3.5 w-3.5" />
              Webcam local (USB)
            </button>
          </div>

          <Field label="Nome da câmera">
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex.: Bebedouro do vizinho"
              className={inputClass}
            />
          </Field>

          <Field label="Local" hint="Ex.: Casa vizinha · Sitio · Parque (opcional)">
            <div className="relative">
              <MapPin className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="Onde esta câmera está instalada?"
                className={`${inputClass} pl-9`}
              />
            </div>
          </Field>

          {modo === "stream" ? (
            <>
              <Field
                label="URL do Stream ao Vivo (RTSP, HLS, HTTP)"
                hint="Links públicos/abertos conectam direto, sem login."
              >
                <div className="relative">
                  <Link2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
                  <input
                    required
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="rtsp://... ou https://.../stream.m3u8"
                    className={`${inputClass} pl-9 font-mono text-[13px]`}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
              </Field>

              {url.trim() ? (
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="inline-flex items-center gap-1 rounded-md bg-cyan-500/10 px-2 py-0.5 text-cyan-300">
                    Tipo detectado: {TIPO_LABEL[tipoDetectado]}
                  </span>
                  {linkComCredenciais ? (
                    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-emerald-300">
                      <Lock className="h-3 w-3" />
                      Credenciais no link serão criptografadas
                    </span>
                  ) : null}
                </div>
              ) : null}

              {/* Seção opcional e recolhível de credenciais */}
              <div className="rounded-lg border border-dark-700 bg-dark-900/60">
                <button
                  type="button"
                  onClick={() => setMostrarCredenciais((v) => !v)}
                  aria-expanded={mostrarCredenciais}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
                >
                  <span className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-muted)]">
                    <KeyRound className="h-3.5 w-3.5 text-emerald-400" />
                    Esta câmera exige login e senha?{" "}
                    <span className="text-[var(--color-text-muted)]/60">(Opcional)</span>
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform",
                      mostrarCredenciais && "rotate-180",
                    )}
                  />
                </button>

                {mostrarCredenciais ? (
                  <div className="grid gap-3 border-t border-dark-700 px-3 py-3 sm:grid-cols-2">
                    <Field label="Usuário (criptografado)">
                      <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className={inputClass}
                        autoComplete="off"
                      />
                    </Field>
                    <Field label="Senha (criptografada)">
                      <div className="relative">
                        <input
                          type={showPassword ? "text" : "password"}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          className={`${inputClass} pr-10`}
                          autoComplete="new-password"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword((v) => !v)}
                          aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-[var(--color-text-muted)] transition hover:text-emerald-400"
                        >
                          {showPassword ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    </Field>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <Field
              label="Índice da webcam USB"
              hint="Normalmente 0 para a primeira webcam conectada."
            >
              <input
                required
                value={usbIndex}
                onChange={(e) => setUsbIndex(e.target.value)}
                placeholder="0"
                className={`${inputClass} font-mono`}
              />
            </Field>
          )}

          <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="accent-emerald-500"
            />
            Ativar monitoramento imediatamente
          </label>

          {error ? (
            <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          ) : null}

          <div className="flex items-center justify-between gap-2 border-t border-dark-700 pt-4">
            <p className="hidden items-center gap-1 text-[11px] text-[var(--color-text-muted)] sm:flex">
              <Lock className="h-3 w-3" />
              Nunca expomos sua URL/senha no navegador
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-dark-700 px-4 py-2 text-sm text-[var(--color-text-muted)] hover:bg-dark-700"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:opacity-60"
              >
                <Plus className="h-4 w-4" />
                {submitting ? "Conectando…" : "Salvar e conectar"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-[var(--color-text-muted)]">
        {label}
      </span>
      {children}
      {hint ? (
        <span className="mt-1 block text-[11px] text-[var(--color-text-muted)]">{hint}</span>
      ) : null}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none transition placeholder:text-[var(--color-text-muted)]/60 focus:border-emerald-500/50";
