import { useEffect, useState } from "react";
import { AlertTriangle, LoaderCircle, X } from "lucide-react";

type Props = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  requiredText?: string;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  requiredText,
  busy = false,
  onCancel,
  onConfirm,
}: Props) {
  const [typedConfirmation, setTypedConfirmation] = useState("");
  useEffect(() => {
    if (open) setTypedConfirmation("");
  }, [open]);
  if (!open) return null;
  const canConfirm =
    !busy && (!requiredText || typedConfirmation === requiredText);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <button
        type="button"
        disabled={busy}
        className="absolute inset-0 bg-black/75"
        aria-label="Fechar confirmação"
        onClick={onCancel}
      />
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="relative z-10 w-full max-w-md rounded-xl border border-dark-700 bg-dark-800 p-5 shadow-2xl"
      >
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" />
          <div className="min-w-0 flex-1">
            <h2
              id="confirm-dialog-title"
              className="font-display text-base font-semibold text-[var(--color-text-primary)]"
            >
              {title}
            </h2>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">{message}</p>
          </div>
          <button
            type="button"
            aria-label="Cancelar"
            disabled={busy}
            onClick={onCancel}
            className="rounded-md p-1 text-[var(--color-text-muted)] hover:bg-dark-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {requiredText ? (
          <label className="mt-4 block text-xs text-[var(--color-text-muted)]">
            Digite <strong className="text-red-200">{requiredText}</strong> para
            confirmar
            <input
              value={typedConfirmation}
              onChange={(event) => setTypedConfirmation(event.target.value)}
              disabled={busy}
              autoComplete="off"
              className="mt-1 w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-red-400/60"
            />
          </label>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-lg border border-dark-600 px-3 py-2 text-sm text-[var(--color-text-muted)] hover:bg-dark-700 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!canConfirm}
            className="inline-flex items-center gap-2 rounded-lg bg-red-500 px-3 py-2 text-sm font-semibold text-white hover:bg-red-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
            {busy ? "Excluindo…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
