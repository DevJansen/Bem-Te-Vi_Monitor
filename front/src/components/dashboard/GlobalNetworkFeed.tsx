import { Globe2, LoaderCircle, MapPin, Radio, RefreshCw } from "lucide-react";

import { usePolling } from "@/hooks/usePolling";
import { fetchNetworkFeed, getErrorMessage } from "@/services/api";
import { cn } from "@/utils/cn";
import type { NetworkFeedEvent } from "@/types";

/** Tempo relativo curto para o feed ("agora", "há 5 min", "há 2 h"). */
function relativeTime(iso: string): string {
  const moment = new Date(iso).getTime();
  if (Number.isNaN(moment)) return "há instantes";
  const seconds = Math.max(0, Math.round((Date.now() - moment) / 1000));
  if (seconds < 45) return "agora";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.round(hours / 24);
  return `há ${days} d`;
}

function FeedRow({ event }: { event: NetworkFeedEvent }) {
  const rare = event.rarity === "Rara";
  const garden =
    event.garden_name || event.source_instance || "jardim conectado";
  return (
    <li className="group flex items-start gap-3 rounded-xl border border-dark-700 bg-dark-900/60 px-3 py-2.5 transition hover:border-emerald-500/30 hover:bg-dark-900">
      <span
        className={cn(
          "mt-0.5 rounded-lg p-1.5",
          rare
            ? "bg-amber-400/15 text-amber-300"
            : "bg-sky-400/15 text-sky-300",
        )}
        aria-hidden
      >
        {rare ? "🦜" : "🐦"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs leading-relaxed text-[var(--color-text-primary)]">
          <span
            className={cn(
              "mr-1 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
              rare
                ? "border-amber-400/25 bg-amber-400/10 text-amber-200"
                : "border-sky-400/25 bg-sky-400/10 text-sky-200",
            )}
          >
            {event.rarity}
          </span>
          <strong className="font-semibold">{event.species}</strong>{" "}
          <span className="text-[var(--color-text-muted)]">avistada no</span>{" "}
          <span className="font-medium">{garden}</span>
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-[var(--color-text-muted)]">
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {event.source_kind === "local" ? "Seu jardim" : event.source_instance}
          </span>
          <span aria-hidden>·</span>
          <span>{relativeTime(event.occurred_at)}</span>
          {event.confidence != null ? (
            <>
              <span aria-hidden>·</span>
              <span>{Math.round(event.confidence * 100)}% de confiança</span>
            </>
          ) : null}
        </p>
      </div>
    </li>
  );
}

/**
 * Card **Feed Global Bem-Ti-Vi** do Painel Principal.
 *
 * Reúne os destaques raros/incomuns das câmeras deste jardim e das instâncias
 * conectadas por webhook. O polling é leve (30 s) e o componente tolera falhas
 * de rede sem esconder o restante do painel.
 */
export function GlobalNetworkFeed() {
  const query = usePolling(() => fetchNetworkFeed(12), 30_000);
  const feed = query.data;
  const events = feed?.events ?? [];

  return (
    <section
      aria-label="Feed Global Bem-Ti-Vi"
      className="rounded-2xl border border-dark-700 bg-dark-800/80 p-4 shadow-[0_10px_40px_-28px_rgba(16,185,129,0.65)] backdrop-blur"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-emerald-500/15 p-2.5 text-emerald-300">
            <Globe2 className="h-5 w-5" />
          </span>
          <div>
            <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
              Feed Global Bem-Ti-Vi
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Destaques dos jardins conectados · {feed?.instance_name ?? "seu jardim"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-full border border-dark-600 bg-dark-900 px-2 py-1 text-[10px] text-[var(--color-text-muted)]">
            <Radio className="h-3 w-3 text-emerald-300" />
            {feed?.total ?? 0} destaque(s) · {feed?.days ?? 7} dias
          </span>
          <button
            type="button"
            onClick={() => void query.refresh()}
            disabled={query.loading}
            aria-label="Atualizar Feed Global"
            className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:text-emerald-300 disabled:opacity-50"
          >
            <RefreshCw
              className={cn("h-4 w-4", query.loading && "animate-spin")}
            />
          </button>
        </div>
      </header>

      {query.error ? (
        <p className="mt-3 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          {getErrorMessage(query.error, "Feed global indisponível agora.")}
        </p>
      ) : null}

      {query.loading && !feed ? (
        <p className="mt-3 flex items-center gap-2 rounded-xl border border-dark-700 bg-dark-900/60 px-3 py-4 text-xs text-[var(--color-text-muted)]">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Conectando aos jardins da rede…
        </p>
      ) : feed && !feed.enabled ? (
        <div className="mt-3 rounded-xl border border-dashed border-dark-700 bg-dark-900/40 px-4 py-5 text-center">
          <p className="text-sm font-medium text-[var(--color-text-primary)]">
            Rede global desativada
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Ative <code className="rounded bg-dark-950 px-1 py-0.5 text-[10px] text-emerald-200">GLOBAL_NETWORK_ENABLED</code>{" "}
            para reunir os destaques raros deste jardim e dos parceiros.
          </p>
        </div>
      ) : events.length === 0 ? (
        <div className="mt-3 rounded-xl border border-dashed border-dark-700 bg-dark-900/40 px-4 py-5 text-center">
          <p className="text-sm font-medium text-[var(--color-text-primary)]">
            Nenhum destaque raro compartilhado ainda
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Os avistamentos raros e incomuns deste jardim aparecem aqui
            automaticamente. Para ver outros jardins, configure
            <code className="mx-1 rounded bg-dark-950 px-1 py-0.5 text-[10px] text-emerald-200">
              GLOBAL_NETWORK_PEERS
            </code>
            e o mesmo token nas instâncias.
          </p>
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {events.map((event) => (
            <FeedRow key={event.id} event={event} />
          ))}
        </ul>
      )}
    </section>
  );
}
