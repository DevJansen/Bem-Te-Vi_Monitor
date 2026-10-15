import { useEffect, useState } from "react";
import {
  Bird,
  CheckCircle2,
  Gauge,
  LoaderCircle,
  RotateCcw,
  Sparkles,
  Timer,
  Zap,
} from "lucide-react";
import type { Calibration, CalibrationProfile } from "@/types";
import {
  fetchCalibration,
  getErrorMessage,
  updateCalibration,
} from "@/services/api";

/** Limites de confiança do YOLO aceitos pelo backend. */
const CONF_MIN = 0.05;
const CONF_MAX = 1.0;
/** Limites (segundos) do controle de permanência imóvel. */
const PERSISTENCE_MIN = 3;
const PERSISTENCE_MAX = 15;

/** Converte a confiança do YOLO (menor = mais sensível) para 0–100 no slider. */
function confidenceToSensitivity(confidence: number): number {
  const ratio = (confidence - CONF_MIN) / (CONF_MAX - CONF_MIN);
  return Math.round((1 - ratio) * 100);
}

/** Converte o valor do slider (0 = rigoroso, 100 = sensível) em confiança. */
function sensitivityToConfidence(sensitivity: number): number {
  const confidence = CONF_MIN + (1 - sensitivity / 100) * (CONF_MAX - CONF_MIN);
  return Number(confidence.toFixed(2));
}

type Props = {
  onCalibrationChange?: (calibration: Calibration) => void;
};

export function CalibrationPanel({ onCalibrationChange }: Props) {
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [confidence, setConfidence] = useState(0.3);
  const [persistence, setPersistence] = useState(5);
  const [motion, setMotion] = useState(50);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applyLoaded = (data: Calibration) => {
    setCalibration(data);
    setConfidence(data.yolo_confidence);
    setPersistence(
      Math.min(PERSISTENCE_MAX, Math.max(PERSISTENCE_MIN, data.object_persistence_time)),
    );
    setMotion(Math.round(data.motion_sensitivity * 100));
    onCalibrationChange?.(data);
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      applyLoaded(await fetchCalibration());
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao carregar a calibração"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!message) return;
    const timeout = window.setTimeout(() => setMessage(null), 4000);
    return () => window.clearTimeout(timeout);
  }, [message]);

  /** Seleciona um perfil pronto (aplicação em um clique). */
  const selectProfile = async (profile: CalibrationProfile) => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await updateCalibration({ profile });
      applyLoaded(updated);
      setMessage(
        profile === "stationary"
          ? "Perfil \"Passarinhos Parados\" aplicado."
          : "Perfil \"Alta Movimentação\" aplicado.",
      );
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao aplicar o perfil"));
    } finally {
      setSaving(false);
    }
  };

  /** Aplica os ajustes manuais dos sliders. */
  const applyManual = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const updated = await updateCalibration({
        yolo_confidence: confidence,
        object_persistence_time: persistence,
        motion_sensitivity: motion / 100,
      });
      applyLoaded(updated);
      setMessage("Calibração manual aplicada.");
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao salvar a calibração"));
    } finally {
      setSaving(false);
    }
  };

  if (loading && !calibration) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        Carregando calibração…
      </p>
    );
  }

  const activeProfile = calibration?.profile ?? "custom";
  const sensitivity = confidenceToSensitivity(confidence);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
          Calibração e Ajustes
        </h2>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          Ajuste a sensibilidade da IA para reconhecer pássaros que ficam parados
          se alimentando. Escolha um perfil pronto ou use os controles avançados.
          As mudanças são aplicadas na hora, sem reiniciar o sistema.
        </p>
      </div>

      {/* ——— Perfis prontos ——— */}
      <div className="grid gap-3 md:grid-cols-2">
        <ProfileCard
          title="Passarinhos Parados / Alimentador"
          badge="Recomendado"
          icon={<Bird className="h-5 w-5" />}
          description="Ideal para bebedouros e comedouros. Mantém o foco no passarinho mesmo se ele ficar imóvel por vários segundos comendo."
          selected={activeProfile === "stationary"}
          disabled={saving}
          onClick={() => void selectProfile("stationary")}
        />
        <ProfileCard
          title="Alta Movimentação / Voo Rápido"
          badge={null}
          icon={<Zap className="h-5 w-5" />}
          description="Ideal para capturar aves em movimento rápido. Aumenta a velocidade de captura, mas pode ignorar pássaros parados."
          selected={activeProfile === "fast_motion"}
          disabled={saving}
          onClick={() => void selectProfile("fast_motion")}
        />
      </div>

      {/* ——— Controles manuais avançados ——— */}
      <div className="rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
        <div className="mb-4 flex items-center gap-2">
          <Gauge className="h-4 w-4 text-emerald-400" />
          <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
            Controles manuais avançados
          </h3>
          {activeProfile === "custom" ? (
            <span className="ml-auto rounded-md bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-300">
              Ajuste personalizado
            </span>
          ) : null}
        </div>

        <div className="space-y-6">
          <SliderField
            icon={<Sparkles className="h-4 w-4" />}
            label="Sensibilidade da IA (confiança)"
            leftLabel="Rigorosa (menos falsos alarmes)"
            rightLabel="Sensível (pega pássaros distantes/escondidos)"
            min={0}
            max={100}
            step={1}
            value={sensitivity}
            onChange={(value) => setConfidence(sensitivityToConfidence(value))}
            tooltip="Quanto mais sensível, menor a certeza exigida da IA para marcar um pássaro. Útil para aves pequenas, distantes ou com pouca luz. Excesso de sensibilidade pode gerar falsos alarmes."
            valueLabel={`${sensitivity}% · confiança ${Math.round(confidence * 100)}%`}
          />

          <SliderField
            icon={<Timer className="h-4 w-4" />}
            label="Tempo de permanência imóvel"
            leftLabel="Rápido (3s)"
            rightLabel="Paciente (15s)"
            min={PERSISTENCE_MIN}
            max={PERSISTENCE_MAX}
            step={1}
            value={persistence}
            onChange={setPersistence}
            tooltip="Tempo que a visita continua registrada mesmo se o pássaro ficar totalmente parado comendo. Valores maiores evitam que a visita seja encerrada enquanto a ave está imóvel."
            valueLabel={`${persistence}s`}
          />

          <SliderField
            icon={<Gauge className="h-4 w-4" />}
            label="Sensibilidade de movimento inicial"
            leftLabel="Conservadora"
            rightLabel="Muito sensível"
            min={0}
            max={100}
            step={1}
            value={motion}
            onChange={setMotion}
            tooltip="Controla o quanto de movimento é preciso para a IA começar a procurar uma ave. Mais sensível detecta aves que chegam com pouca movimentação; menos sensível reduz o esforço em cenas muito ruidosas."
            valueLabel={`${motion}%`}
          />
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-dark-700 pt-4">
          <button
            type="button"
            onClick={() => void applyManual()}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-dark-900 transition hover:bg-emerald-400 disabled:opacity-60"
          >
            {saving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
            {saving ? "Aplicando…" : "Aplicar calibração"}
          </button>
          <button
            type="button"
            onClick={() => void selectProfile("stationary")}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg border border-dark-700 px-4 py-2 text-sm font-medium text-[var(--color-text-muted)] transition hover:text-emerald-300 disabled:opacity-60"
          >
            <RotateCcw className="h-4 w-4" />
            Restaurar recomendado
          </button>
        </div>
      </div>

      {message ? (
        <p
          role="status"
          className="fixed bottom-5 right-5 z-50 rounded-lg border border-emerald-500/30 bg-emerald-950 px-4 py-3 text-sm text-emerald-300 shadow-xl"
        >
          {message}
        </p>
      ) : null}
      {error ? (
        <p
          role="alert"
          className="fixed bottom-5 right-5 z-50 max-w-sm rounded-lg border border-red-500/30 bg-red-950 px-4 py-3 text-sm text-red-300 shadow-xl"
        >
          {error}
        </p>
      ) : null}
    </section>
  );
}

function ProfileCard({
  title,
  badge,
  icon,
  description,
  selected,
  disabled,
  onClick,
}: {
  title: string;
  badge: string | null;
  icon: React.ReactNode;
  description: string;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      className={`relative rounded-xl border p-4 text-left transition disabled:opacity-60 ${
        selected
          ? "border-emerald-500/60 bg-emerald-500/10 ring-1 ring-emerald-500/40"
          : "border-dark-700 bg-dark-800 hover:border-emerald-500/30"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={selected ? "text-emerald-400" : "text-[var(--color-text-muted)]"}>
          {icon}
        </span>
        <h3 className="font-display text-sm font-semibold text-[var(--color-text-primary)]">
          {title}
        </h3>
        {badge ? (
          <span className="ml-auto rounded-md bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
            {badge}
          </span>
        ) : null}
      </div>
      <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-muted)]">
        {description}
      </p>
      {selected ? (
        <span className="mt-3 inline-flex items-center gap-1 text-[11px] font-medium text-emerald-300">
          <CheckCircle2 className="h-3.5 w-3.5" /> Perfil ativo
        </span>
      ) : null}
    </button>
  );
}

function SliderField({
  icon,
  label,
  leftLabel,
  rightLabel,
  min,
  max,
  step,
  value,
  onChange,
  tooltip,
  valueLabel,
}: {
  icon: React.ReactNode;
  label: string;
  leftLabel: string;
  rightLabel: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
  tooltip: string;
  valueLabel: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="text-emerald-400">{icon}</span>
        <label className="text-sm font-medium text-[var(--color-text-primary)]">
          {label}
        </label>
        <span className="ml-auto rounded-md bg-dark-900 px-2 py-0.5 text-xs font-semibold text-emerald-300">
          {valueLabel}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-3 w-full cursor-pointer accent-emerald-500"
      />
      <div className="mt-1 flex justify-between text-[11px] text-[var(--color-text-muted)]">
        <span>{leftLabel}</span>
        <span>{rightLabel}</span>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-[var(--color-text-muted)]">
        {tooltip}
      </p>
    </div>
  );
}
