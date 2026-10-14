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

export function formatSpeciesLabel(species: string): string {
  if (!species || species === "bird") return "Ave (genérica)";
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
