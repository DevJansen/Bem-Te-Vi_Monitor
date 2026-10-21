import { useEffect, useMemo, useState } from "react";
import {
  Bird,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Moon,
  Radar,
  RefreshCw,
  Sparkles,
  Squirrel,
  Star,
} from "lucide-react";
import type { BirdSpecies, BirdVisit, WildlifeSummary } from "@/types";
import { fetchTodayVisits, fetchWildlifeSummary, getErrorMessage, listCameras, resolveMediaUrl, visitCropUrl } from "@/services/api";
import { usePolling } from "@/hooks/usePolling";
import { cn } from "@/utils/cn";
import { formatTime } from "@/utils/format";
import { VisitDeepDiveModal } from "@/components/dashboard/VisitDeepDiveModal";
import {
  formatRelativeTime,
  isFreshVisit,
  isEcologicalUnknown,
  resolveEcological,
  resolveIdentificationBadge,
  resolveVisitNames,
  resolveVisitSpeciesLabel,
} from "@/utils/visits";

/** Quantidade de visitas exibidas por página (as 5 mais recentes primeiro). */
const PAGE_SIZE = 5;
/** Limite buscado na API: cobre todas as visitas do dia (máx. aceito: 200). */
const FETCH_LIMIT = 200;

async function loadBirdVisits(): Promise<BirdVisit[]> {
  try {
    return await fetchTodayVisits(FETCH_LIMIT);
  } catch (error) {
    throw new Error(
      getErrorMessage(error, "Não foi possível carregar as visitas de hoje."),
    );
  }
}

async function loadVisitorVisits(): Promise<BirdVisit[]> {
  try {
    return await fetchTodayVisits(FETCH_LIMIT, "special");
  } catch (error) {
    throw new Error(
      getErrorMessage(error, "Não foi possível carregar os Visitantes Especiais."),
    );
  }
}

async function loadWildlifeSummary(): Promise<WildlifeSummary> {
  try {
    return await fetchWildlifeSummary();
  } catch (error) {
    throw new Error(
      getErrorMessage(error, "Não foi possível carregar os Visitantes Especiais."),
    );
  }
}

type Props = {
  /** Catálogo local — resolve o status ecológico quando os metadados não têm. */
  species?: BirdSpecies[];
  /** Abre o clipe completo da visita na aba Galeria (atalho do deep-dive). */
  onOpenInGallery?: (visitId: string) => void;
};

/**
 * Painel "Visitas de Hoje": as 5 capturas mais recentes do dia em cards
 * clicáveis, com paginação limpa para as demais. Cada card abre um modal
 * imersivo (deep-dive) com a foto tratada em alta definição e a telemetria do
 * Bem-Te-Vi Core.
 */
export function TodayVisitsPanel({ species = [], onOpenInGallery }: Props) {
  const [view, setView] = useState<"birds" | "visitors">("birds");
  const [gardenFilter, setGardenFilter] = useState<string | null>(null);

  const birdsQuery = usePolling(loadBirdVisits, 8_000, view === "birds");
  const visitorsQuery = usePolling(loadVisitorVisits, 8_000, view === "visitors");
  const wildlifeQuery = usePolling(loadWildlifeSummary, 15_000);
  const camerasQuery = usePolling(listCameras, 60_000);

  const activeQuery = view === "birds" ? birdsQuery : visitorsQuery;
  const allVisits = useMemo(() => activeQuery.data ?? [], [activeQuery.data]);
  const visits = useMemo(
    () =>
      gardenFilter
        ? allVisits.filter((v) => v.camera_id === gardenFilter)
        : allVisits,
    [allVisits, gardenFilter],
  );

  const cameras = camerasQuery.data ?? [];

  const [page, setPage] = useState(1);
  const [selectedVisit, setSelectedVisit] = useState<BirdVisit | null>(null);
  // "Relógio" local para expirar o selo "Novo Registro ✨" (janela de 60 s).
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 5_000);
    return () => window.clearInterval(id);
  }, []);

  // Volta à primeira página ao trocar de visão.
  useEffect(() => {
    setPage(1);
  }, [view]);

  const totalPages = Math.max(1, Math.ceil(visits.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageVisits = useMemo(
    () => visits.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [visits, safePage],
  );
  const freshCount = useMemo(
    () => visits.filter((visit) => isFreshVisit(visit.detected_at, now)).length,
    [visits, now],
  );

  // Mantém o modal com os dados mais recentes do polling (com fallback local).
  const detailedVisit = useMemo(
    () =>
      selectedVisit
        ? visits.find((visit) => visit.id === selectedVisit.id) ?? selectedVisit
        : null,
    [selectedVisit, visits],
  );

  const handleOpenInGallery = (visitId: string) => {
    onOpenInGallery?.(visitId);
  };

  return (
    <section className="overflow-hidden rounded-xl border border-dark-700 bg-dark-800">
      {/* Cabeçalho */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-dark-700 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400">
            <Clock3 className="h-4 w-4" />
          </span>
          <div>
            <h2 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
              Visitas de Hoje
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Últimas capturas tratadas pelo Bem-Te-Vi Core
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {freshCount > 0 && view === "birds" ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/40 bg-emerald-500/15 px-2.5 py-1 text-[10px] font-semibold text-emerald-300">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
              </span>
              {freshCount} {freshCount === 1 ? "novo agora" : "novos agora"}
            </span>
          ) : null}
          {visits.length > 0 ? (
            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-semibold text-emerald-300">
              {visits.length} hoje
            </span>
          ) : null}
          <select
            value={gardenFilter ?? ""}
            onChange={(event) =>
              setGardenFilter(event.target.value === "" ? null : event.target.value)
            }
            aria-label="Filtrar por jardim"
            className="rounded-md border border-dark-700 bg-dark-900/60 px-2 py-1.5 text-xs text-[var(--color-text-primary)] transition hover:border-emerald-400/40 focus:outline-none focus:ring-2 focus:ring-emerald-400/40"
          >
            <option value="">Todos os jardins</option>
            {cameras.map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.location_label || camera.name || "Jardim sem nome"}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void activeQuery.refresh()}
            disabled={activeQuery.loading}
            aria-label="Atualizar visitas de hoje"
            className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:text-emerald-300 disabled:opacity-50"
          >
            <RefreshCw className={cn("h-4 w-4", activeQuery.loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* Aba segmentada: Aves × Visitantes Especiais (Modo Esquilo) */}
      <div className="flex flex-wrap items-center gap-2 border-b border-dark-700 bg-dark-900/40 px-4 py-2">
        <button
          type="button"
          onClick={() => setView("birds")}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition",
            view === "birds"
              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
              : "text-[var(--color-text-muted)] hover:text-emerald-300",
          )}
        >
          <Bird className="h-3.5 w-3.5" />
          Aves
        </button>
        <button
          type="button"
          onClick={() => setView("visitors")}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition",
            view === "visitors"
              ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
              : "text-[var(--color-text-muted)] hover:text-amber-300",
          )}
        >
          <Squirrel className="h-3.5 w-3.5" />
          Visitantes Especiais
        </button>

        {view === "visitors" ? (
          <div className="ml-auto flex flex-wrap items-center gap-2 text-[10px] font-semibold">
            <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-amber-300">
              🐿️ {wildlifeQuery.data?.squirrel_visits_today ?? 0} hoje
            </span>
            <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-amber-300">
              🌰 {wildlifeQuery.data?.seeds_stolen_today ?? 0} sementes roubadas hoje
            </span>
            <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-amber-300">
              Total: {wildlifeQuery.data?.total_visits ?? 0} aparições
            </span>
          </div>
        ) : null}
      </div>

      <div className="p-4">
        {activeQuery.error ? (
          <p role="alert" className="text-sm text-red-300">
            {activeQuery.error}
          </p>
        ) : activeQuery.loading && visits.length === 0 ? (
          <LoadingSkeleton />
        ) : visits.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            <ul className="space-y-2">
              {pageVisits.map((visit, index) => (
                <VisitRow
                  key={visit.id}
                  visit={visit}
                  catalogSpecies={species}
                  now={now}
                  index={index}
                  onOpen={() => setSelectedVisit(visit)}
                />
              ))}
            </ul>

            {totalPages > 1 ? (
              <nav
                aria-label="Paginação das visitas de hoje"
                className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-dark-700 pt-3"
              >
                <span className="text-[11px] text-[var(--color-text-muted)]">
                  Página{" "}
                  <strong className="font-semibold text-[var(--color-text-primary)]">
                    {safePage}
                  </strong>{" "}
                  de {totalPages} · {visits.length} registros hoje
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setPage(Math.max(1, safePage - 1))}
                    disabled={safePage <= 1}
                    className={pagerButtonClass}
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                    Anterior
                  </button>
                  <div className="hidden items-center gap-1 sm:flex">
                    {pageNumbers(totalPages, safePage).map((number) => (
                      <button
                        key={number}
                        type="button"
                        onClick={() => setPage(number)}
                        aria-label={`Ir para a página ${number}`}
                        aria-current={number === safePage ? "page" : undefined}
                        className={cn(
                          "h-7 w-7 rounded-md text-xs font-semibold tabular-nums transition",
                          number === safePage
                            ? "bg-emerald-500/20 text-emerald-200 ring-1 ring-emerald-400/50"
                            : "text-[var(--color-text-muted)] hover:bg-dark-700 hover:text-[var(--color-text-primary)]",
                        )}
                      >
                        {number}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => setPage(Math.min(totalPages, safePage + 1))}
                    disabled={safePage >= totalPages}
                    className={pagerButtonClass}
                  >
                    Próxima
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </nav>
            ) : null}
          </>
        )}
      </div>

      <VisitDeepDiveModal
        visit={detailedVisit}
        catalogSpecies={species}
        onClose={() => setSelectedVisit(null)}
        onOpenInGallery={handleOpenInGallery}
        onVisitUpdated={() => void activeQuery.refresh()}
      />
    </section>
  );
}

/** Card clicável de uma visita (miniatura, espécie, horário e selo ecológico). */
function VisitRow({
  visit,
  catalogSpecies,
  now,
  index,
  onOpen,
}: {
  visit: BirdVisit;
  catalogSpecies: BirdSpecies[];
  now: number;
  index: number;
  onOpen: () => void;
}) {
  const frame = resolveMediaUrl(visit.thumbnail_url ?? visit.thumbnail_path);
  // A miniatura circular usa o **recorte (close-up) da ave** tratado pelo
  // Bem-Te-Vi Core — bem mais nítido que o quadro inteiro. Se o recorte não existir ou
  // falhar ao carregar, cai de volta para a thumbnail do quadro completo.
  const crop = visit.metadata?.crop_path ? visitCropUrl(visit.id) : null;
  const [cropFailed, setCropFailed] = useState(false);
  const thumb = crop && !cropFailed ? crop : frame;
  const label = resolveVisitSpeciesLabel(visit);
  const names = resolveVisitNames(visit);
  const catalogEntry = visit.species_id
    ? catalogSpecies.find((item) => item.id === visit.species_id)
    : undefined;
  const ecological = resolveEcological(visit, catalogEntry);
  // O selo ecológico "desconhecido" é omitido: a identificação já é
  // comunicada pelo badge elegante abaixo do nome da ave.
  const showEcological = Boolean(ecological?.badge) && !isEcologicalUnknown(ecological);
  // Selo de identificação (substitui a antiga tag estática "Desconhecido").
  const identificationBadge = resolveIdentificationBadge(visit);
  const fresh = isFreshVisit(visit.detected_at, now);
  const confidencePct = Math.round(
    Math.min(1, Math.max(0, visit.confidence)) * 100,
  );
  const nightCapture = Boolean(visit.metadata?.night_mode);
  const enhanced = Boolean(visit.metadata?.enhanced);

  return (
    <li
      style={{ animationDelay: `${Math.min(index, PAGE_SIZE - 1) * 45}ms` }}
      className="animate-fade-in-up"
    >
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Ver detalhes da visita de ${label} às ${formatTime(visit.detected_at)}`}
        className="group relative flex w-full items-center gap-3 overflow-hidden rounded-xl border border-dark-700 bg-dark-900/40 px-3 py-2.5 text-left transition-all duration-300 hover:-translate-y-0.5 hover:border-emerald-400/50 hover:bg-dark-700/50 hover:shadow-[0_0_28px_-8px_rgba(16,185,129,0.7)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
      >
        {/* Brilho neon à esquerda (aparece no hover). */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-0 w-0.5 bg-gradient-to-b from-emerald-400/0 via-emerald-400/80 to-cyan-400/0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        />

        {/* Miniatura circular otimizada */}
        <span className="relative h-12 w-12 shrink-0">
          <span className="block h-12 w-12 overflow-hidden rounded-full ring-2 ring-emerald-500/25 transition group-hover:ring-emerald-400/70">
            {thumb ? (
              <img
                src={thumb}
                alt={`Miniatura de ${label}`}
                className="h-full w-full object-cover transition duration-500 group-hover:scale-110"
                onError={() => {
                  if (thumb === crop) setCropFailed(true);
                }}
              />
            ) : (
              <span className="flex h-full w-full items-center justify-center bg-dark-900 text-[var(--color-text-muted)]">
                <Bird className="h-5 w-5" />
              </span>
            )}
          </span>
          {fresh ? (
            <span className="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full bg-emerald-400 ring-2 ring-dark-900">
              <span className="absolute inset-0 animate-pulse-ring rounded-full bg-emerald-400" />
            </span>
          ) : null}
        </span>

        {/* Identificação */}
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-[var(--color-text-primary)]">
              {label}
            </span>
            {visit.location_label || visit.camera_name ? (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 text-[10px] font-semibold text-sky-300">
                📍 {visit.location_label || visit.camera_name}
              </span>
            ) : null}
            {fresh ? (
              <span className="inline-flex shrink-0 animate-pulse-soft items-center gap-1 rounded-full border border-emerald-400/40 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                <Sparkles className="h-2.5 w-2.5" />
                Novo Registro
              </span>
            ) : null}
          </span>
          {names.scientificName ? (
            <span className="block truncate text-xs italic text-[var(--color-text-muted)]">
              {names.scientificName}
            </span>
          ) : null}
          <span className="mt-1 flex flex-wrap items-center gap-1.5">
            {identificationBadge ? (
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold",
                  identificationBadge.className,
                )}
                title={identificationBadge.title}
              >
                <CheckCircle2 className="h-2.5 w-2.5" />
                {identificationBadge.label}
              </span>
            ) : null}
            {showEcological && ecological?.badge ? (
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold",
                  ecological.rare
                    ? "bg-amber-400/90 text-amber-950"
                    : "bg-dark-700 text-[var(--color-text-primary)]",
                )}
                title={`Status ecológico: ${ecological.label}`}
              >
                {ecological.rare ? <Star className="h-2.5 w-2.5 fill-current" /> : null}
                {ecological.badge}
              </span>
            ) : null}
            {nightCapture ? (
              <span
                className="inline-flex items-center gap-1 rounded-md bg-indigo-500/80 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                title="Captura em visão noturna (infravermelho)"
              >
                <Moon className="h-2.5 w-2.5" />
                Noturno
              </span>
            ) : null}
            {enhanced ? (
              <span
                className="rounded-md bg-emerald-500/80 px-1.5 py-0.5 text-[10px] font-semibold text-white"
                title="Foto tratada automaticamente (alta definição)"
              >
                HD
              </span>
            ) : null}
          </span>
        </span>

        {/* Horário e confiança */}
        <span className="flex shrink-0 flex-col items-end gap-0.5">
          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold tabular-nums text-emerald-300">
            {formatTime(visit.detected_at)}
          </span>
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {formatRelativeTime(visit.detected_at, now)}
          </span>
          <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
            {confidencePct}% conf.
          </span>
        </span>

        <ChevronRight className="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition group-hover:translate-x-0.5 group-hover:text-emerald-300" />
      </button>
    </li>
  );
}

/** Estado vazio sofisticado: radar em vigilância ativa. */
function EmptyState() {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-dashed border-emerald-500/25 bg-gradient-to-b from-emerald-500/[0.07] to-transparent px-6 py-12 text-center">
      <span className="relative mx-auto flex h-16 w-16 items-center justify-center">
        <span className="absolute inset-0 animate-pulse-ring rounded-full bg-emerald-500/20" />
        <span className="absolute inset-0 rounded-full border border-emerald-500/30" />
        <span className="relative flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-300">
          <Radar className="h-7 w-7" />
        </span>
      </span>
      <h3 className="mt-4 font-display text-sm font-semibold text-[var(--color-text-primary)]">
        Bem-Te-Vi Core em vigilância ativa
      </h3>
      <p className="mx-auto mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
        Aguardando os primeiros visitantes do dia…
      </p>
      <p className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
        <Radar className="h-3 w-3 animate-pulse-soft" />
        Monitorando o comedouro
      </p>
    </div>
  );
}

/** Esqueleto de carregamento (evita "salto" visual no primeiro fetch). */
function LoadingSkeleton() {
  return (
    <ul className="space-y-2" aria-hidden>
      {Array.from({ length: 3 }).map((_, index) => (
        <li
          key={index}
          className="flex items-center gap-3 rounded-xl border border-dark-700 bg-dark-900/40 px-3 py-3"
        >
          <span className="h-12 w-12 shrink-0 animate-pulse rounded-full bg-dark-700" />
          <span className="flex-1 space-y-2">
            <span className="block h-3 w-2/5 animate-pulse rounded bg-dark-700" />
            <span className="block h-2.5 w-3/5 animate-pulse rounded bg-dark-700/70" />
          </span>
        </li>
      ))}
    </ul>
  );
}

const pagerButtonClass =
  "inline-flex items-center gap-1 rounded-lg border border-dark-700 px-2.5 py-1.5 text-xs font-medium text-[var(--color-text-muted)] transition hover:border-emerald-500/40 hover:bg-dark-700 hover:text-emerald-200 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-dark-700 disabled:hover:bg-transparent disabled:hover:text-[var(--color-text-muted)]";

/** Janela de números de página (no máximo 5) centrada na página atual. */
function pageNumbers(total: number, current: number): number[] {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const start = Math.max(1, Math.min(current - 2, total - 4));
  return Array.from({ length: 5 }, (_, index) => start + index);
}
