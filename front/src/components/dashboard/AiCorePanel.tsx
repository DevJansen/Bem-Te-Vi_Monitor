import {
  Activity,
  BrainCircuit,
  CircuitBoard,
  Cpu,
  Gauge,
  MemoryStick,
  Radio,
  Sparkles,
  Timer,
  Zap,
} from "lucide-react";
import type { ReactNode } from "react";
import { usePolling } from "@/hooks/usePolling";
import { fetchAiStatus } from "@/services/api";
import { cn } from "@/utils/cn";

/**
 * "AI Core" — o coração pulsante da IA, visível em tempo real.
 *
 * Widget futurista (Dark Mode + neon) que evidencia que uma rede neural está
 * processando o stream: estado ao vivo, FPS, latência da inferência, modelo em
 * uso e uso de recursos. Alimenta-se de `GET /api/ai/status`.
 */
export function AiCorePanel() {
  const query = usePolling(fetchAiStatus, 2_500);
  const data = query.data;
  const online = Boolean(data) && !query.error;

  const engine = data?.engine;
  const throughput = data?.throughput;
  const performance = data?.performance;
  const resources = data?.resources;

  const backendLabel = engine?.backend
    ? BACKEND_LABELS[engine.backend] ?? engine.backend
    : "—";

  return (
    <section
      aria-label="Bem-Te-Vi Core"
      className="relative overflow-hidden rounded-xl border border-emerald-500/25 bg-gradient-to-br from-dark-800 via-dark-800 to-dark-900"
    >
      {/* Brilho radial decorativo + linha de varredura (processamento neural). */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 12% 20%, rgba(16,185,129,0.14), transparent 45%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-16 animate-scan-line bg-gradient-to-b from-transparent via-emerald-400/10 to-transparent"
      />

      <div className="relative flex flex-col gap-4 p-4 lg:flex-row lg:items-center lg:gap-6">
        {/* Núcleo pulsante */}
        <div className="flex items-center gap-4">
          <div className="relative grid h-20 w-20 shrink-0 place-items-center">
            <span
              aria-hidden
              className={cn(
                "absolute inset-0 rounded-full border border-emerald-400/50",
                online && "animate-pulse-ring",
              )}
            />
            <span
              aria-hidden
              className={cn(
                "absolute inset-0 rounded-full border border-cyan-400/40",
                online && "animate-pulse-ring [animation-delay:0.8s]",
              )}
            />
            <span
              className={cn(
                "relative grid h-16 w-16 place-items-center rounded-full border bg-dark-900",
                online
                  ? "border-emerald-400/60 animate-core-glow"
                  : "border-dark-700",
              )}
            >
              <BrainCircuit
                className={cn(
                  "h-7 w-7",
                  online ? "text-emerald-300" : "text-[var(--color-text-muted)]",
                )}
                aria-hidden
              />
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
                Bem-Te-Vi Core
              </h2>
              <span className="inline-flex items-center gap-1 rounded-full border border-violet-400/40 bg-violet-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-300">
                <Sparkles className="h-3 w-3" />
                Powered by Bem-Te-Vi Core
              </span>
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                  online
                    ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                    : "border-red-400/40 bg-red-500/10 text-red-300",
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    online ? "bg-emerald-400 animate-pulse-soft" : "bg-red-400",
                  )}
                />
                {online ? "Bem-Te-Vi Core ativo" : "Bem-Te-Vi Core indisponível"}
              </span>
            </div>
            <p className="mt-0.5 text-sm text-[var(--color-text-muted)]">
              {engine?.state ?? "Conectando ao Bem-Te-Vi Core…"}
            </p>
            <p className="mt-0.5 font-mono text-[11px] text-emerald-300/80">
              {engine?.model ?? "—"} · {backendLabel} · {engine?.device ?? "—"}
            </p>
          </div>
        </div>

        {/* Métricas ao vivo */}
        <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
          <Metric
            icon={<Gauge className="h-3.5 w-3.5" />}
            label="FPS"
            value={throughput ? formatNumber(throughput.fps, 1) : "—"}
            tone="emerald"
          />
          <Metric
            icon={<Timer className="h-3.5 w-3.5" />}
            label="Latência"
            value={
              performance ? `${formatNumber(performance.latency_ms_last, 1)} ms` : "—"
            }
            hint={
              performance && performance.samples > 0
                ? `média ${formatNumber(performance.latency_ms_avg, 1)} ms`
                : undefined
            }
          />
          <Metric
            icon={<Zap className="h-3.5 w-3.5" />}
            label="Inferências hoje"
            value={
              throughput ? formatNumber(throughput.inferences_today, 0) : "—"
            }
            hint={
              throughput
                ? `${formatNumber(throughput.detections_today, 0)} detecções`
                : undefined
            }
          />
          <Metric
            icon={<Activity className="h-3.5 w-3.5" />}
            label="Limiar (conf)"
            value={
              engine?.confidence != null
                ? formatNumber(engine.confidence, 2)
                : "—"
            }
          />
          <Metric
            icon={<CircuitBoard className="h-3.5 w-3.5" />}
            label="Modelo"
            value={engine?.model ? engine.model.replace(/\.(pt|onnx|engine)$/i, "") : "—"}
            hint={engine?.imgsz ? `${engine.imgsz}px` : undefined}
          />
          <Metric
            icon={<Radio className="h-3.5 w-3.5" />}
            label="Câmeras"
            value={
              data ? `${data.cameras_online}/${data.cameras_enabled}` : "—"
            }
            hint="online/ativas"
          />
          <Metric
            icon={<Cpu className="h-3.5 w-3.5" />}
            label="CPU"
            value={
              resources?.cpu_percent != null
                ? `${formatNumber(resources.cpu_percent, 1)}%`
                : "—"
            }
          />
          <Metric
            icon={<MemoryStick className="h-3.5 w-3.5" />}
            label="Memória"
            value={
              resources?.memory_mb != null
                ? `${formatNumber(resources.memory_mb, 0)} MB`
                : "—"
            }
            hint={
              resources?.memory_percent != null
                ? `${formatNumber(resources.memory_percent, 1)}%`
                : undefined
            }
          />
        </div>
      </div>

      {/* Rodapé: backend/aceleração + tempo de atividade. */}
      <div className="relative flex flex-wrap items-center justify-between gap-2 border-t border-dark-700/60 px-4 py-2 text-[11px] text-[var(--color-text-muted)]">
        <span className="inline-flex items-center gap-1.5">
          <Zap className="h-3 w-3 text-emerald-400/80" />
          {engine?.notes && engine.notes.length > 0
            ? engine.notes.join(" · ")
            : "Bem-Te-Vi Core — inferência Edge AI (YOLOv8)"}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Timer className="h-3 w-3" />
          Ativo há {data ? formatUptime(data.uptime_seconds) : "—"}
          {throughput
            ? ` · ${formatNumber(throughput.inferences_total, 0)} inferências totais`
            : ""}
        </span>
      </div>
    </section>
  );
}

const BACKEND_LABELS: Record<string, string> = {
  tensorrt: "TensorRT",
  onnx: "ONNX Runtime",
  pytorch: "PyTorch",
};

const TONES: Record<string, string> = {
  emerald: "text-emerald-300",
  default: "text-[var(--color-text-primary)]",
};

function Metric({
  icon,
  label,
  value,
  hint,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint?: string;
  tone?: "emerald" | "default";
}) {
  return (
    <div className="rounded-lg border border-dark-700/70 bg-dark-900/50 px-2.5 py-2">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">
        <span className="text-emerald-400/80">{icon}</span>
        {label}
      </div>
      <p
        className={cn(
          "mt-0.5 font-mono text-sm font-semibold",
          TONES[tone] ?? TONES.default,
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="text-[10px] text-[var(--color-text-muted)]">{hint}</p>
      ) : null}
    </div>
  );
}

/** Formata um número com separador de milhar pt-BR e casas decimais fixas. */
function formatNumber(value: number, decimals: number): string {
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Converte segundos em um texto curto de tempo de atividade (ex.: "2h 14min"). */
function formatUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "instantes";
  const total = Math.floor(seconds);
  const dias = Math.floor(total / 86_400);
  const horas = Math.floor((total % 86_400) / 3_600);
  const minutos = Math.floor((total % 3_600) / 60);
  if (dias > 0) return `${dias}d ${horas}h`;
  if (horas > 0) return `${horas}h ${minutos}min`;
  if (minutos > 0) return `${minutos}min`;
  return `${total}s`;
}
