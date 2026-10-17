import { useEffect, useRef, useState } from "react";
import { BrainCircuit, ChevronDown, Terminal } from "lucide-react";
import { fetchAiLogs } from "@/services/api";
import type { AiLogEntry } from "@/types";
import { cn } from "@/utils/cn";

/** Máximo de linhas mantidas no terminal (buffer de exibição). */
const MAX_LINHAS = 200;

/**
 * "Logs Cognitivos da Alaris" — os pensamentos do motor em tempo real.
 *
 * Terminal elegante que exibe as mensagens dinâmicas do pipeline (detecção,
 * nitidez do frame, identificação de espécie, auto-calibração por clima,
 * anomalias). Cada pensamento é assinado com `[Alaris]`. Faz *polling
 * incremental* via `since_id` para trafegar apenas os eventos novos.
 * Alimenta-se de `GET /api/ai/logs`.
 */
export function AiStreamLog() {
  const [entries, setEntries] = useState<AiLogEntry[]>([]);
  const [connected, setConnected] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const lastIdRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const resp = await fetchAiLogs({
          limit: 80,
          sinceId: lastIdRef.current || undefined,
        });
        if (!active) return;
        setConnected(true);
        lastIdRef.current = Math.max(lastIdRef.current, resp.last_id);
        if (resp.entries.length > 0) {
          setEntries((prev) => [...prev, ...resp.entries].slice(-MAX_LINHAS));
        }
      } catch {
        if (active) setConnected(false);
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 2_000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!autoScroll) return;
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [entries, autoScroll]);

  return (
    <section
      aria-label="Logs cognitivos da Alaris"
      className="relative overflow-hidden rounded-xl border border-cyan-500/20 bg-[#050a08]"
    >
      <div className="flex items-center justify-between gap-2 border-b border-cyan-500/15 bg-cyan-500/[0.04] px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-cyan-300" aria-hidden />
          <h2 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
            Logs Cognitivos da Alaris
          </h2>
          <span className="hidden items-center gap-1 text-[10px] text-[var(--color-text-muted)] sm:inline-flex">
            <BrainCircuit className="h-3 w-3" />
            raciocínio em tempo real
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setAutoScroll((v) => !v)}
            className={cn(
              "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-medium transition",
              autoScroll
                ? "border-cyan-400/40 bg-cyan-500/10 text-cyan-300"
                : "border-dark-700 bg-dark-800 text-[var(--color-text-muted)]",
            )}
            title="Rolar automaticamente para as mensagens mais recentes"
          >
            <ChevronDown className="h-3 w-3" />
            Auto
          </button>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide",
              connected ? "text-emerald-400" : "text-red-300",
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                connected ? "bg-emerald-400 animate-pulse-soft" : "bg-red-400",
              )}
            />
            {connected ? "ao vivo" : "sem conexão"}
          </span>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="h-64 overflow-y-auto px-4 py-3 font-mono text-[12px] leading-relaxed"
      >
        {entries.length === 0 ? (
          <p className="text-[var(--color-text-muted)]">
            <span className="text-emerald-400">›</span> Aguardando a Alaris Core
            processar o stream
            <span className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-blink bg-emerald-400 align-middle" />
          </p>
        ) : (
          <ul className="space-y-0.5">
            {entries.map((entry) => (
              <LogLine key={entry.id} entry={entry} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

const LEVEL_STYLE: Record<
  string,
  { dot: string; text: string; label: string }
> = {
  info: { dot: "text-[var(--color-text-muted)]", text: "text-[var(--color-text-muted)]", label: "INFO" },
  analise: { dot: "text-cyan-300", text: "text-cyan-100", label: "ANÁLISE" },
  sucesso: { dot: "text-emerald-400", text: "text-emerald-200", label: "OK" },
  atencao: { dot: "text-amber-300", text: "text-amber-200", label: "ATENÇÃO" },
  alerta: { dot: "text-red-400", text: "text-red-200", label: "ALERTA" },
};

function LogLine({ entry }: { entry: AiLogEntry }) {
  const style = LEVEL_STYLE[entry.level] ?? LEVEL_STYLE.info;
  // Destaca a assinatura do motor: "[Alaris] restante da mensagem".
  const prefixo = "[Alaris]";
  const assinada = entry.message.startsWith(prefixo);
  const texto = assinada ? entry.message.slice(prefixo.length).trimStart() : entry.message;
  return (
    <li className="flex gap-2">
      <span className="shrink-0 text-[var(--color-text-muted)]/70">
        [{entry.hora}]
      </span>
      <span className={cn("shrink-0", style.dot)}>●</span>
      <span className={cn(style.text)}>
        {assinada ? (
          <span className="mr-1 font-semibold text-cyan-300">{prefixo}</span>
        ) : null}
        {texto}
      </span>
    </li>
  );
}
