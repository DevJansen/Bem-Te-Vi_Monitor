import { useRef, useState } from "react";
import {
  Camera as CameraIcon,
  Download,
  ImageOff,
  LoaderCircle,
  Play,
  RefreshCw,
  Sparkles,
  Star,
} from "lucide-react";
import type { RareMoment } from "@/types";
import {
  fetchRareMoments,
  getErrorMessage,
  rareMomentPostcardUrl,
  refreshRareMoments,
  resolveMediaUrl,
} from "@/services/api";
import { usePolling } from "@/hooks/usePolling";
import { formatDateTime, formatSpeciesLabel } from "@/utils/format";
import { cn } from "@/utils/cn";
import { VideoPlayerModal } from "@/components/common/VideoPlayerModal";

const PERIODS = [
  { days: 7, label: "7 dias" },
  { days: 14, label: "14 dias" },
  { days: 30, label: "30 dias" },
];

const RARITY_STYLE: Record<string, string> = {
  Rara: "border-amber-300/50 bg-amber-400/90 text-amber-950",
  Incomum: "border-sky-300/40 bg-sky-400/85 text-sky-950",
  Comum: "border-white/20 bg-black/55 text-white/90",
};

/**
 * Sub-aba "Momentos Raros / Fotos de Postal".
 *
 * A curadoria é feita no backend: nitidez (Laplaciano) + raridade da espécie.
 * A primeira foto vira destaque de revista; as demais formam uma grade com
 * download da versão em postal (moldura + legenda + marca d'água).
 */
export function RareMomentsGallery() {
  const daysRef = useRef(7);
  const [days, setDays] = useState(7);
  const [scanning, setScanning] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [playing, setPlaying] = useState<RareMoment | null>(null);

  const query = usePolling(
    () => fetchRareMoments({ days: daysRef.current, limit: 24 }),
    120_000,
  );

  const moments = query.data?.moments ?? [];
  const [featured, ...rest] = moments;

  const changePeriod = (value: number) => {
    daysRef.current = value;
    setDays(value);
    void query.refresh();
  };

  const refreshCuration = async () => {
    setScanning(true);
    setToast(null);
    try {
      const result = await refreshRareMoments(120);
      await query.refresh();
      setToast(
        result.scanned > 0
          ? `${result.scanned} captura(s) avaliada(s) pelo Bem-Te-Vi Core.`
          : "Todas as capturas já estavam avaliadas.",
      );
    } catch (error) {
      setToast(getErrorMessage(error, "Não foi possível atualizar a curadoria."));
    } finally {
      setScanning(false);
      window.setTimeout(() => setToast(null), 4500);
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300">
            <Sparkles className="h-5 w-5" />
          </span>
          <div>
            <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
              Momentos Raros · Fotos de Postal
            </h2>
            <p className="text-sm text-[var(--color-text-muted)]">
              Curadoria do Bem-Te-Vi Core: as fotos mais nítidas e as espécies
              raras ou incomuns da semana.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex gap-1 rounded-lg border border-dark-700 bg-dark-800 p-1">
            {PERIODS.map((period) => (
              <button
                key={period.days}
                type="button"
                onClick={() => changePeriod(period.days)}
                aria-pressed={days === period.days}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-xs font-medium transition",
                  days === period.days
                    ? "bg-amber-400/15 text-amber-200"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
                )}
              >
                {period.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => void refreshCuration()}
            disabled={scanning}
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-300 transition hover:bg-emerald-500/20 disabled:opacity-60"
          >
            {scanning ? (
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            Atualizar curadoria
          </button>
        </div>
      </div>

      {query.error && !query.data ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {getErrorMessage(query.error, "Não foi possível carregar os Momentos Raros.")}
        </div>
      ) : null}

      {query.loading && !query.data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="aspect-[16/10] animate-pulse rounded-2xl bg-dark-800 sm:col-span-2" />
          <div className="aspect-square animate-pulse rounded-2xl bg-dark-800" />
        </div>
      ) : !featured ? (
        <div className="rounded-2xl border border-dashed border-dark-700 bg-dark-800/60 px-6 py-14 text-center">
          <ImageOff className="mx-auto h-8 w-8 text-[var(--color-text-muted)]" />
          <p className="mt-3 text-sm font-medium text-[var(--color-text-primary)]">
            Nenhuma foto na curadoria ainda.
          </p>
          <p className="mx-auto mt-1 max-w-md text-xs text-[var(--color-text-muted)]">
            Assim que as primeiras aves forem capturadas, o Bem-Te-Vi Core mede a
            nitidez e destaca aqui as fotos de postal e as espécies raras.
          </p>
          <button
            type="button"
            onClick={() => void refreshCuration()}
            disabled={scanning}
            className="mt-4 inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/20 disabled:opacity-60"
          >
            {scanning ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            Preparar curadoria agora
          </button>
        </div>
      ) : (
        <>
          {/* Destaque principal — capa de revista */}
          <FeaturedMoment moment={featured} onPlay={() => setPlaying(featured)} />

          {rest.length ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {rest.map((moment) => (
                <MomentCard
                  key={moment.visit_id}
                  moment={moment}
                  onPlay={() => setPlaying(moment)}
                />
              ))}
            </div>
          ) : null}
        </>
      )}

      <p className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
        <Star className="h-3 w-3 text-amber-300/80" />
        O escore combina nitidez (variância do Laplaciano), confiança da IA e
        raridade da espécie no seu histórico. A foto de postal é gerada na hora,
        com moldura e marca d&apos;água oficiais.
      </p>

      {toast ? (
        <p
          role="status"
          className="fixed bottom-5 right-5 z-50 rounded-lg border border-emerald-500/30 bg-emerald-950 px-4 py-3 text-sm text-emerald-300 shadow-xl"
        >
          {toast}
        </p>
      ) : null}

      <VideoPlayerModal
        open={playing !== null}
        title={
          playing
            ? `${formatSpeciesLabel(playing.species)} · ${formatDateTime(playing.detected_at)}`
            : ""
        }
        src={resolveMediaUrl(playing?.clip_url ?? null)}
        species={playing?.species ?? null}
        confidence={playing?.confidence ?? null}
        scientificName={playing?.scientific_name ?? null}
        onClose={() => setPlaying(null)}
      />
    </section>
  );
}

function FeaturedMoment({
  moment,
  onPlay,
}: {
  moment: RareMoment;
  onPlay: () => void;
}) {
  const image = resolveMediaUrl(moment.thumbnail_url);
  return (
    <article className="group relative overflow-hidden rounded-2xl border border-amber-400/20 bg-dark-900">
      <div className="relative aspect-[16/9] w-full sm:aspect-[21/9]">
        {image ? (
          <img
            src={image}
            alt={formatSpeciesLabel(moment.species)}
            className="h-full w-full object-cover transition duration-700 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-muted)]">
            Sem imagem
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/25 to-black/10" />

        <div className="absolute left-4 top-4 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md border border-amber-300/40 bg-amber-400/90 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-950">
            <Sparkles className="h-3 w-3" />
            Destaque da semana
          </span>
          <RarityBadge rarity={moment.rarity} />
        </div>

        <div className="absolute right-4 top-4 flex items-center gap-2">
          <SharpnessBadge score={moment.sharpness_score} />
        </div>

        <div className="absolute inset-x-0 bottom-0 flex flex-wrap items-end justify-between gap-3 p-4 sm:p-6">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-200/90">
              {moment.reason}
            </p>
            <h3 className="mt-1 font-display text-2xl font-semibold text-white sm:text-3xl">
              {formatSpeciesLabel(moment.species)}
            </h3>
            {moment.scientific_name ? (
              <p className="text-sm italic text-white/70">
                {moment.scientific_name}
              </p>
            ) : null}
            <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-white/70">
              <span>{formatDateTime(moment.detected_at)}</span>
              {moment.garden ? (
                <span className="inline-flex items-center gap-1">
                  <CameraIcon className="h-3 w-3" />
                  {moment.garden}
                </span>
              ) : null}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {moment.clip_url ? (
              <button
                type="button"
                onClick={onPlay}
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 bg-black/40 px-3 py-2 text-xs font-semibold text-white backdrop-blur transition hover:bg-black/60"
              >
                <Play className="h-3.5 w-3.5 fill-current" />
                Ver clipe
              </button>
            ) : null}
            <DownloadPostcard moment={moment} />
          </div>
        </div>
      </div>
    </article>
  );
}

function MomentCard({
  moment,
  onPlay,
}: {
  moment: RareMoment;
  onPlay: () => void;
}) {
  const image = resolveMediaUrl(moment.thumbnail_url);
  return (
    <article className="group relative overflow-hidden rounded-xl border border-dark-700 bg-dark-900">
      <div className="relative aspect-[4/3] w-full">
        {image ? (
          <img
            src={image}
            alt={formatSpeciesLabel(moment.species)}
            loading="lazy"
            className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-[var(--color-text-muted)]">
            Sem imagem
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent" />
        <div className="absolute left-2 top-2">
          <RarityBadge rarity={moment.rarity} compact />
        </div>
        <div className="absolute right-2 top-2">
          <SharpnessBadge score={moment.sharpness_score} compact />
        </div>
        <div className="absolute inset-x-0 bottom-0 p-3">
          <p className="truncate text-sm font-semibold text-white">
            {formatSpeciesLabel(moment.species)}
          </p>
          <p className="truncate text-[10px] text-white/60">
            {formatDateTime(moment.detected_at)}
            {moment.garden ? ` · ${moment.garden}` : ""}
          </p>
        </div>
        <div className="absolute inset-x-0 bottom-0 flex translate-y-2 items-center justify-end gap-1.5 p-2 opacity-0 transition group-hover:translate-y-0 group-hover:opacity-100">
          {moment.clip_url ? (
            <button
              type="button"
              onClick={onPlay}
              aria-label="Reproduzir clipe"
              className="rounded-md border border-white/20 bg-black/60 p-1.5 text-white backdrop-blur transition hover:bg-black/80"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
            </button>
          ) : null}
          <DownloadPostcard moment={moment} compact />
        </div>
      </div>
    </article>
  );
}

function RarityBadge({
  rarity,
  compact = false,
}: {
  rarity: string;
  compact?: boolean;
}) {
  const style = RARITY_STYLE[rarity] ?? RARITY_STYLE.Comum;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border font-semibold uppercase tracking-wider",
        compact ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-1 text-[10px]",
        style,
      )}
    >
      {rarity === "Rara" ? <Star className="h-2.5 w-2.5 fill-current" /> : null}
      {rarity}
    </span>
  );
}

function SharpnessBadge({
  score,
  compact = false,
}: {
  score: number;
  compact?: boolean;
}) {
  return (
    <span
      title="Escore de nitidez (Laplaciano)"
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-emerald-400/25 bg-black/55 font-mono font-semibold text-emerald-200 backdrop-blur",
        compact ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-1 text-[10px]",
      )}
    >
      <Sparkles className={compact ? "h-2.5 w-2.5" : "h-3 w-3"} />
      {score}
    </span>
  );
}

function DownloadPostcard({
  moment,
  compact = false,
}: {
  moment: RareMoment;
  compact?: boolean;
}) {
  return (
    <a
      href={rareMomentPostcardUrl(moment.visit_id)}
      download={`bem-te-vi-monitor-postal-${moment.species.replace(/\s+/g, "-").toLowerCase()}.jpg`}
      title="Baixar foto de postal com moldura e marca d'água"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border font-semibold transition",
        compact
          ? "border-white/20 bg-black/60 p-1.5 text-white backdrop-blur hover:bg-black/80"
          : "border-emerald-300/30 bg-emerald-500/90 px-3 py-2 text-xs text-dark-900 hover:bg-emerald-400",
      )}
    >
      <Download className={compact ? "h-3.5 w-3.5" : "h-3.5 w-3.5"} />
      {compact ? null : "Baixar postal"}
    </a>
  );
}
