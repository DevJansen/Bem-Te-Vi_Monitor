import { useEffect, useState, type FormEvent } from "react";
import { Bird, Bot, LoaderCircle, Plus, Trash2, X } from "lucide-react";
import type { BirdSpecies } from "@/types";
import { createSpecies, deleteSpecies, getErrorMessage, resolveMediaUrl } from "@/services/api";
import { BIRD_SILHOUETTE_DATA_URI } from "@/utils/speciesImage";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import {
  SpeciesProfileModal,
  type SpeciesRef,
} from "@/components/species/SpeciesProfileModal";
import { SpeciesAiConsultModal } from "@/components/species/SpeciesAiConsultModal";

type Props = {
  species: BirdSpecies[];
  loading: boolean;
  error: string | null;
  onCatalogChanged: () => void;
};

const inputClass =
  "mt-1 block w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-emerald-500/50";

/**
 * Miniatura da foto de referência do card.
 *
 * Normaliza a URL (caminho relativo → absoluto) e, se o arquivo estiver
 * ausente/corrompido, cai para a **silhueta padrão** do sistema — nunca deixa
 * um ícone de imagem quebrada.
 */
function ReferenceThumb({ url, name }: { url: string | null; name: string }) {
  const [failed, setFailed] = useState(false);
  const resolved = resolveMediaUrl(url);
  if (!resolved || failed) {
    return (
      <div className="relative h-full w-full">
        <img
          src={BIRD_SILHOUETTE_DATA_URI}
          alt="Silhueta padrão de pássaro"
          className="h-full w-full object-cover"
        />
        <span className="absolute inset-x-0 bottom-0 bg-dark-900/70 px-2 py-1 text-center text-[10px] text-[var(--color-text-muted)]">
          Sem foto de referência
        </span>
      </div>
    );
  }
  return (
    <img
      src={resolved}
      alt={`Foto de referência: ${name}`}
      onError={() => setFailed(true)}
      className="h-full w-full object-cover"
      loading="lazy"
    />
  );
}

export function SpeciesCatalog({
  species,
  loading,
  error: loadError,
  onCatalogChanged,
}: Props) {
  const [modalOpen, setModalOpen] = useState(false);
  const [commonName, setCommonName] = useState("");
  const [scientificName, setScientificName] = useState("");
  const [description, setDescription] = useState("");
  const [referenceImage, setReferenceImage] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingSpecies, setDeletingSpecies] = useState<BirdSpecies | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  // Espécie aberta na ficha técnica (null = modal fechado).
  const [selected, setSelected] = useState<SpeciesRef | null>(null);
  // Espécie aberta na ficha ornitológica da IA externa (null = fechado).
  const [consultSpecies, setConsultSpecies] = useState<BirdSpecies | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 3500);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  const resetForm = () => {
    setCommonName("");
    setScientificName("");
    setDescription("");
    setReferenceImage(null);
    setFormError(null);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await createSpecies({
        common_name: commonName.trim(),
        scientific_name: scientificName.trim(),
        description: description.trim(),
        reference_image: referenceImage,
      });
      resetForm();
      setModalOpen(false);
      setToast("Espécie cadastrada no catálogo local.");
      onCatalogChanged();
    } catch (cause) {
      setFormError(getErrorMessage(cause, "Não foi possível cadastrar a espécie."));
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async () => {
    if (!deletingSpecies) return;
    setDeleting(true);
    setActionError(null);
    try {
      await deleteSpecies(deletingSpecies.id);
      setDeletingSpecies(null);
      setToast("Espécie removida do catálogo.");
      onCatalogChanged();
    } catch (cause) {
      setActionError(getErrorMessage(cause, "Não foi possível excluir a espécie."));
      setDeletingSpecies(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
            Catálogo local de aves
          </h2>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            {species.length} espécie(s) cadastrada(s), armazenadas somente neste computador.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            resetForm();
            setModalOpen(true);
          }}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400"
        >
          <Plus className="h-4 w-4" />
          Cadastrar Nova Ave
        </button>
      </div>

      {loadError || actionError ? (
        <p role="alert" className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {loadError ?? actionError}
        </p>
      ) : null}

      {loading && species.length === 0 ? (
        <p className="text-sm text-[var(--color-text-muted)]">Carregando catálogo…</p>
      ) : species.length === 0 ? (
        <div className="rounded-xl border border-dashed border-dark-700 px-6 py-12 text-center">
          <Bird className="mx-auto h-8 w-8 text-emerald-400" />
          <p className="mt-3 text-sm text-[var(--color-text-muted)]">
            Seu catálogo ainda está vazio. Cadastre as aves comuns na sua região.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {species.map((item) => (
            <article
              key={item.id}
              className="relative overflow-hidden rounded-xl border border-dark-700 bg-dark-800 transition-colors hover:border-emerald-500/40"
            >
              {/* Card inteiro clicável: abre a ficha técnica completa. */}
              <button
                type="button"
                onClick={() =>
                  setSelected({
                    id: item.id,
                    common_name: item.common_name,
                    scientific_name: item.scientific_name,
                    description: item.description,
                  })
                }
                aria-label={`Abrir ficha técnica de ${item.common_name}`}
                title="Ver ficha técnica completa"
                className="absolute inset-0 z-10 cursor-pointer"
              />
              <div className="aspect-[4/3] bg-dark-900">
                <ReferenceThumb
                  url={item.reference_image_url}
                  name={item.common_name}
                />
              </div>
              <div className="space-y-2 p-4">
                <h3 className="font-medium text-[var(--color-text-primary)]">
                  {item.common_name}
                </h3>
                <p className="text-sm italic text-emerald-300">
                  {item.scientific_name}
                </p>
                {item.ecological_badge ? (
                  <span
                    className={
                      "inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold " +
                      (item.ecological_status === "rara"
                        ? "border-amber-400/40 bg-amber-400/15 text-amber-300"
                        : item.ecological_status === "endemica"
                          ? "border-sky-400/30 bg-sky-400/10 text-sky-300"
                          : item.ecological_status === "migratoria"
                            ? "border-yellow-400/30 bg-yellow-400/10 text-yellow-300"
                            : item.ecological_status === "exotica"
                              ? "border-orange-400/30 bg-orange-400/10 text-orange-300"
                              : "border-emerald-500/25 bg-emerald-500/10 text-emerald-300")
                    }
                    title={`Status ecológico regional: ${item.ecological_status_label ?? ""}`}
                  >
                    {item.ecological_badge}
                  </span>
                ) : null}
                {item.description ? (
                  <p className="line-clamp-3 text-xs leading-relaxed text-[var(--color-text-muted)]">
                    {item.description}
                  </p>
                ) : null}
                <div className="flex flex-wrap items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setConsultSpecies(item)}
                    title="Perguntar à IA externa (nome científico, família, conservação, dieta, habitat, curiosidades)"
                    className="relative z-20 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-violet-200 transition hover:bg-violet-500/10"
                  >
                    <Bot className="h-3.5 w-3.5" />
                    Ficha IA
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeletingSpecies(item)}
                    className="relative z-20 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-300 transition hover:bg-red-500/10"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Excluir espécie
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      {modalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/70"
            aria-label="Fechar cadastro"
            disabled={saving}
            onClick={() => setModalOpen(false)}
          />
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="species-modal-title"
            className="relative z-10 w-full max-w-lg rounded-xl border border-dark-700 bg-dark-800 shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-dark-700 px-5 py-4">
              <div>
                <h2
                  id="species-modal-title"
                  className="font-display text-lg font-semibold text-[var(--color-text-primary)]"
                >
                  Cadastrar Nova Ave
                </h2>
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  Os dados e a foto ficam armazenados localmente.
                </p>
              </div>
              <button
                type="button"
                aria-label="Fechar"
                disabled={saving}
                onClick={() => setModalOpen(false)}
                className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-dark-700"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={(event) => void submit(event)} className="space-y-4 px-5 py-4">
              <label className="block text-xs text-[var(--color-text-muted)]">
                Nome popular
                <input
                  required
                  maxLength={120}
                  value={commonName}
                  onChange={(event) => setCommonName(event.target.value)}
                  placeholder="Ex.: Beija-flor-de-papo-branco"
                  className={inputClass}
                />
              </label>
              <label className="block text-xs text-[var(--color-text-muted)]">
                Nome científico
                <input
                  required
                  maxLength={160}
                  value={scientificName}
                  onChange={(event) => setScientificName(event.target.value)}
                  placeholder="Ex.: Amazilia versicolor"
                  className={inputClass}
                />
              </label>
              <label className="block text-xs text-[var(--color-text-muted)]">
                Observações ou características
                <textarea
                  maxLength={4000}
                  rows={3}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Descrição, comportamento ou características para identificação."
                  className={inputClass}
                />
              </label>
              <label className="block text-xs text-[var(--color-text-muted)]">
                Foto de referência (opcional, máximo 8 MB)
                <input
                  type="file"
                  accept="image/*"
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null;
                    setReferenceImage(file);
                    if (file && file.size > 8 * 1024 * 1024) {
                      setFormError("A foto de referência deve ter no máximo 8 MB.");
                    } else {
                      setFormError(null);
                    }
                  }}
                  className={`${inputClass} file:mr-3 file:rounded-md file:border-0 file:bg-emerald-500/15 file:px-2 file:py-1 file:text-xs file:text-emerald-300`}
                />
              </label>
              {formError ? (
                <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                  {formError}
                </p>
              ) : null}
              <div className="flex justify-end gap-2 border-t border-dark-700 pt-4">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => setModalOpen(false)}
                  className="rounded-lg border border-dark-700 px-4 py-2 text-sm text-[var(--color-text-muted)] hover:bg-dark-700"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={saving || (referenceImage?.size ?? 0) > 8 * 1024 * 1024}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:opacity-60"
                >
                  {saving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
                  {saving ? "Salvando…" : "Salvar espécie"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      <SpeciesProfileModal
        species={selected}
        onClose={() => setSelected(null)}
      />

      {/* Ficha ornitológica da IA externa (consulta profunda da espécie). */}
      <SpeciesAiConsultModal
        species={
          consultSpecies
            ? {
                id: consultSpecies.id,
                common_name: consultSpecies.common_name,
                scientific_name: consultSpecies.scientific_name,
                image_url: consultSpecies.reference_image_url,
              }
            : null
        }
        onClose={() => setConsultSpecies(null)}
      />

      <ConfirmDialog
        open={deletingSpecies !== null}
        title="Excluir espécie do catálogo?"
        message={
          deletingSpecies
            ? `Deseja realmente remover ${deletingSpecies.common_name}? Os registros de visitas existentes serão mantidos, mas perderão a associação ao catálogo.`
            : ""
        }
        confirmLabel="Excluir espécie"
        busy={deleting}
        onCancel={() => setDeletingSpecies(null)}
        onConfirm={() => void confirmDelete()}
      />

      {toast ? (
        <p role="status" className="fixed bottom-5 right-5 z-50 rounded-lg border border-emerald-500/30 bg-emerald-950 px-4 py-3 text-sm text-emerald-300 shadow-xl">
          {toast}
        </p>
      ) : null}
    </section>
  );
}
