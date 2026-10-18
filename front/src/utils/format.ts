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
 * Rótulos genéricos do detector (YOLO/BirdNET) que significam apenas
 * "ave não identificada". A nomenclatura oficial do Bem-Ti-Vi é
 * **"Pássaro Desconhecido"** — nunca "Ave Genérica" nem "Bird".
 */
const ROTULOS_GENERICOS = new Set([
  "",
  "bird",
  "ave",
  "aves",
  "passaro",
  "passaros",
  "passaro desconhecido",
  "pássaro desconhecido",
  "ave generica",
  "ave genérica",
  "ave (generica)",
  "ave nao identificada",
  "ave não identificada",
  "nao identificada",
  "não identificada",
  "desconhecida",
  "desconhecido",
  "unidentified",
  "unknown",
]);

/** Indica se o rótulo de espécie é genérico (não houve identificação real). */
export function isGenericSpecies(species: string | null | undefined): boolean {
  return ROTULOS_GENERICOS.has((species ?? "").trim().toLowerCase());
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
