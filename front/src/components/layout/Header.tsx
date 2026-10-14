import type { ReactNode } from "react";
import { Activity, Cpu, RefreshCw } from "lucide-react";
import type { AiStatus, Metrics } from "@/types";
import { formatDateTime } from "@/utils/format";
import { cn } from "@/utils/cn";

type Props = {
  title: string;
  subtitle?: string;
  metrics: Metrics | null;
  aiStatus: AiStatus;
  onRefresh?: () => void;
  refreshing?: boolean;
};

const AI_LABEL: Record<AiStatus, string> = {
  online: "IA online",
  degraded: "IA degradada",
  offline: "IA offline",
  loading: "IA carregando",
};

export function Header({
  title,
  subtitle,
  metrics,
  aiStatus,
  onRefresh,
  refreshing,
}: Props) {
  return (
    <header className="sticky top-0 z-30 border-b border-dark-700 bg-dark-900/90 backdrop-blur-md">
      <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4">
        <div>
          <h1 className="font-display text-xl font-semibold text-[var(--color-text-primary)]">
            {title}
          </h1>
          {subtitle ? (
            <p className="mt-0.5 text-sm text-[var(--color-text-muted)]">{subtitle}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <QuickStat
            icon={<Activity className="h-3.5 w-3.5" />}
            label="Hoje"
            value={metrics ? String(metrics.visits_today) : "—"}
          />
          <QuickStat
            icon={<Cpu className="h-3.5 w-3.5" />}
            label="Câmeras"
            value={
              metrics
                ? `${metrics.active_cameras}/${metrics.total_cameras}`
                : "—"
            }
          />
          <div
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium",
              aiStatus === "online" &&
                "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
              aiStatus === "degraded" &&
                "border-amber-500/40 bg-amber-500/10 text-amber-300",
              aiStatus === "offline" && "border-red-500/40 bg-red-500/10 text-red-300",
              aiStatus === "loading" &&
                "border-dark-700 bg-dark-800 text-[var(--color-text-muted)]",
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                aiStatus === "online" && "bg-emerald-400",
                aiStatus === "degraded" && "bg-amber-400",
                aiStatus === "offline" && "bg-red-400",
                aiStatus === "loading" && "bg-[var(--color-text-muted)] animate-pulse",
              )}
            />
            {AI_LABEL[aiStatus]}
          </div>

          {onRefresh ? (
            <button
              type="button"
              onClick={onRefresh}
              className="inline-flex items-center gap-1.5 rounded-lg border border-dark-700 bg-dark-800 px-3 py-1.5 text-xs text-[var(--color-text-muted)] transition hover:border-emerald-500/40 hover:text-emerald-400"
              title="Atualizar dados"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
              Atualizar
            </button>
          ) : null}
        </div>
      </div>
      {metrics?.last_visit_at ? (
        <p className="border-t border-dark-700/60 px-6 py-1.5 text-[11px] text-[var(--color-text-muted)]">
          Última visita: {formatDateTime(metrics.last_visit_at)}
        </p>
      ) : null}
    </header>
  );
}

function QuickStat({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dark-700 bg-dark-800 px-3 py-1.5">
      <span className="text-emerald-400">{icon}</span>
      <div className="leading-none">
        <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {label}
        </p>
        <p className="mt-0.5 text-sm font-semibold text-[var(--color-text-primary)]">
          {value}
        </p>
      </div>
    </div>
  );
}
