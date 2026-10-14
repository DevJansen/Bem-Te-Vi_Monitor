import { useState, type FormEvent, type ReactNode } from "react";
import { Lock, X } from "lucide-react";
import type { CameraCreatePayload, SourceType } from "@/types";
import { cn } from "@/utils/cn";

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: CameraCreatePayload) => Promise<void>;
};

const SOURCE_OPTIONS: Array<{ value: SourceType; label: string; hint: string }> = [
  { value: "usb", label: "Webcam / USB", hint: "Índice do dispositivo (ex.: 0)" },
  { value: "rtsp", label: "RTSP", hint: "URL rtsp:// ou host:porta" },
  { value: "onvif", label: "ONVIF", hint: "Host do dispositivo ONVIF" },
];

export function AddCameraModal({ open, onClose, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("usb");
  const [sourceUri, setSourceUri] = useState("0");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const needsCreds = sourceType === "rtsp" || sourceType === "onvif";

  const reset = () => {
    setName("");
    setSourceType("usb");
    setSourceUri("0");
    setUsername("");
    setPassword("");
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
      const payload: CameraCreatePayload = {
        name: name.trim(),
        source_type: sourceType,
        source_uri: sourceUri.trim(),
        enabled,
        username: needsCreds && username ? username : null,
        password: needsCreds && password ? password : null,
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
        className="relative z-10 w-full max-w-lg rounded-xl border border-dark-700 bg-dark-800 shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-dark-700 px-5 py-4">
          <div>
            <h2
              id="add-camera-title"
              className="font-display text-lg font-semibold text-[var(--color-text-primary)]"
            >
              Adicionar câmera
            </h2>
            <p className="mt-0.5 flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
              <Lock className="h-3 w-3 text-emerald-400" />
              Credenciais criptografadas localmente (Fernet)
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
          <Field label="Nome">
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex.: Bebedouro quintal"
              className={inputClass}
            />
          </Field>

          <Field label="Tipo de fonte">
            <div className="grid grid-cols-3 gap-2">
              {SOURCE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    setSourceType(opt.value);
                    setSourceUri(opt.value === "usb" ? "0" : "");
                  }}
                  className={cn(
                    "rounded-lg border px-2 py-2 text-left text-xs transition",
                    sourceType === opt.value
                      ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-400"
                      : "border-dark-700 bg-dark-900 text-[var(--color-text-muted)]",
                  )}
                >
                  <span className="font-medium">{opt.label}</span>
                </button>
              ))}
            </div>
          </Field>

          <Field
            label={sourceType === "usb" ? "Índice USB" : "Endereço / URI"}
            hint={SOURCE_OPTIONS.find((o) => o.value === sourceType)?.hint}
          >
            <input
              required
              value={sourceUri}
              onChange={(e) => setSourceUri(e.target.value)}
              placeholder={sourceType === "usb" ? "0" : "rtsp://192.168.0.50:554/..."}
              className={inputClass}
              autoComplete="off"
            />
          </Field>

          {needsCreds ? (
            <div className="grid gap-3 sm:grid-cols-2">
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
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputClass}
                  autoComplete="new-password"
                />
              </Field>
            </div>
          ) : null}

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

          <div className="flex justify-end gap-2 border-t border-dark-700 pt-4">
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
              className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:opacity-60"
            >
              {submitting ? "Salvando…" : "Salvar câmera"}
            </button>
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
      {hint ? <span className="mt-1 block text-[11px] text-[var(--color-text-muted)]">{hint}</span> : null}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none transition placeholder:text-[var(--color-text-muted)]/60 focus:border-emerald-500/50";
