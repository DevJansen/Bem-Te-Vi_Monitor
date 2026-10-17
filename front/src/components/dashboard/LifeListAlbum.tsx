import { useState } from "react";
import { Bird, LockKeyhole } from "lucide-react";
import type { LifeListSpecies, RarityTier } from "@/types";
import { formatDateTime } from "@/utils/format";
import { cn } from "@/utils/cn";
import {
  SpeciesProfileModal,
  type SpeciesRef,
} from "@/components/species/SpeciesProfileModal";

type Props = {
  species: LifeListSpecies[];
};

/**
 * Estilo visual por raridade — bordas em dourado (Rara), prata (Incomum) e
 * bronze (Comum), seguindo a metáfora de "álbum de figurinhas".
 */
const RARITY_STYLES: Record<RarityTier, { card: string; chip: string }> = {
  Rara: {
    card: "border-amber-400/70 shadow-[0_0_24px_-6px_rgba(251,191,36,0.6)]",
    chip: "border-amber-400/40 bg-amber-400/15 text-amber-200",
  },
  Incomum: {
    card: "border-slate-300/60 shadow-[0_0_20px_-8px_rgba(226,232,240,0.45)]",
    chip: "border-slate-300/40 bg-slate-300/15 text-slate-100",
  },
  Comum: {
    card: "border-orange-700/70",
    chip: "border-orange-500/40 bg-orange-500/15 text-orange-200",
  },
  "Não observada": {
    card: "border-dark-700",
    chip: "border-dark-700 bg-dark-900 text-[var(--color-text-muted)]",
  },
};

/**
 * Álbum de Conquistas (Life List) gamificado: barra de progresso de descobertas
 * e cards estilo figurinha, com destaque de raridade para as aves desbloqueadas
 * e silhueta com cadeado para as ainda não observadas.
 */
export function LifeListAlbum({ species }: Props) {
  const total = species.length;
  const unlocked = species.filter((item) => item.is_unlocked).length;
  const percentage = total > 0 ? Math.round((unlocked / total) * 100) : 0;
  // Espécie aberta na ficha técnica (null = modal fechado).
  const [selected, setSelected] = useState<SpeciesRef | null>(null);

  return (
    <section className="space-y-5">
      {/* Barra de progresso das descobertas */}
      <div className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
              Álbum de Conquistas
            </h2>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              {unlocked} de {total} espécies descobertas · {percentage}% concluído
            </p>
          </div>
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300">
            {unlocked}/{total} espécies
          </span>
        </div>

        <div
          className="relative mt-4 h-3 overflow-hidden rounded-full bg-dark-900"
          role="progressbar"
          aria-valuenow={percentage}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Progresso de descobertas do álbum"
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-600 via-emerald-400 to-teal-300 transition-[width] duration-700 ease-out"
            style={{ width: `${percentage}%` }}
          />
          {/* Brilho animado sobre a barra preenchida */}
          <div
            className="pointer-events-none absolute inset-y-0 left-0 overflow-hidden"
            style={{ width: `${percentage}%` }}
          >
            <div className="h-full w-1/3 animate-shimmer bg-gradient-to-r from-transparent via-white/30 to-transparent" />
          </div>
        </div>
      </div>

      {/* Cards estilo figurinha */}
      {total === 0 ? (
        <div className="rounded-xl border border-dashed border-dark-700 px-6 py-12 text-center">
          <Bird className="mx-auto h-8 w-8 text-emerald-400" />
          <p className="mt-3 text-sm text-[var(--color-text-muted)]">
            Seu álbum está vazio. Cadastre espécies em “Minhas Aves” para começar
            a colecionar.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {species.map((item, index) => {
            const style = RARITY_STYLES[item.rarity];
            const imageUrl =
              item.best_photo_url ??
              item.featured_photo_url ??
              item.reference_image_url;
            return (
              <article
                key={item.id}
                style={{ animationDelay: `${Math.min(index, 12) * 45}ms` }}
                className={cn(
                  "group relative animate-pop-in overflow-hidden rounded-2xl border bg-dark-800 transition-transform duration-300 hover:-translate-y-1",
                  item.is_unlocked ? style.card : "border-dark-700",
                )}
              >
                {/* Card inteiro clicável: abre a ficha técnica da espécie. */}
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
                <div className="relative aspect-[4/3] overflow-hidden bg-dark-900">
                  {imageUrl ? (
                    <img
                      src={imageUrl}
                      alt={
                        item.is_unlocked
                          ? `Registro de ${item.common_name}`
                          : `Silhueta de ${item.common_name}`
                      }
                      className={cn(
                        "h-full w-full object-cover transition-transform duration-500",
                        item.is_unlocked
                          ? "group-hover:scale-105"
                          : "scale-105 grayscale opacity-25",
                      )}
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center">
                      <Bird
                        aria-hidden
                        className={cn(
                          "h-16 w-16",
                          item.is_unlocked
                            ? "text-emerald-400/60"
                            : "text-[var(--color-text-muted)]/25",
                        )}
                      />
                    </div>
                  )}

                  {/* Cadeado das aves ainda não descobertas */}
                  {!item.is_unlocked ? (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/25">
                      <LockKeyhole className="h-7 w-7 text-white/70" />
                    </div>
                  ) : null}

                  {/* Selo de raridade */}
                  <span
                    className={cn(
                      "absolute left-3 top-3 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide backdrop-blur",
                      item.is_unlocked
                        ? style.chip
                        : "border-white/10 bg-dark-900/80 text-[var(--color-text-muted)]",
                    )}
                  >
                    {item.is_unlocked ? item.rarity : "Bloqueada"}
                  </span>
                </div>

                <div className="space-y-2 p-4">
                  <div>
                    <h3 className="font-medium text-[var(--color-text-primary)]">
                      {item.common_name}
                    </h3>
                    <p className="text-xs italic text-emerald-300">
                      {item.scientific_name}
                    </p>
                    {item.ecological_badge ? (
                      <span
                        className={cn(
                          "mt-1.5 inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                          item.ecological_status === "rara"
                            ? "border-amber-400/40 bg-amber-400/15 text-amber-300"
                            : item.ecological_status === "endemica"
                              ? "border-sky-400/30 bg-sky-400/10 text-sky-300"
                              : item.ecological_status === "migratoria"
                                ? "border-yellow-400/30 bg-yellow-400/10 text-yellow-300"
                                : item.ecological_status === "exotica"
                                  ? "border-orange-400/30 bg-orange-400/10 text-orange-300"
                                  : "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
                        )}
                        title={`Status ecológico regional: ${item.ecological_status_label ?? ""}`}
                      >
                        {item.ecological_badge}
                      </span>
                    ) : null}
                  </div>

                  {item.is_unlocked ? (
                    <>
                      <p className="text-xs text-[var(--color-text-muted)]">
                        {item.visits_count} visita(s) · primeiro registro em{" "}
                        {formatDateTime(item.first_seen_at)}
                      </p>
                      {item.badges.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5 pt-0.5">
                          {item.badges.map((badge) => (
                            <span
                              key={badge}
                              className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-300"
                            >
                              {badge}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-xs text-[var(--color-text-muted)]">
                      Visite o alimentador para desbloquear esta figurinha.
                    </p>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
      <SpeciesProfileModal
        species={selected}
        onClose={() => setSelected(null)}
      />
    </section>
  );
}
