import { useCallback, useEffect, useState } from "react";
import { Bell, LoaderCircle, Plus, Trash2 } from "lucide-react";
import { api, getErrorMessage } from "@/services/api";

type SmartAlertRule = {
  id: string;
  name: string;
  enabled: boolean;
  conditions: Array<{ field: string; operator: string; value: unknown }>;
  description?: string;
};

type SmartAlertsResponse = {
  rules: SmartAlertRule[];
};

const FIELD_OPTIONS = [
  { value: "species_is_new", label: "Espécie nova" },
  { value: "species_is_rare", label: "Espécie rara" },
  { value: "sharpness_min", label: "Nitidez mínima" },
  { value: "confidence_min", label: "Confiança mínima" },
  { value: "garden_id", label: "Jardim específico" },
  { value: "visitor_kind", label: "Tipo de visitante" },
  { value: "has_individual", label: "Indivíduo recorrente" },
];

const OPERATOR_OPTIONS = [
  { value: "eq", label: "=" },
  { value: "ne", label: "≠" },
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "contains", label: "contém" },
  { value: "in", label: "em lista" },
];

export function SmartAlertsPanel() {
  const [rules, setRules] = useState<SmartAlertRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newField, setNewField] = useState("species_is_new");
  const [newOp, setNewOp] = useState("eq");
  const [newVal, setNewVal] = useState("true");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<SmartAlertsResponse>("/settings/smart-alerts");
      setRules(data.rules ?? []);
    } catch (cause) {
      setError(getErrorMessage(cause, "Não foi possível carregar as regras de alerta."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (id: string) => {
    try {
      const { data } = await api.patch<{ rule: SmartAlertRule }>(
        `/settings/smart-alerts/${id}/toggle`,
      );
      setRules((current) =>
        current.map((r) => (r.id === id ? data.rule : r)),
      );
    } catch (cause) {
      setError(getErrorMessage(cause, "Não foi possível alternar a regra."));
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/settings/smart-alerts/${id}`);
      setRules((current) => current.filter((r) => r.id !== id));
      setNotice("Regra removida.");
    } catch (cause) {
      setError(getErrorMessage(cause, "Não foi possível remover a regra."));
    }
  };

  const create = async () => {
    setCreating(true);
    setError(null);
    try {
      let value: unknown = newVal;
      if (newField === "species_is_new" || newField === "species_is_rare" || newField === "has_individual") {
        value = newVal === "true";
      } else if (newField === "sharpness_min" || newField === "confidence_min") {
        value = Number(newVal);
      }
      const { data } = await api.post<{ rule: SmartAlertRule }>(
        "/settings/smart-alerts",
        {
          name: newName || "Nova regra",
          conditions: [{ field: newField, operator: newOp, value }],
        },
      );
      setRules((current) => [...current, data.rule]);
      setNewName("");
      setNotice("Regra criada.");
    } catch (cause) {
      setError(getErrorMessage(cause, "Não foi possível criar a regra."));
    } finally {
      setCreating(false);
    }
  };

  return (
    <section className="space-y-4 rounded-xl border border-dark-700 bg-dark-800 p-4">
      <div className="flex items-center gap-3">
        <span className="rounded-xl bg-amber-500/15 p-2.5 text-amber-300">
          <Bell className="h-5 w-5" />
        </span>
        <div>
          <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
            Regras de Alerta Personalizadas (Smart Alerts)
          </h2>
          <p className="text-xs text-[var(--color-text-muted)]">
            Configure condições para enviar ou suprimir notificações Telegram/Discord
          </p>
        </div>
      </div>

      {error ? (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          {notice}
        </p>
      ) : null}

      {loading ? (
        <p className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Carregando regras…
        </p>
      ) : (
        <ul className="space-y-2">
          {rules.map((rule) => (
            <li
              key={rule.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-dark-700 bg-dark-900/60 px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-[var(--color-text-primary)]">
                  {rule.name}
                </p>
                <p className="text-[10px] text-[var(--color-text-muted)]">
                  {rule.conditions.length === 0
                    ? "Sem condições (sempre notifica)"
                    : rule.conditions
                        .map((c) => `${c.field} ${c.operator} ${c.value}`)
                        .join(" E ")}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void toggle(rule.id)}
                  className={`rounded-full px-2.5 py-1 text-[10px] font-semibold transition ${
                    rule.enabled
                      ? "bg-emerald-500/20 text-emerald-300"
                      : "bg-dark-700 text-[var(--color-text-muted)]"
                  }`}
                >
                  {rule.enabled ? "Ligado" : "Desligado"}
                </button>
                <button
                  type="button"
                  onClick={() => void remove(rule.id)}
                  aria-label="Remover regra"
                  className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:bg-red-500/10 hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
          {rules.length === 0 ? (
            <p className="text-xs text-[var(--color-text-muted)]">
              Nenhuma regra configurada. A regra padrão notifica todas as visitas de aves.
            </p>
          ) : null}
        </ul>
      )}

      {/* Criar nova regra */}
      <div className="space-y-2 rounded-lg border border-dashed border-dark-700 bg-dark-900/40 p-3">
        <p className="text-xs font-semibold text-[var(--color-text-primary)]">
          Nova regra
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs text-[var(--color-text-muted)]">
            Nome
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Ex: Apenas nitidez alta"
              className="mt-1 block w-40 rounded-lg border border-dark-700 bg-dark-900 px-2 py-1.5 text-sm text-[var(--color-text-primary)] outline-none focus:border-amber-500/50"
            />
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            Campo
            <select
              value={newField}
              onChange={(e) => setNewField(e.target.value)}
              className="mt-1 block rounded-lg border border-dark-700 bg-dark-900 px-2 py-1.5 text-sm text-[var(--color-text-primary)] outline-none focus:border-amber-500/50"
            >
              {FIELD_OPTIONS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            Operador
            <select
              value={newOp}
              onChange={(e) => setNewOp(e.target.value)}
              className="mt-1 block rounded-lg border border-dark-700 bg-dark-900 px-2 py-1.5 text-sm text-[var(--color-text-primary)] outline-none focus:border-amber-500/50"
            >
              {OPERATOR_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-[var(--color-text-muted)]">
            Valor
            <input
              value={newVal}
              onChange={(e) => setNewVal(e.target.value)}
              placeholder="true / 350 / cam1"
              className="mt-1 block w-24 rounded-lg border border-dark-700 bg-dark-900 px-2 py-1.5 text-sm text-[var(--color-text-primary)] outline-none focus:border-amber-500/50"
            />
          </label>
          <button
            type="button"
            onClick={() => void create()}
            disabled={creating}
            className="inline-flex items-center gap-2 rounded-lg border border-amber-400/40 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/25 disabled:cursor-wait disabled:opacity-60"
          >
            {creating ? (
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            Criar regra
          </button>
        </div>
      </div>
    </section>
  );
}