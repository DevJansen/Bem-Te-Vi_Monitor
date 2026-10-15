import { LockKeyhole } from "lucide-react";
import type { Achievement } from "@/types";
import { cn } from "@/utils/cn";

type Props = {
  achievements: Achievement[];
};

/**
 * Seção de Conquistas: medalhas/marcos do observador. As conquistadas ganham
 * destaque colorido; as pendentes mostram uma barra de progresso até o alvo.
 */
export function AchievementsGrid({ achievements }: Props) {
  const unlocked = achievements.filter((item) => item.unlocked).length;

  return (
    <section className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
            Medalhas do Observador
          </h2>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Marcos conquistados acompanhando seus passarinhos
          </p>
        </div>
        <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1 text-xs font-semibold text-amber-200">
          {unlocked}/{achievements.length} conquistadas
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {achievements.map((item, index) => {
          const progressPct = Math.min(
            100,
            Math.round((item.progress / item.target) * 100),
          );
          return (
            <article
              key={item.id}
              style={{ animationDelay: `${Math.min(index, 12) * 45}ms` }}
              className={cn(
                "animate-pop-in rounded-xl border p-4 transition-transform duration-300 hover:-translate-y-1",
                item.unlocked
                  ? "border-amber-400/40 bg-gradient-to-br from-amber-400/10 to-dark-800"
                  : "border-dark-700 bg-dark-900/50",
              )}
            >
              <div className="flex items-start gap-3">
                <span
                  className={cn(
                    "flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-2xl ring-2",
                    item.unlocked
                      ? "bg-amber-400/15 ring-amber-400/50"
                      : "bg-dark-800 ring-dark-700 grayscale opacity-50",
                  )}
                  aria-hidden
                >
                  {item.unlocked ? item.icon : <LockKeyhole className="h-5 w-5" />}
                </span>
                <div className="min-w-0">
                  <h3
                    className={cn(
                      "font-medium",
                      item.unlocked
                        ? "text-[var(--color-text-primary)]"
                        : "text-[var(--color-text-muted)]",
                    )}
                  >
                    {item.name}
                  </h3>
                  <p className="mt-0.5 text-xs leading-snug text-[var(--color-text-muted)]">
                    {item.description}
                  </p>
                </div>
              </div>

              <div className="mt-3">
                <div className="h-1.5 overflow-hidden rounded-full bg-dark-900">
                  <div
                    className={cn(
                      "h-full rounded-full transition-[width] duration-700 ease-out",
                      item.unlocked
                        ? "bg-gradient-to-r from-amber-500 to-amber-300"
                        : "bg-emerald-500/70",
                    )}
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <p className="mt-1 text-[11px] tabular-nums text-[var(--color-text-muted)]">
                  {item.unlocked
                    ? "Conquistada 🎉"
                    : `${item.progress} de ${item.target}`}
                </p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
