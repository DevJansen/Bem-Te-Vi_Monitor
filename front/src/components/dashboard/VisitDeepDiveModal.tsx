import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  Bird,
  Bot,
  Camera,
  CheckCircle2,
  Clock3,
  Crosshair,
  Droplets,
  ExternalLink,
  Film,
  Image as ImageIcon,
  ImageDown,
  Leaf,
  LoaderCircle,
  Moon,
  Play,
  RefreshCw,
  Sparkles,
  Star,
  Thermometer,
  Users,
  Wind,
  X,
} from "lucide-react";
import type { BirdSpecies, BirdVisit } from "@/types";
import { confirmVisit, resolveMediaUrl, visitCropDownloadUrl, visitCropUrl } from "@/services/api";
import { cn } from "@/utils/cn";
import { formatDateTime, formatTime } from "@/utils/format";
import { formatHumidity, formatTemperature, formatWind, weatherEmoji } from "@/utils/weather";
import {
  CONFIDENCE_BAR_CLASS,
  SHARPNESS_TONE_CLASS,
  confidenceTone,
  formatDwell,
  isEcologicalUnknown,
  resolveEcological,
  resolveIdentificationBadge,
  resolveSharpness,
  resolveVisitNames,
  resolveVisitSpeciesLabel,
} from "@/utils/visits";
import { SpeciesAiConsultModal } from "@/components/species/SpeciesAiConsultModal";
import { ReclassifySpeciesModal } from "@/components/gallery/ReclassifySpeciesModal";

type Props = {
  /** Visita aberta no deep-dive (null = modal fechado). */
  visit: BirdVisit | null;
  /** Catálogo local, usado para resolver o status ecológico quando ausente. */
  catalogSpecies: BirdSpecies[];
  onClose: () => void;
  /** Abre o clipe completo (6 s) da visita na aba Galeria. */
  onOpenInGallery: (visitId: string) => void;
  /** Avisa o painel que a visita mudou (após reclassificação). */
  onVisitUpdated?: () => void;
};

/** Visão da imagem: quadro HD tratado ou o recorte (close-up) da ave. */
type ImageView = "frame" | "crop";

/**
 * Modal imersivo (lightbox) com o "deep-dive" de uma visita: foto tratada em
 * alta definição + painel de telemetria do Bem-Te-Vi Core (nomes, confiança,
 * nitidez do quadro, clima e status ecológico), download do recorte HD e
 * atalhos para o clipe na Galeria e para a reclassificação da espécie.
 */
export function VisitDeepDiveModal({
  visit: initialVisit,
  catalogSpecies,
  onClose,
  onOpenInGallery,
  onVisitUpdated,
}: Props) {
  const [imageView, setImageView] = useState<ImageView>("frame");
  // Recorte indisponível no servidor (arquivo ausente) → esconde a alternância.
  const [cropFailed, setCropFailed] = useState(false);
  // Ficha ornitológica da IA externa (consulta profunda) aberta sobre o modal.
  const [consultOpen, setConsultOpen] = useState(false);
  // Confirmação da detecção (aprendizado ativo + assinatura visual).
  const [confirming, setConfirming] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  // Modal de curadoria ("Associação Incorreta / Reclassificar").
  const [reclassifyOpen, setReclassifyOpen] = useState(false);
  // Versão local da visita (após reclassificação) — tem prioridade sobre a
  // prop até o painel recarregar a lista.
  const [override, setOverride] = useState<BirdVisit | null>(null);

  const visit = override ?? initialVisit;

  // Abre já no **recorte da ave** (close-up, mais legível) quando ele existir;
  // caso contrário, no quadro HD. Fecha com a tecla Esc.
  useEffect(() => {
    setOverride(null);
    if (initialVisit) {
      setImageView(initialVisit.metadata?.crop_path ? "crop" : "frame");
      setCropFailed(false);
      setConsultOpen(false);
      setConfirmMessage(null);
      setConfirmError(null);
      setReclassifyOpen(false);
    }
  }, [initialVisit]);

  useEffect(() => {
    if (!visit) return;
    const onKeyDown = (event: KeyboardEvent) => {
      // Não fecha o deep-dive com Esc quando a ficha da IA está aberta por cima.
      if (event.key === "Escape" && !consultOpen) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [visit, onClose, consultOpen]);

  const data = useMemo(() => {
    if (!visit) return null;
    const frame = resolveMediaUrl(visit.thumbnail_url ?? visit.thumbnail_path);
    // O recorte da ave vive em `app-data/crops` e é servido pelo endpoint
    // dedicado (`/api/visits/{id}/crop`), não pela pasta estática `captures`.
    const crop = visit.metadata?.crop_path ? visitCropUrl(visit.id) : null;
    const clip = resolveMediaUrl(visit.clip_url ?? visit.clip_path);
    const catalogEntry = visit.species_id
      ? catalogSpecies.find((item) => item.id === visit.species_id)
      : undefined;
    const ecological = resolveEcological(visit, catalogEntry);
    return {
      frame,
      crop,
      clip,
      ecological,
      // O selo ecológico "desconhecido" é omitido no deep-dive: a
      // identificação já é comunicada pelo badge elegante do cabeçalho.
      showEcological:
        Boolean(ecological?.badge) && !isEcologicalUnknown(ecological),
      sharpness: resolveSharpness(visit),
      names: resolveVisitNames(visit),
      label: resolveVisitSpeciesLabel(visit),
      behaviorLabel: visit.metadata?.behavior_label,
      behaviorIcon: visit.metadata?.behavior_icon,
      individualsPeak: visit.metadata?.individuals_peak ?? 0,
      individualsSummary: visit.metadata?.individuals_summary,
      annotation: visit.metadata?.ai_analysis?.annotation,
      nightCapture: Boolean(visit.metadata?.night_mode),
      enhanced: Boolean(visit.metadata?.enhanced),
      confidencePct: Math.round(
        Math.min(1, Math.max(0, visit.confidence)) * 100,
      ),
      tone: confidenceTone(visit.confidence),
      identificationBadge: resolveIdentificationBadge(visit),
    };
  }, [visit, catalogSpecies]);

  if (!visit || !data) return null;

  /**
   * Confirma a detecção no Bem-Te-Vi Core.
   *
   * Gera uma amostra de treino rotulada e a assinatura visual do indivíduo,
   * sem alterar o rótulo atual da visita.
   */
  const handleConfirm = async () => {
    setConfirming(true);
    setConfirmError(null);
    setConfirmMessage(null);
    try {
      const result = await confirmVisit(visit.id, {
        species_id: visit.species_id,
        species_name: visit.assigned_species_common_name ?? visit.species,
      });
      setConfirmMessage(
        result.training_queued
          ? "Detecção confirmada — amostra enviada ao Bem-Te-Vi Core."
          : result.training_reason ||
              "Detecção confirmada para a memória do jardim.",
      );
    } catch (error) {
      setConfirmError(
        error instanceof Error
          ? error.message
          : "Não foi possível confirmar a detecção.",
      );
    } finally {
      setConfirming(false);
    }
  };

  // Se o recorte falhar ao carregar, voltamos ao quadro HD e escondemos o seletor.
  const view: ImageView = cropFailed ? "frame" : imageView;
  const showCrop = Boolean(data.crop) && !cropFailed;
  const heroSrc = view === "crop" && data.crop ? data.crop : data.frame ?? data.crop;

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-3 sm:p-6">
      {/* Fundo translúcido desfocado (dark mode imersivo). */}
      <button
        type="button"
        aria-label="Fechar detalhes da visita"
        onClick={onClose}
        className="absolute inset-0 bg-black/80 backdrop-blur-md"
      />

      <section
        role="dialog"
        aria-modal="true"
        aria-label={`Detalhes da visita de ${data.label}`}
        className="relative z-10 flex max-h-[92vh] w-full max-w-5xl animate-pop-in flex-col overflow-hidden rounded-2xl border border-emerald-500/20 bg-dark-800/95 shadow-[0_0_70px_-15px_rgba(16,185,129,0.5)]"
      >
        {/* Cabeçalho */}
        <header className="flex items-start gap-3 border-b border-dark-700 px-4 py-3 sm:px-5">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
            <Bird className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300/90">
              <Sparkles className="h-3 w-3" />
              Bem-Te-Vi Core · Deep-Dive
            </p>
            <h2 className="truncate font-display text-base font-semibold text-[var(--color-text-primary)] sm:text-lg">
              {data.label}
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              {formatDateTime(visit.detected_at)}
              {visit.camera_name ? ` · ${visit.camera_name}` : ""}
            </p>
            {data.identificationBadge ? (
              <span
                className={cn(
                  "mt-1.5 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold",
                  data.identificationBadge.className,
                )}
                title={data.identificationBadge.title}
              >
                <CheckCircle2 className="h-2.5 w-2.5" />
                {data.identificationBadge.label}
              </span>
            ) : null}
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="rounded-md p-1.5 text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="grid min-h-0 flex-1 overflow-y-auto lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          {/* ——— Foto focada em alta definição ——— */}
          <div className="relative bg-black">
            <div className="relative aspect-video w-full overflow-hidden">
              {heroSrc ? (
                <img
                  key={heroSrc}
                  src={heroSrc}
                  alt={`Foto tratada pelo Bem-Te-Vi Core: ${data.label}`}
                  onError={() => {
                    if (view === "crop") setCropFailed(true);
                  }}
                  className={cn(
                    "h-full w-full",
                    view === "crop" ? "object-contain" : "object-cover",
                  )}
                />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-muted)]">
                  Imagem tratada indisponível para esta visita.
                </div>
              )}

              {/* Selo do Bem-Te-Vi Core sobre a foto. */}
              <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-3">
                <div className="flex items-start justify-between gap-2">
                  <span className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-black/65 px-3 py-2 shadow-lg backdrop-blur-md">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300">
                      <Bird className="h-4 w-4" />
                    </span>
                    <span className="flex min-w-0 flex-col leading-tight">
                      <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-300/90">
                        <Sparkles className="h-2.5 w-2.5" />
                        Bem-Te-Vi Core
                      </span>
                      <span className="truncate text-sm font-semibold text-white">
                        {data.label}
                      </span>
                    </span>
                    <span className="ml-1 shrink-0 rounded-md bg-emerald-500/20 px-1.5 py-0.5 text-[11px] font-bold tabular-nums text-emerald-300">
                      {data.confidencePct}%
                    </span>
                  </span>

                  <span className="flex shrink-0 flex-col items-end gap-1.5">
                    {data.enhanced ? (
                      <span
                        className="rounded-md bg-emerald-500/85 px-2 py-0.5 text-[10px] font-semibold text-white"
                        title="Foto tratada automaticamente pelo Bem-Te-Vi Core (alta definição)"
                      >
                        HD
                      </span>
                    ) : null}
                    {data.nightCapture ? (
                      <span
                        className="inline-flex items-center gap-1 rounded-md bg-indigo-500/85 px-2 py-0.5 text-[10px] font-semibold text-white"
                        title="Captura em visão noturna (infravermelho)"
                      >
                        <Moon className="h-3 w-3" />
                        Noturno
                      </span>
                    ) : null}
                  </span>
                </div>

                <div className="flex items-end justify-between gap-2">
                  {showCrop ? (
                    <div className="pointer-events-auto inline-flex rounded-lg border border-white/10 bg-black/65 p-0.5 backdrop-blur-md">
                      <ImageButton
                        active={view === "frame"}
                        icon={<ImageIcon className="h-3.5 w-3.5" />}
                        label="Quadro HD"
                        onClick={() => setImageView("frame")}
                      />
                      <ImageButton
                        active={view === "crop"}
                        icon={<Crosshair className="h-3.5 w-3.5" />}
                        label="Recorte da ave"
                        onClick={() => setImageView("crop")}
                      />
                    </div>
                  ) : (
                    <span />
                  )}
                  {data.showEcological && data.ecological ? (
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-semibold backdrop-blur-md",
                        data.ecological.rare
                          ? "border-amber-300/40 bg-amber-400/20 text-amber-100"
                          : "border-white/10 bg-black/65 text-white/85",
                      )}
                      title={`Status ecológico: ${data.ecological.label}`}
                    >
                      {data.ecological.rare ? (
                        <Star className="h-3 w-3 fill-current" />
                      ) : (
                        <Leaf className="h-3 w-3 text-emerald-300" />
                      )}
                      {data.ecological.badge}
                    </span>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          {/* ——— Painel de informações do Bem-Te-Vi Core ——— */}
          <div className="space-y-4 p-4 sm:p-5">
            <div>
              <h3 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
                {data.names.commonName || data.label}
              </h3>
              <p className="text-sm italic text-[var(--color-text-muted)]">
                {data.names.scientificName ?? "Nome científico não identificado"}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {data.showEcological && data.ecological?.badge ? (
                  <span
                    className={cn(
                      "rounded-md px-2 py-0.5 text-[11px] font-semibold",
                      data.ecological.rare
                        ? "bg-amber-400/90 text-amber-950"
                        : "bg-dark-700 text-[var(--color-text-primary)]",
                    )}
                    title={data.ecological.label}
                  >
                    {data.ecological.badge}
                  </span>
                ) : null}
                {data.behaviorLabel ? (
                  <span className="rounded-md bg-dark-700 px-2 py-0.5 text-[11px] font-semibold text-[var(--color-text-primary)]">
                    {data.behaviorIcon} {data.behaviorLabel}
                  </span>
                ) : null}
                {data.individualsPeak > 1 ? (
                  <span
                    className="rounded-md bg-sky-500/85 px-2 py-0.5 text-[11px] font-semibold text-white"
                    title={data.individualsSummary ?? `${data.individualsPeak} aves`}
                  >
                    👥 {data.individualsPeak} indivíduos
                  </span>
                ) : null}
              </div>
            </div>

            {/* Índice de certeza da IA */}
            <div>
              <div className="mb-1 flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                <span className="inline-flex items-center gap-1">
                  <Activity className="h-3.5 w-3.5 text-emerald-400/80" />
                  Escore de confiança da IA
                </span>
                <span className="font-mono font-semibold text-emerald-300">
                  {data.confidencePct}%
                </span>
              </div>
              <div
                className="h-2 w-full overflow-hidden rounded-full bg-dark-700"
                role="meter"
                aria-valuenow={data.confidencePct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Escore de confiança da IA"
              >
                <div
                  className={cn(
                    "h-full rounded-full transition-all",
                    CONFIDENCE_BAR_CLASS[data.tone],
                  )}
                  style={{ width: `${data.confidencePct}%` }}
                />
              </div>
            </div>

            {/* Telemetria do quadro */}
            <div className="grid grid-cols-2 gap-2">
              <MetricTile
                icon={<Crosshair className="h-3.5 w-3.5" />}
                label="Nitidez (Laplacian)"
                value={
                  data.sharpness.value !== null
                    ? data.sharpness.value.toFixed(0)
                    : "—"
                }
                hint={data.sharpness.label}
                valueClassName={SHARPNESS_TONE_CLASS[data.sharpness.tone]}
              />
              <MetricTile
                icon={<Users className="h-3.5 w-3.5" />}
                label="Indivíduos (pico)"
                value={data.individualsPeak > 0 ? String(data.individualsPeak) : "—"}
                hint={data.individualsSummary ?? "Contagem da janela"}
              />
              <MetricTile
                icon={<Clock3 className="h-3.5 w-3.5" />}
                label="Permanência"
                value={formatDwell(visit.dwell_seconds)}
                hint={`às ${formatTime(visit.detected_at)}`}
              />
              <MetricTile
                icon={<Camera className="h-3.5 w-3.5" />}
                label="Câmera"
                value={visit.camera_name ?? "—"}
                hint={visit.zone_id ? "Zona monitorada" : "Fluxo principal"}
                truncate
              />
            </div>

            {/* Clima no momento do registro */}
            <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
              <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                <Thermometer className="h-3 w-3" />
                Clima no momento do registro
              </p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-[var(--color-text-primary)]">
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden>{weatherEmoji(visit.weather_code)}</span>
                  {formatTemperature(visit.temperature)}
                </span>
                <span className="inline-flex items-center gap-1.5 text-[var(--color-text-muted)]">
                  <Droplets className="h-3.5 w-3.5 text-sky-300" />
                  {formatHumidity(visit.humidity)}
                </span>
                <span className="inline-flex items-center gap-1.5 text-[var(--color-text-muted)]">
                  <Wind className="h-3.5 w-3.5 text-cyan-300" />
                  {formatWind(visit.wind_speed)}
                </span>
                {visit.weather_code ? (
                  <span className="text-[var(--color-text-muted)]">
                    {visit.weather_code}
                  </span>
                ) : null}
              </div>
            </div>

            {/* Anotação ornitológica da IA */}
            {data.annotation ? (
              <p className="rounded-xl border border-emerald-500/15 bg-emerald-500/5 p-3 text-[11px] italic leading-snug text-emerald-200/85">
                🧠 {data.annotation}
              </p>
            ) : null}

            {/* Ações */}
            <div className="flex flex-col gap-2 pt-1">
              {visit.species_id ? (
                <button
                  type="button"
                  onClick={() => void handleConfirm()}
                  disabled={confirming}
                  title="Confirmar que esta detecção está correta e ensinar o Bem-Te-Vi Core"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-4 py-2.5 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:cursor-wait disabled:opacity-60"
                >
                  {confirming ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4" />
                  )}
                  {confirming ? "Confirmando…" : "Confirmar detecção"}
                </button>
              ) : null}
              {confirmMessage ? (
                <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
                  {confirmMessage}
                </p>
              ) : null}
              {confirmError ? (
                <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                  {confirmError}
                </p>
              ) : null}
              <button
                type="button"
                disabled={!data.clip}
                title={
                  data.clip
                    ? "Abrir o clipe completo na Galeria"
                    : "Clipe indisponível para esta visita"
                }
                onClick={() => {
                  onOpenInGallery(visit.id);
                  onClose();
                }}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Film className="h-4 w-4" />
                Ver clipe de 6 s na Galeria
                <Play className="h-3.5 w-3.5 fill-current" />
              </button>
              <button
                type="button"
                onClick={() => setConsultOpen(true)}
                title="Perguntar à IA externa (ficha ornitológica completa)"
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-violet-400/40 bg-violet-500/15 px-4 py-2.5 text-sm font-semibold text-violet-200 transition hover:bg-violet-500/25"
              >
                <Bot className="h-4 w-4" />
                Perguntar à IA Externa
              </button>
              {/* Download do recorte HD e curadoria da espécie. */}
              <div className="flex flex-col gap-2 sm:flex-row">
                {visit.metadata?.crop_path ? (
                  <a
                    href={visitCropDownloadUrl(visit.id)}
                    download
                    title="Baixar o recorte da ave em alta resolução (JPEG HD)"
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-sky-400/40 bg-sky-500/10 px-4 py-2.5 text-sm font-semibold text-sky-200 transition hover:bg-sky-500/20"
                  >
                    <ImageDown className="h-4 w-4" />
                    Baixar Recorte HD (Crop)
                  </a>
                ) : null}
                <button
                  type="button"
                  onClick={() => setReclassifyOpen(true)}
                  title="A associação está errada? Escolha a espécie correta — o recorte é salvo para o retreinamento do Core"
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-4 py-2.5 text-sm font-semibold text-cyan-200 transition hover:bg-cyan-500/20"
                >
                  <RefreshCw className="h-4 w-4" />
                  Associação Incorreta / Reclassificar
                </button>
              </div>
              {data.frame ? (
                <a
                  href={data.frame}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-dark-600 px-4 py-2 text-xs text-[var(--color-text-muted)] transition hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  Abrir foto tratada em nova aba
                </a>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {/* Ficha ornitológica da IA externa (consulta profunda, por cima). */}
      {consultOpen ? (
        <SpeciesAiConsultModal
          visit={visit}
          onClose={() => setConsultOpen(false)}
        />
      ) : null}

      {/* Curadoria da espécie: "Associação Incorreta / Reclassificar". */}
      {reclassifyOpen ? (
        <ReclassifySpeciesModal
          visit={visit}
          species={catalogSpecies}
          onClose={() => setReclassifyOpen(false)}
          onReclassified={(updated) => {
            setOverride(updated);
            setReclassifyOpen(false);
            onVisitUpdated?.();
          }}
        />
      ) : null}
    </div>
  );
}

/** Botão do seletor de imagem (quadro HD x recorte da ave). */
function ImageButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition",
        active
          ? "bg-emerald-500/20 text-emerald-200"
          : "text-white/70 hover:bg-white/10",
      )}
    >
      {icon}
      {label}
    </button>
  );
}

/** Bloco compacto de telemetria (rótulo, valor e dica). */
function MetricTile({
  icon,
  label,
  value,
  hint,
  valueClassName,
  truncate = false,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint?: string;
  valueClassName?: string;
  truncate?: boolean;
}) {
  return (
    <div className="rounded-xl border border-dark-700 bg-dark-900/60 p-3">
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
        {icon}
        {label}
      </p>
      <p
        className={cn(
          "mt-1 font-mono text-lg font-semibold tabular-nums text-[var(--color-text-primary)]",
          truncate && "truncate font-sans text-sm",
          valueClassName,
        )}
        title={value}
      >
        {value}
      </p>
      {hint ? (
        <p className="truncate text-[10px] text-[var(--color-text-muted)]" title={hint}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
