import { useState } from "react";
import {
  BrainCircuit,
  CheckCircle2,
  CircleDot,
  Clock,
  Database,
  GraduationCap,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  Zap,
} from "lucide-react";

import { usePolling } from "@/hooks/usePolling";
import {
  fetchActiveLearningStatus,
  getErrorMessage,
  optimizeCore,
} from "@/services/api";
import { cn } from "@/utils/cn";
import type { ActiveLearningStatus, FineTuneRun } from "@/types";

const RUN_LABELS: Record<string, string> = {
  queued: "Na fila",
  running: "Otimizando",
  completed: "Concluído",
  failed: "Falhou",
};

function runTone(status: string): string {
  if (status === "completed") return "text-emerald-300 border-emerald-400/30 bg-emerald-400/10";
  if (status === "failed") return "text-red-300 border-red-400/30 bg-red-400/10";
  if (status === "running") return "text-sky-300 border-sky-400/30 bg-sky-400/10";
  return "text-amber-200 border-amber-400/30 bg-amber-400/10";
}

function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function LastRun({ run }: { run: FineTuneRun }) {
  return (
    <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-primary)]">
          <Clock className="h-3.5 w-3.5 text-[var(--color-text-muted)]" />
          Última otimização
        </span>
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-[10px] font-medium",
            runTone(run.status),
          )}
        >
          {RUN_LABELS[run.status] ?? run.status}
        </span>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        {run.message || "Sem detalhes."}
      </p>
      <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-[var(--color-text-muted)]">
        <span className="rounded-full border border-dark-600 bg-dark-800 px-2 py-0.5">
          {run.samples} amostras
        </span>
        <span className="rounded-full border border-dark-600 bg-dark-800 px-2 py-0.5">
          {run.classes} classes
        </span>
        <span className="rounded-full border border-dark-600 bg-dark-800 px-2 py-0.5">
          {run.epochs} épocas · {run.imgsz}px
        </span>
        {run.finished_at ? (
          <span className="rounded-full border border-dark-600 bg-dark-800 px-2 py-0.5">
            {formatDate(run.finished_at)}
          </span>
        ) : null}
      </div>
      {run.status === "completed" ? (
        <p className="mt-2 flex items-center gap-1 text-[10px] text-emerald-300">
          <CheckCircle2 className="h-3 w-3" />
          O pipeline já está usando o modelo treinado.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Painel de **Aprendizado Ativo** do Bem-Te-Vi Core.
 *
 * Cada correção/confirmação do usuário vira uma amostra recortada na fila por
 * espécie. O botão "Otimizar Bem-Te-Vi Core com Novas Amostras" dispara um
 * fine-tuning incremental em segundo plano, sem bloquear a captura.
 */
export function ActiveLearningPanel() {
  const query = usePolling<ActiveLearningStatus>(
    () => fetchActiveLearningStatus(),
    30_000,
  );
  const [optimizing, setOptimizing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const status = query.data;
  const canOptimize =
    !!status &&
    status.enabled &&
    !status.running &&
    status.eligible_classes >= 2;

  const handleOptimize = async () => {
    setOptimizing(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const updated = await optimizeCore();
      query.setData(updated);
      setActionMessage(
        "Otimização iniciada em segundo plano. O progresso aparece aqui.",
      );
    } catch (error) {
      setActionError(
        getErrorMessage(error, "Falha ao iniciar a otimização do Core"),
      );
    } finally {
      setOptimizing(false);
    }
  };

  return (
    <article className="rounded-2xl border border-dark-700 bg-dark-800 p-5">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-400/25 bg-emerald-400/10">
            <GraduationCap className="h-5 w-5 text-emerald-300" />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-muted)]">
              Aprendizado ativo
            </p>
            <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
              Bem-Te-Vi Core adaptativo
            </h2>
            <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">
              Suas correções viram amostras cirúrgicas de treino — o modelo
              aprende com o seu jardim.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void query.refresh()}
          disabled={query.loading}
          className="rounded-lg border border-dark-600 bg-dark-900/60 p-1.5 text-[var(--color-text-muted)] transition hover:text-[var(--color-text-primary)] disabled:opacity-50"
          title="Atualizar o status"
          aria-label="Atualizar"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", query.loading && "animate-spin")} />
        </button>
      </header>

      {query.error ? (
        <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {query.error}
        </p>
      ) : null}
      {actionError ? (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {actionError}
        </p>
      ) : null}
      {actionMessage ? (
        <p className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          {actionMessage}
        </p>
      ) : null}

      {!status ? (
        <div className="mt-4 space-y-2">
          <div className="h-4 w-2/3 animate-pulse rounded bg-dark-700" />
          <div className="h-16 animate-pulse rounded-xl bg-dark-700" />
        </div>
      ) : (
        <>
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
              <p className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                <Database className="h-3 w-3" /> Amostras na fila
              </p>
              <p className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
                {status.total_samples}
              </p>
            </div>
            <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
              <p className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                <CircleDot className="h-3 w-3" /> Classes elegíveis
              </p>
              <p className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
                {status.eligible_classes}
                <span className="ml-1 text-[11px] font-normal text-[var(--color-text-muted)]">
                  / {status.min_samples}+ por espécie
                </span>
              </p>
            </div>
            <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
              <p className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                <BrainCircuit className="h-3 w-3" /> Modelo adaptado
              </p>
              <p className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
                {status.model_available ? "Ativo" : "Base"}
              </p>
              <p className="text-[10px] text-[var(--color-text-muted)]">
                {status.model_available
                  ? `${formatBytes(status.model_size_bytes)} · ${formatDate(status.model_trained_at)}`
                  : "YOLOv8n-cls de fábrica"}
              </p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void handleOptimize()}
              disabled={!canOptimize || optimizing}
              className="inline-flex items-center gap-2 rounded-lg border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Zap className={cn("h-3.5 w-3.5", (optimizing || status.running) && "animate-pulse")} />
              {status.running || optimizing
                ? "Otimizando Bem-Te-Vi Core…"
                : "Otimizar Bem-Te-Vi Core com Novas Amostras"}
            </button>
            <span className="text-[10px] text-[var(--color-text-muted)]">
              Fine-tuning incremental · roda em segundo plano
            </span>
          </div>

          {status.notes.length > 0 ? (
            <ul className="mt-3 space-y-1">
              {status.notes.map((note) => (
                <li
                  key={note}
                  className="flex items-start gap-1.5 rounded-lg border border-amber-400/20 bg-amber-400/5 px-2.5 py-1.5 text-[11px] text-amber-200"
                >
                  <TriangleAlert className="mt-0.5 h-3 w-3 shrink-0" />
                  {note}
                </li>
              ))}
            </ul>
          ) : null}

          {status.queue.length > 0 ? (
            <div className="mt-4">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
                <Sparkles className="h-3.5 w-3.5" />
                Fila por espécie
              </p>
              <ul className="mt-2 space-y-1.5">
                {status.queue.slice(0, 12).map((item) => {
                  const progress = Math.min(
                    100,
                    Math.round((item.samples / Math.max(1, status.min_samples)) * 100),
                  );
                  return (
                    <li
                      key={item.species_name}
                      className="rounded-lg border border-dark-700 bg-dark-900/60 px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2 text-[11px]">
                        <span className="flex min-w-0 items-center gap-1.5 text-[var(--color-text-primary)]">
                          {item.eligible ? (
                            <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-400" />
                          ) : (
                            <CircleDot className="h-3 w-3 shrink-0 text-[var(--color-text-muted)]" />
                          )}
                          <span className="truncate">{item.species_name}</span>
                        </span>
                        <span className="shrink-0 font-mono text-[var(--color-text-muted)]">
                          {item.samples}/{status.min_samples}
                        </span>
                      </div>
                      <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-dark-700">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            item.eligible ? "bg-emerald-400" : "bg-sky-400",
                          )}
                          style={{ width: `${Math.max(4, progress)}%` }}
                        />
                      </div>
                      {item.missing_files > 0 ? (
                        <p className="mt-1 text-[10px] text-amber-300">
                          {item.missing_files} arquivo(s) ausente(s) — serão
                          ignorados no treino.
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {status.last_run ? (
            <div className="mt-4">
              <LastRun run={status.last_run} />
            </div>
          ) : null}
        </>
      )}
    </article>
  );
}
