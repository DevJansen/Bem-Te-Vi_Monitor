import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  ChevronDown,
  Eye,
  EyeOff,
  Globe2,
  KeyRound,
  Link2,
  LoaderCircle,
  Lock,
  MapPin,
  Plus,
  Search,
  Webcam,
  X,
  Youtube,
} from "lucide-react";
import type { CameraCreatePayload, GeoLocation, SourceType } from "@/types";
import { geocodeLocation } from "@/services/api";
import { cn } from "@/utils/cn";

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: CameraCreatePayload) => Promise<void>;
};

type Modo = "stream" | "usb";

/** Detecta o tipo de fonte a partir do link colado (Smart Stream Resolver). */
function detectarTipo(url: string): SourceType {
  const v = url.trim().toLowerCase();
  if (!v) return "rtsp";
  if (v.startsWith("rtsp://") || v.startsWith("rtsps://")) return "rtsp";
  if (v.startsWith("ws://") || v.startsWith("wss://")) return "webrtc";
  if (v.includes(".m3u8")) return "hls";
  if (v.startsWith("http://") || v.startsWith("https://")) return "http";
  return "rtsp";
}

/** Detecta se o link é de uma live/vídeo do YouTube (traduzido no backend). */
function isYouTubeLink(url: string): boolean {
  return /(youtube\.com|youtu\.be)/i.test(url.trim());
}

const TIPO_LABEL: Record<SourceType, string> = {
  usb: "Webcam / USB",
  rtsp: "RTSP",
  hls: "HLS",
  http: "HTTP / MJPEG",
  webrtc: "WebRTC",
  onvif: "ONVIF",
};

export function AddCameraModal({ open, onClose, onSubmit }: Props) {
  const [modo, setModo] = useState<Modo>("stream");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [usbIndex, setUsbIndex] = useState("0");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [mostrarCredenciais, setMostrarCredenciais] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // --- Localização & fuso horário (opcional, câmeras globais/remotas) ---
  const [mostrarLocalizacao, setMostrarLocalizacao] = useState(false);
  const [location, setLocation] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [timezone, setTimezone] = useState("");
  const [country, setCountry] = useState("");
  const [geocodeResults, setGeocodeResults] = useState<GeoLocation[]>([]);
  const [geocodeLoading, setGeocodeLoading] = useState(false);
  const [geocodeError, setGeocodeError] = useState<string | null>(null);
  const [geocodeFeito, setGeocodeFeito] = useState(false);

  const tipoDetectado = useMemo(() => detectarTipo(url), [url]);
  const linkComCredenciais = /\/\/[^/@\s]+:[^/@\s]+@/.test(url);
  const linkYouTube = useMemo(() => isYouTubeLink(url), [url]);
  const temCoordenadas = latitude.trim() !== "" && longitude.trim() !== "";

  if (!open) return null;

  const reset = () => {
    setModo("stream");
    setName("");
    setUrl("");
    setUsbIndex("0");
    setUsername("");
    setPassword("");
    setShowPassword(false);
    setMostrarCredenciais(false);
    setEnabled(true);
    setError(null);
    setMostrarLocalizacao(false);
    setLocation("");
    setLatitude("");
    setLongitude("");
    setTimezone("");
    setCountry("");
    setGeocodeResults([]);
    setGeocodeLoading(false);
    setGeocodeError(null);
    setGeocodeFeito(false);
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  /** Aplica uma localidade escolhida no seletor de cidade inteligente. */
  const aplicarLocalizacao = (local: GeoLocation) => {
    setLatitude(String(local.latitude));
    setLongitude(String(local.longitude));
    setTimezone(local.timezone ?? "");
    setCountry(local.country ?? "");
    if (!location.trim()) setLocation(local.label);
    setGeocodeResults([]);
    setGeocodeFeito(false);
  };

  const limparLocalizacao = () => {
    setLatitude("");
    setLongitude("");
    setTimezone("");
    setCountry("");
    setGeocodeResults([]);
    setGeocodeFeito(false);
  };

  /** Busca a localidade digitada (cidade/país) e mostra as opções. */
  const handleGeocode = async () => {
    const consulta = location.trim();
    if (consulta.length < 2) {
      setGeocodeError("Digite ao menos 2 letras (ex.: Costa Rica).");
      return;
    }
    setGeocodeLoading(true);
    setGeocodeError(null);
    setGeocodeFeito(false);
    try {
      const resultados = await geocodeLocation(consulta);
      setGeocodeResults(resultados);
      setGeocodeFeito(true);
      // Se houver apenas um resultado, já preenche tudo automaticamente.
      if (resultados.length === 1) aplicarLocalizacao(resultados[0]);
    } catch (err) {
      setGeocodeError(
        err instanceof Error ? err.message : "Falha ao buscar a localidade",
      );
    } finally {
      setGeocodeLoading(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const lat = latitude.trim();
      const lon = longitude.trim();
      if ((lat === "") !== (lon === "")) {
        throw new Error(
          "Preencha latitude e longitude juntas (ou deixe ambas vazias).",
        );
      }
      const latitudeNum = lat === "" ? null : Number(lat);
      const longitudeNum = lon === "" ? null : Number(lon);
      if (
        (latitudeNum !== null && !Number.isFinite(latitudeNum)) ||
        (longitudeNum !== null && !Number.isFinite(longitudeNum))
      ) {
        throw new Error("Latitude/longitude inválidas.");
      }

      const usarCredenciais =
        modo === "stream" && mostrarCredenciais && (username || password);
      const payload: CameraCreatePayload = {
        name: name.trim(),
        location_label: location.trim() || undefined,
        enabled,
        source_type: modo === "usb" ? "usb" : tipoDetectado,
        stream_url: modo === "usb" ? usbIndex.trim() : url.trim(),
        latitude: latitudeNum,
        longitude: longitudeNum,
        timezone: timezone.trim() || null,
        country: country.trim() || null,
        username: usarCredenciais && username ? username : null,
        password: usarCredenciais && password ? password : null,
      };
      await onSubmit(payload);
      reset();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao cadastrar câmera");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        className="absolute inset-0 bg-black/70"
        aria-label="Fechar"
        onClick={handleClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-camera-title"
        className="relative z-10 max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-xl border border-dark-700 bg-dark-800 shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-dark-700 px-5 py-4">
          <div>
            <h2
              id="add-camera-title"
              className="font-display text-lg font-semibold text-[var(--color-text-primary)]"
            >
              <span className="inline-flex items-center gap-2">
                <Link2 className="h-4 w-4 text-emerald-400" />
                Adicionar câmera
              </span>
            </h2>
            <p className="mt-0.5 flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
              <Lock className="h-3 w-3 text-emerald-400" />
              Cole o link e conecte — credenciais são opcionais
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-dark-700 hover:text-[var(--color-text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-5 py-4">
          {/* Seletor de origem: stream externo (URL) x webcam local */}
          <div className="flex gap-1 rounded-lg border border-dark-700 bg-dark-900 p-1">
            <button
              type="button"
              onClick={() => setModo("stream")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition",
                modo === "stream"
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
              )}
            >
              <Link2 className="h-3.5 w-3.5" />
              Câmera externa (URL)
            </button>
            <button
              type="button"
              onClick={() => setModo("usb")}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition",
                modo === "usb"
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]",
              )}
            >
              <Webcam className="h-3.5 w-3.5" />
              Webcam local (USB)
            </button>
          </div>

          <Field label="Nome da câmera">
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex.: Comedouro de Beija-Flores"
              className={inputClass}
            />
          </Field>

          {modo === "stream" ? (
            <>
              <Field
                label="URL do Stream ao Vivo (RTSP, HLS, HTTP ou YouTube)"
                hint="Links públicos/abertos conectam direto. Lives do YouTube são traduzidas automaticamente."
              >
                <div className="relative">
                  <Link2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
                  <input
                    required
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="rtsp://... , https://.../stream.m3u8 ou link do YouTube"
                    className={`${inputClass} pl-9 font-mono text-[13px]`}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
              </Field>

              {url.trim() ? (
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="inline-flex items-center gap-1 rounded-md bg-cyan-500/10 px-2 py-0.5 text-cyan-300">
                    Tipo detectado: {TIPO_LABEL[tipoDetectado]}
                  </span>
                  {linkYouTube ? (
                    <span className="inline-flex items-center gap-1 rounded-md bg-red-500/10 px-2 py-0.5 text-red-300">
                      <Youtube className="h-3 w-3" />
                      Live do YouTube (link traduzido automaticamente)
                    </span>
                  ) : null}
                  {linkComCredenciais ? (
                    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-emerald-300">
                      <Lock className="h-3 w-3" />
                      Credenciais no link serão criptografadas
                    </span>
                  ) : null}
                </div>
              ) : null}

              {/* Seção opcional e recolhível de credenciais */}
              <div className="rounded-lg border border-dark-700 bg-dark-900/60">
                <button
                  type="button"
                  onClick={() => setMostrarCredenciais((v) => !v)}
                  aria-expanded={mostrarCredenciais}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
                >
                  <span className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-muted)]">
                    <KeyRound className="h-3.5 w-3.5 text-emerald-400" />
                    Esta câmera exige login e senha?{" "}
                    <span className="text-[var(--color-text-muted)]/60">(Opcional)</span>
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform",
                      mostrarCredenciais && "rotate-180",
                    )}
                  />
                </button>

                {mostrarCredenciais ? (
                  <div className="grid gap-3 border-t border-dark-700 px-3 py-3 sm:grid-cols-2">
                    <Field label="Usuário (criptografado)">
                      <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className={inputClass}
                        autoComplete="off"
                      />
                    </Field>
                    <Field label="Senha (criptografada)">
                      <div className="relative">
                        <input
                          type={showPassword ? "text" : "password"}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          className={`${inputClass} pr-10`}
                          autoComplete="new-password"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword((v) => !v)}
                          aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-[var(--color-text-muted)] transition hover:text-emerald-400"
                        >
                          {showPassword ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    </Field>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <Field
              label="Índice da webcam USB"
              hint="Normalmente 0 para a primeira webcam conectada."
            >
              <input
                required
                value={usbIndex}
                onChange={(e) => setUsbIndex(e.target.value)}
                placeholder="0"
                className={`${inputClass} font-mono`}
              />
            </Field>
          )}

          {/* Seção opcional: localização & fuso horário (câmeras globais/remotas) */}
          <div className="rounded-lg border border-dark-700 bg-dark-900/60">
            <button
              type="button"
              onClick={() => setMostrarLocalizacao((v) => !v)}
              aria-expanded={mostrarLocalizacao}
              className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
            >
              <span className="inline-flex items-center gap-2 text-xs font-medium text-[var(--color-text-muted)]">
                <Globe2 className="h-3.5 w-3.5 text-sky-400" />
                Localização & fuso horário{" "}
                <span className="text-[var(--color-text-muted)]/60">(Opcional)</span>
              </span>
              <ChevronDown
                className={cn(
                  "h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform",
                  mostrarLocalizacao && "rotate-180",
                )}
              />
            </button>

            {mostrarLocalizacao ? (
              <div className="space-y-3 border-t border-dark-700 px-3 py-3">
                <p className="text-[11px] leading-snug text-[var(--color-text-muted)]">
                  Informe onde o jardim está. Câmeras em outros países passam a
                  exibir o <strong>clima</strong> e o <strong>horário locais</strong>{" "}
                  (ex.: sol na Costa Rica enquanto é noite no Brasil) e os gráficos
                  de horário de pico usam o fuso da câmera.
                </p>

                <Field
                  label="Localidade / Cidade / País"
                  hint="Ex.: Costa Rica - Comedouro de Beija-Flores"
                >
                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <MapPin className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
                      <input
                        value={location}
                        onChange={(e) => setLocation(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void handleGeocode();
                          }
                        }}
                        placeholder="Ex.: San José, Costa Rica"
                        className={`${inputClass} pl-9`}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleGeocode()}
                      disabled={geocodeLoading}
                      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-xs font-medium text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-60"
                    >
                      {geocodeLoading ? (
                        <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Search className="h-3.5 w-3.5" />
                      )}
                      Buscar
                    </button>
                  </div>
                </Field>

                {geocodeError ? (
                  <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
                    {geocodeError}
                  </p>
                ) : null}

                {geocodeResults.length > 0 ? (
                  <ul className="space-y-1 rounded-lg border border-dark-700 bg-dark-800 p-1">
                    {geocodeResults.map((local) => (
                      <li key={`${local.latitude}-${local.longitude}-${local.label}`}>
                        <button
                          type="button"
                          onClick={() => aplicarLocalizacao(local)}
                          className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-xs transition hover:bg-dark-700"
                        >
                          <span className="min-w-0 truncate text-[var(--color-text-primary)]">
                            {local.label}
                          </span>
                          <span className="shrink-0 font-mono text-[10px] text-[var(--color-text-muted)]">
                            {local.timezone ?? "—"}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : geocodeFeito ? (
                  <p className="text-[11px] text-amber-300">
                    Nenhuma localidade encontrada. Ajuste o nome ou informe as
                    coordenadas manualmente.
                  </p>
                ) : null}

                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Latitude">
                    <input
                      value={latitude}
                      onChange={(e) => setLatitude(e.target.value)}
                      inputMode="decimal"
                      placeholder="-23.5505"
                      className={`${inputClass} font-mono text-[13px]`}
                    />
                  </Field>
                  <Field label="Longitude">
                    <input
                      value={longitude}
                      onChange={(e) => setLongitude(e.target.value)}
                      inputMode="decimal"
                      placeholder="-46.6333"
                      className={`${inputClass} font-mono text-[13px]`}
                    />
                  </Field>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Fuso horário (IANA)" hint="Preenchido pela busca.">
                    <input
                      value={timezone}
                      onChange={(e) => setTimezone(e.target.value)}
                      placeholder="America/Costa_Rica"
                      className={`${inputClass} font-mono text-[13px]`}
                    />
                  </Field>
                  <Field label="País">
                    <input
                      value={country}
                      onChange={(e) => setCountry(e.target.value)}
                      placeholder="Costa Rica"
                      className={inputClass}
                    />
                  </Field>
                </div>

                {temCoordenadas ? (
                  <div className="flex items-center justify-between gap-2 rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2 text-[11px] text-sky-200">
                    <span className="inline-flex min-w-0 items-center gap-1.5">
                      <Globe2 className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">
                        Clima e horário locais ativados
                        {timezone ? ` · ${timezone}` : ""}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={limparLocalizacao}
                      className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-sky-300 underline-offset-2 hover:underline"
                    >
                      Limpar
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="accent-emerald-500"
            />
            Ativar monitoramento imediatamente
          </label>

          {error ? (
            <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          ) : null}

          <div className="flex items-center justify-between gap-2 border-t border-dark-700 pt-4">
            <p className="hidden items-center gap-1 text-[11px] text-[var(--color-text-muted)] sm:flex">
              <Lock className="h-3 w-3" />
              Nunca expomos sua URL/senha no navegador
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-dark-700 px-4 py-2 text-sm text-[var(--color-text-muted)] hover:bg-dark-700"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:opacity-60"
              >
                <Plus className="h-4 w-4" />
                {submitting ? "Conectando…" : "Salvar e conectar"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-[var(--color-text-muted)]">
        {label}
      </span>
      {children}
      {hint ? (
        <span className="mt-1 block text-[11px] text-[var(--color-text-muted)]">{hint}</span>
      ) : null}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none transition placeholder:text-[var(--color-text-muted)]/60 focus:border-emerald-500/50";
