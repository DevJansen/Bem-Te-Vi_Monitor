const dateFmt = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
});

const timeFmt = new Intl.DateTimeFormat("pt-BR", {
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return dateFmt.format(d);
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return timeFmt.format(d);
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/**
 * Normaliza um rótulo para comparação: minúsculas, sem acentos e com espaços
 * colapsados. Assim "Pássaro Desconhecido", "Passaro Desconhecido" e
 * "PASSARO  DESCONHECIDO" caem todos na mesma chave.
 */
function normalizarRotulo(valor: string): string {
  return valor
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ");
}

/**
 * Rótulos genéricos do detector (YOLO/BirdNET) que significam apenas
 * "ave não identificada". A nomenclatura oficial do Bem-Ti-Vi é
 * **"Pássaro Desconhecido"** — nunca "Ave Genérica" nem "Bird".
 *
 * As chaves estão já sem acento (ver `normalizarRotulo`).
 */
const ROTULOS_GENERICOS = new Set([
  "",
  "bird",
  "ave",
  "aves",
  "passaro",
  "passaros",
  "passaro desconhecido",
  "ave generica",
  "ave (generica)",
  "passaro (generico)",
  "ave nao identificada",
  "nao identificada",
  "desconhecida",
  "desconhecido",
  "unidentified",
  "unknown",
]);

/** Indica se o rótulo de espécie é genérico (não houve identificação real). */
export function isGenericSpecies(species: string | null | undefined): boolean {
  return ROTULOS_GENERICOS.has(normalizarRotulo(species ?? ""));
}

export function formatSpeciesLabel(species: string): string {
  if (isGenericSpecies(species)) return "Pássaro Desconhecido";
  return species.charAt(0).toUpperCase() + species.slice(1);
}

/** Rótulo curto de espécie para selos compactos (ex.: `bird` → "Desconhecido"). */
export function formatSpeciesShort(species: string): string {
  if (isGenericSpecies(species)) return "Desconhecido";
  return species.charAt(0).toUpperCase() + species.slice(1);
}

export function peakHourFromMap(visitsByHour: Record<string, number>): string {
  const entries = Object.entries(visitsByHour);
  if (entries.length === 0) return "—";
  const [hour] = entries.reduce((best, cur) => (cur[1] > best[1] ? cur : best));
  const h = hour.padStart(2, "0");
  return `${h}h`;
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    idle: "Ociosa",
    connecting: "Conectando",
    online: "Online",
    reconnecting: "Reconectando",
    error: "Erro",
    stopped: "Parada",
    disabled: "Desligada",
  };
  return map[status] ?? status;
}
