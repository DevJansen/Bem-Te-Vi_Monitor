/**
 * Utilitários de apresentação das visitas (Painel · Visitas de Hoje).
 *
 * Concentra a leitura "defensiva" dos metadados que o Bem-Te-Vi Core grava na
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

/**
 * Badge de identificação da visita (substitui a antiga tag "Desconhecido").
 *
 * O Painel Principal deixou de exibir o status estático "Desconhecido" para
 * aves que já possuem correspondência no catálogo local. Agora a visita mostra
 * um selo elegante que explica **como** a espécie foi resolvida:
 *
 * * **Identificado pelo Bem-Te-Vi Core** — associação automática por re-ID visual
 *   (similaridade de cosseno acima de 65% com as fotos de referência);
 * * **Espécie Confirmada** — curadoria humana (confirmação, reclassificação ou
 *   identificação pela IA externa).
 */
export type IdentificationBadge = {
  /** Texto exibido no selo. */
  label: string;
  /** Texto explicativo (tooltip). */
  title: string;
  /** Tom visual do selo. */
  tone: "core" | "confirmada";
  /** Classes Tailwind prontas para uso. */
  className: string;
};

/** Classes Tailwind do selo de identificação. */
export const IDENTIFICATION_BADGE_CLASS: Record<
  IdentificationBadge["tone"],
  string
> = {
  core: "border-cyan-400/30 bg-cyan-500/15 text-cyan-200",
  confirmada: "border-emerald-400/30 bg-emerald-500/15 text-emerald-200",
};

/**
 * Resolve o selo de identificação da visita (ou ``null`` quando a ave segue
 * sem espécie — nesse caso não mostramos nenhum "status" genérico).
 */
export function resolveIdentificationBadge(
  visit: BirdVisit,
): IdentificationBadge | null {
  // Visitantes Especiais (esquilos, gatos…) não são aves: o painel usa o
  // grupo do visitante, não um status de identificação de espécie.
  if (visit.visitor_kind && visit.visitor_kind !== "bird") return null;

  const metadata = visit.metadata ?? {};
  const status = metadata.identification_status ?? "";
  const auto = metadata.auto_association;

  if (status === "Espécie Confirmada" || status === "Confirmado pelo usuário") {
    return {
      label: "Espécie Confirmada",
      title: "Identificação confirmada por você (curadoria do observador).",
      tone: "confirmada",
      className: IDENTIFICATION_BADGE_CLASS.confirmada,
    };
  }

  if (status === "Reclassificado pelo usuário") {
    return {
      label: "Espécie Confirmada",
      title:
        "Associação corrigida por você — o recorte foi salvo para o retreinamento.",
      tone: "confirmada",
      className: IDENTIFICATION_BADGE_CLASS.confirmada,
    };
  }

  if (status === "Identificado por IA Externa") {
    return {
      label: "Espécie Confirmada",
      title: "Espécie resolvida pela consulta à IA externa (ficha ornitológica).",
      tone: "confirmada",
      className: IDENTIFICATION_BADGE_CLASS.confirmada,
    };
  }

  // Compatibilidade: visitas gravadas antes do rebranding carregam o rótulo
  // antigo ("Alaris Core") e continuam exibindo o mesmo selo.
  const statusCore =
    status === "Identificado pelo Bem-Te-Vi Core" ||
    status === "Identificado pelo Alaris Core";

  if (statusCore || auto?.applied) {
    const score =
      typeof auto?.score === "number" ? Math.round(auto.score * 100) : null;
    return {
      label: "Identificado pelo Bem-Te-Vi Core",
      title: score
        ? `Associação automática por similaridade visual (${score}%) com as fotos de "Minhas Aves".`
        : 'Associação automática por similaridade visual com as fotos de "Minhas Aves".',
      tone: "core",
      className: IDENTIFICATION_BADGE_CLASS.core,
    };
  }

  return null;
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
 * Bem-Te-Vi Core na captura, cai para a análise de IA e, por fim, para o Catálogo Local.
 *
 * Exceção importante: quando o status da captura é **"desconhecida"** (a ave
 * ainda não era identificada no momento do registro) e o Catálogo Local já
 * conhece a espécie, o status do catálogo tem prioridade — evita exibir o
 * selo estático "⚪ Status desconhecido" em uma ave já identificada.
 */
export function resolveEcological(
  visit: BirdVisit,
  catalogEntry?: BirdSpecies,
): EcologicalInfo | null {
  const eco = visit.metadata?.ecological;
  const analysis = visit.metadata?.ai_analysis;
  let badge =
    eco?.badge ??
    analysis?.ecological_badge ??
    catalogEntry?.ecological_badge ??
    null;
  let status =
    eco?.status ??
    analysis?.ecological_status ??
    catalogEntry?.ecological_status ??
    "";
  let label =
    eco?.label ??
    analysis?.ecological_label ??
    catalogEntry?.ecological_status_label ??
    "";

  // Status da captura inconclusivo → o catálogo local (que já conhece a
  // espécie) tem a informação mais precisa.
  if (status === "desconhecida" && catalogEntry?.ecological_status) {
    badge = catalogEntry.ecological_badge ?? badge;
    status = catalogEntry.ecological_status;
    label = catalogEntry.ecological_status_label ?? label;
  }
  if (!badge && !status) return null;
  return {
    badge: badge ?? null,
    label: label || status,
    status,
    rare: status === "rara",
  };
}

/**
 * Indica se o status ecológico é o placeholder "desconhecido".
 *
 * Nesse caso o selo **não** deve ser exibido: o painel já comunica o estado da
 * identificação pelo badge elegante ("Identificado pelo Bem-Te-Vi Core" ou
 * "Espécie Confirmada"), e a tag estática "Status desconhecido" só poluiria a
 * interface.
 */
export function isEcologicalUnknown(
  ecological: EcologicalInfo | null | undefined,
): boolean {
  if (!ecological) return false;
  return (
    ecological.status === "desconhecida" ||
    ecological.badge?.includes("desconhecido") === true
  );
}

/** Qualidade do quadro escolhido pelo Bem-Te-Vi Core (índice de nitidez / Laplacian). */
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
