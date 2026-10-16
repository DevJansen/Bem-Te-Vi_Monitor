import { Check, Sparkles } from "lucide-react";
import { useState } from "react";
import { acknowledgeAnomaly, listAnomalies } from "@/services/api";
import { usePolling } from "@/hooks/usePolling";

/**
 * Painel de anomalias acústico-visuais (uso científico/conservação).
 *
 * Mostra os eventos raros ainda não reconhecidos — em especial o
 * **reaparecimento de uma espécie** que não era registrada há meses. Quando não
 * há nada pendente, o painel não é renderizado (não ocupa espaço no Painel).
 */
export function AnomalyAlertsPanel() {
  const query = usePolling(
    () => listAnomalies({ limit: 20, onlyPending: true }),
    60_000,
  );
  const [reconhecendo, setReconhecendo] = useState<string | null>(null);

  const lista = query.data ?? [];

  if (query.loading && lista.length === 0) return null;
  if (lista.length === 0) return null;

  async function reconhecer(id: string) {
    setReconhecendo(id);
    try {
      await acknowledgeAnomaly(id);
      await query.refresh();
    } finally {
      setReconhecendo(null);
    }
  }

  return (
    <section
      aria-label="Alertas de anomalias"
      className="rounded-xl border border-amber-400/40 bg-amber-500/10 px-4 py-3"
    >
      <div className="mb-2 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-amber-300" aria-hidden />
        <h2 className="text-sm font-semibold text-amber-200">
          Alertas de anomalias
        </h2>
        <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-[10px] font-semibold text-amber-200">
          {lista.length} pendente(s)
        </span>
      </div>
      <ul className="space-y-2">
        {lista.map((item) => (
          <li
            key={item.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-400/20 bg-dark-900/40 px-3 py-2"
          >
            <div>
              <p className="text-sm font-medium text-[var(--color-text-primary)]">
                {item.message}
              </p>
              <p className="text-xs text-[var(--color-text-muted)]">
                {item.species}
                {item.scientific_name ? ` · ${item.scientific_name}` : ""}
                {item.days_absent ? ` · ${item.days_absent} dias ausente` : ""}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void reconhecer(item.id)}
              disabled={reconhecendo === item.id}
              className="inline-flex items-center gap-1 rounded-md border border-amber-400/40 px-2.5 py-1 text-xs font-semibold text-amber-200 transition hover:bg-amber-400/15 disabled:opacity-60"
            >
              <Check className="h-3.5 w-3.5" />
              Reconhecer
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
