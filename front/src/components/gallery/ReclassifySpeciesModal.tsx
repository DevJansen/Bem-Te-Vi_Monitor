import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Image as ImageIcon,
  LoaderCircle,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import type { BirdSpecies, BirdVisit } from "@/types";
import { getErrorMessage, reclassifyVisitSpecies, resolveMediaUrl } from "@/services/api";
import { formatSpeciesLabel } from "@/utils/format";
import { resolveVisitSpeciesLabel } from "@/utils/visits";

type Props = {
  /** Visita a reclassificar (``null`` = modal fechado). */
  visit: BirdVisit | null;
  /** Catálogo local ("Minhas Aves") com as espécies candidatas. */
  species: BirdSpecies[];
  onClose: () => void;
  /** Recebe a visita já corrigida pelo backend. */
  onReclassified: (visit: BirdVisit) => void;
};

/**
 * Modal **"Associação Incorreta / Reclassificar"**.
 *
 * O observador aponta a espécie correta da ave. O backend:
 *
 * 1. reescreve a associação da visita (nome e dados exibidos no painel);
 * 2. grava o recorte tratado em ``app-data/fine_tuning/{espécie}/`` — o
 *    material local de retreinamento do Bem-Te-Vi Core;
 * 3. alimenta a fila de aprendizado ativo e a assinatura visual do indivíduo.
 */
export function ReclassifySpeciesModal({
  visit,
  species,
  onClose,
  onReclassified,
}: Props) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ao abrir, pré-seleciona a espécie atualmente associada à visita.
  useEffect(() => {
    if (!visit) return;
    setQuery("");
    setNotes("");
    setError(null);
    setSelectedId(visit.species_id ?? null);
  }, [visit]);

  // Fecha com Esc (sem confirmar).
  useEffect(() => {
    if (!visit) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [visit, onClose, saving]);

  const options = useMemo(() => {
    const termo = query.trim().toLocaleLowerCase("pt-BR");
    const lista = [...species].sort((a, b) =>
      a.common_name.localeCompare(b.common_name, "pt-BR"),
    );
    if (!termo) return lista;
    return lista.filter((item) =>
      `${item.common_name} ${item.scientific_name}`
        .toLocaleLowerCase("pt-BR")
        .includes(termo),
    );
  }, [species, query]);

  if (!visit) return null;

  const selected = species.find((item) => item.id === selectedId) ?? null;
  const currentLabel = resolveVisitSpeciesLabel(visit);
  const canSave = Boolean(selectedId) && !saving;

  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await reclassifyVisitSpecies(
        visit.id,
        selectedId,
        notes.trim() || null,
      );
      onReclassified(updated);
      onClose();
    } catch (cause) {
      setError(
        getErrorMessage(cause, "Não foi possível salvar a reclassificação."),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Fechar reclassificação"
        onClick={onClose}
        className="absolute inset-0 bg-black/80 backdrop-blur-sm"
      />

      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="reclassificar-title"
        className="relative z-10 flex max-h-[88vh] w-full max-w-lg animate-pop-in flex-col overflow-hidden rounded-2xl border border-cyan-500/25 bg-dark-800 shadow-[0_0_60px_-18px_rgba(34,211,238,0.55)]"
      >
        <header className="flex items-start gap-3 border-b border-dark-700 px-4 py-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cyan-500/15 text-cyan-300">
            <RefreshCw className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-300/90">
              <Sparkles className="h-3 w-3" />
              Bem-Te-Vi Core · Curadoria
            </p>
            <h2
              id="reclassificar-title"
              className="truncate font-display text-base font-semibold text-[var(--color-text-primary)]"
            >
              Associação incorreta? Reclassifique a ave
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Identificação atual:{" "}
              <span className="font-medium text-[var(--color-text-primary)]">
                {currentLabel}
              </span>
            </p>
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="rounded-md p-1 text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <label className="block text-xs text-[var(--color-text-muted)]">
            Buscar espécie do catálogo
            <span className="relative mt-1 block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--color-text-muted)]" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ex.: cardeal, sabiá, beija-flor…"
                autoFocus
                className="w-full rounded-lg border border-dark-700 bg-dark-900 py-2 pl-9 pr-3 text-sm text-[var(--color-text-primary)] outline-none focus:border-cyan-500/50"
              />
            </span>
          </label>

          <ul className="mt-3 max-h-64 space-y-1.5 overflow-y-auto pr-1">
            {options.length === 0 ? (
              <li className="rounded-lg border border-dashed border-dark-700 px-3 py-6 text-center text-xs text-[var(--color-text-muted)]">
                Nenhuma espécie encontrada no Catálogo Local. Cadastre a espécie
                em “Minhas Aves” antes de reclassificar.
              </li>
            ) : null}
            {options.map((item) => {
              const isSelected = item.id === selectedId;
              const isCurrent = item.id === visit.species_id;
              const reference = resolveMediaUrl(item.reference_image_url);
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    aria-pressed={isSelected}
                    className={`flex w-full items-center gap-3 rounded-lg border px-2.5 py-2 text-left transition ${
                      isSelected
                        ? "border-cyan-400/60 bg-cyan-500/10"
                        : "border-dark-700 bg-dark-900/50 hover:border-cyan-500/30 hover:bg-dark-800"
                    }`}
                  >
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-md border border-dark-700 bg-dark-900">
                      {reference ? (
                        <img
                          src={reference}
                          alt={item.common_name}
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <ImageIcon className="h-4 w-4 text-[var(--color-text-muted)]" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-[var(--color-text-primary)]">
                        {item.common_name}
                      </span>
                      <span className="block truncate text-xs italic text-[var(--color-text-muted)]">
                        {item.scientific_name}
                      </span>
                    </span>
                    {isCurrent ? (
                      <span className="shrink-0 rounded-md bg-dark-700 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-text-muted)]">
                        Atual
                      </span>
                    ) : null}
                    {isSelected ? (
                      <Check className="h-4 w-4 shrink-0 text-cyan-300" />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>

          <label className="mt-4 block text-xs text-[var(--color-text-muted)]">
            Observação (opcional)
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={2}
              placeholder="Ex.: era um sabiá-laranjeira, não um cardeal."
              className="mt-1 w-full resize-none rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-cyan-500/50"
            />
          </label>

          <p className="mt-3 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2 text-[11px] leading-snug text-cyan-100/80">
            O recorte tratado desta visita será salvo em{" "}
            <code className="font-mono">data/fine_tuning/</code> para
            aprimorar o modelo local do Bem-Te-Vi Core.
          </p>

          {error ? (
            <p role="alert" className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {error}
            </p>
          ) : null}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-dark-700 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-dark-600 px-3 py-2 text-sm text-[var(--color-text-muted)] transition hover:bg-dark-700 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={!canSave}
            title={
              selected
                ? `Associar ${formatSpeciesLabel(selected.common_name)} a esta visita`
                : "Escolha a espécie correta"
            }
            className="inline-flex items-center gap-2 rounded-lg bg-cyan-500 px-3.5 py-2 text-sm font-semibold text-dark-900 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {saving ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            {saving ? "Salvando…" : "Salvar correção"}
          </button>
        </footer>
      </section>
    </div>
  );
}
