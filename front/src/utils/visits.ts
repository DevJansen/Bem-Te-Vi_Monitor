/**
 * Utilitários de apresentação das visitas (Painel · Visitas de Hoje).
 *
 * Concentra a leitura "defensiva" dos metadados que o Alaris Core grava na
 * visita (identificação, status ecológico, nitidez do quadro, clima) para que os
 * componentes fiquem limpos e não repitam regras de negócio.
 */

import type { BirdSpecies, BirdVisit } from "@/types";
import { formatSpeciesLabel, isGenericSpecies } from "@/utils/format";

/** Nomes popular e científico resolvidos (catálogo, IA externa ou metadados). */
export function resolveVisitNames(visit: BirdVisit): {
  commonName: string;
  scientificName: string | null;
} {
  const external = visit.metadata?.external_identification;
  const analysis = visit.metadata?.ai_analysis;
  // Candidatos a nome popular — ignorando rótulos genéricos do detector
  // (ex.: "bird"), que não são um nome de espécie de verdade.
  const commonName =
    [
      visit.assigned_species_common_name,
      external?.common_name,
      analysis?.species,
    ]
      .map((candidate) => candidate?.trim() ?? "")
      .find((candidate) => candidate && !isGenericSpecies(candidate)) ?? "";
  const scientificName =
    [
      visit.assigned_species_scientific_name,
      external?.scientific_name,
      analysis?.scientific_name,
    ]
      .map((candidate) => candidate?.trim() ?? "")
      .find((candidate) => candidate && !isGenericSpecies(candidate)) ?? null;
  return { commonName, scientificName };
}

/**
 * Rótulo da espécie da visita: nome popular identificado ou, quando ainda não
 * houve identificação, o rótulo oficial **"Pássaro Desconhecido"**.
 */
export function resolveVisitSpeciesLabel(visit: BirdVisit): string {
  // Visitantes Especiais (esquilos, gatos…) não são aves: exibem o rótulo do
  // grupo em vez de tentar resolver um nome de espécie de ave.
  if (visit.visitor_kind && visit.visitor_kind !== "bird") {
    const visitorMeta = (visit.metadata?.visitor ?? {}) as {
      label?: string;
      icon?: string;
    };
    if (visitorMeta.label) {
      return visitorMeta.icon
        ? `${visitorMeta.icon} ${visitorMeta.label}`
        : visitorMeta.label;
    }
    return visit.visitor_group
      ? `🐾 ${visit.visitor_group}`
      : "Visitante Especial";
  }
  return resolveVisitNames(visit).commonName || formatSpeciesLabel(visit.species);
}

/** Status ecológico regional pronto para exibição (selo + rótulo). */
export type EcologicalInfo = {
  /** Selo completo com emoji (ex.: "🟢 Nativa"). */
  badge: string | null;
  /** Rótulo textual (ex.: "Rara / Acidental"). */
  label: string;
  /** Código cru do status (ex.: "rara"). */
  status: string;
  /** Espécie rara/acidental — merece destaque visual. */
  rare: boolean;
};

/**
 * Resolve o status ecológico da visita: prioriza os metadados gravados pelo
 * Alaris na captura, cai para a análise de IA e, por fim, para o Catálogo Local.
 */
export function resolveEcological(
  visit: BirdVisit,
  catalogEntry?: BirdSpecies,
): EcologicalInfo | null {
  const eco = visit.metadata?.ecological;
  const analysis = visit.metadata?.ai_analysis;
  const badge =
    eco?.badge ??
    analysis?.ecological_badge ??
    catalogEntry?.ecological_badge ??
    null;
  const status =
    eco?.status ??
    analysis?.ecological_status ??
    catalogEntry?.ecological_status ??
    "";
  const label =
    eco?.label ??
    analysis?.ecological_label ??
    catalogEntry?.ecological_status_label ??
    "";
  if (!badge && !status) return null;
  return {
    badge: badge ?? null,
    label: label || status,
    status,
    rare: status === "rara",
  };
}

/** Qualidade do quadro escolhido pelo Alaris (índice de nitidez / Laplacian). */
export type SharpnessInfo = {
  /** Variância do Laplaciano do quadro (quanto maior, mais nítido). */
  value: number | null;
  /** Rótulo qualitativo em pt-BR. */
  label: string;
  /** Tom visual para colorir o selo. */
  tone: "alta" | "media" | "baixa" | "indisponivel";
};

/** Escala de referência do backend (`BEST_FRAME_SHARPNESS_SCALE`). */
const SHARPNESS_SCALE = 120;

/** Interpreta o índice de nitidez (Laplacian Variance) do melhor quadro. */
export function resolveSharpness(visit: BirdVisit): SharpnessInfo {
  const raw = visit.metadata?.best_frame_sharpness;
  const value = typeof raw === "number" && Number.isFinite(raw) ? raw : null;
  if (value === null) {
    return { value: null, label: "Não medida", tone: "indisponivel" };
  }
  if (visit.metadata?.best_frame_sharpness_ok === false) {
    return { value, label: "Desfoque (fallback)", tone: "baixa" };
  }
  if (value >= SHARPNESS_SCALE) return { value, label: "Nítido", tone: "alta" };
  if (value >= SHARPNESS_SCALE * 0.4) {
    return { value, label: "Aceitável", tone: "media" };
  }
  return { value, label: "Baixa nitidez", tone: "baixa" };
}

/** Tom do índice de certeza da IA (0..1). */
export function confidenceTone(confidence: number): "alta" | "media" | "baixa" {
  if (confidence >= 0.8) return "alta";
  if (confidence >= 0.5) return "media";
  return "baixa";
}

/** Classes Tailwind da barra/valor do índice de certeza. */
export const CONFIDENCE_BAR_CLASS: Record<
  ReturnType<typeof confidenceTone>,
  string
> = {
  alta: "bg-emerald-400",
  media: "bg-amber-400",
  baixa: "bg-red-400",
};

/** Classes Tailwind do tom de nitidez. */
export const SHARPNESS_TONE_CLASS: Record<SharpnessInfo["tone"], string> = {
  alta: "text-emerald-300",
  media: "text-amber-300",
  baixa: "text-red-300",
  indisponivel: "text-[var(--color-text-muted)]",
};

/** Janela (ms) em que uma visita ainda é considerada "novo registro". */
export const FRESH_VISIT_WINDOW_MS = 60_000;

/**
 * Tolerância para relógios levemente dessincronizados: o `now` do painel é um
 * estado atualizado por intervalo (pode estar alguns segundos "atrás" do
 * horário real da visita), então aceitamos um pequeno delta negativo.
 */
const CLOCK_SKEW_TOLERANCE_MS = 5_000;

/** Indica se a visita acabou de acontecer (destaque "Novo Registro ✨"). */
export function isFreshVisit(
  detectedAt: string,
  now: number,
  windowMs = FRESH_VISIT_WINDOW_MS,
): boolean {
  const timestamp = new Date(detectedAt).getTime();
  if (Number.isNaN(timestamp)) return false;
  const delta = now - timestamp;
  return delta <= windowMs && delta >= -CLOCK_SKEW_TOLERANCE_MS;
}

/** Tempo relativo curto em pt-BR (ex.: "há 2 min", "agora mesmo"). */
export function formatRelativeTime(detectedAt: string, now: number): string {
  const timestamp = new Date(detectedAt).getTime();
  if (Number.isNaN(timestamp)) return "";
  const seconds = Math.max(0, Math.round((now - timestamp) / 1000));
  if (seconds < 45) return "agora mesmo";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  return `há ${Math.round(hours / 24)} d`;
}

/** Duração de permanência formatada (ex.: "12 s", "1 min 05 s"). */
export function formatDwell(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total} s`;
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes} min ${String(rest).padStart(2, "0")} s`;
}
