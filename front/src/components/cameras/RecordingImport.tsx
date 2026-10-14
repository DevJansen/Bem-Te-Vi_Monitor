import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Film, LoaderCircle, Upload } from "lucide-react";
import type { Camera, RecordingAnalysis } from "@/types";
import {
  fetchRecordingAnalysis,
  getErrorMessage,
  importRecording,
} from "@/services/api";

type Props = {
  cameras: Camera[];
  onCompleted: () => void;
};

const MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".mp4", ".avi", ".mkv"];

export function RecordingImport({ cameras, onCompleted }: Props) {
  const [cameraId, setCameraId] = useState(cameras[0]?.id ?? "");
  const [job, setJob] = useState<RecordingAnalysis | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const completedJobId = useRef<string | null>(null);
  const onCompletedRef = useRef(onCompleted);

  useEffect(() => {
    onCompletedRef.current = onCompleted;
  }, [onCompleted]);

  useEffect(() => {
    if (!cameras.some((camera) => camera.id === cameraId) && cameras[0]) {
      setCameraId(cameras[0].id);
    }
  }, [cameraId, cameras]);

  useEffect(() => {
    if (!job || !["queued", "processing"].includes(job.status)) return;
    let stopped = false;
    let timeoutId = 0;

    const poll = async () => {
      try {
        const updated = await fetchRecordingAnalysis(job.id);
        if (stopped) return;
        setJob(updated);
        if (updated.status === "completed") {
          if (completedJobId.current !== updated.id) {
            completedJobId.current = updated.id;
            onCompletedRef.current();
          }
          return;
        }
        if (updated.status === "failed") return;
        timeoutId = window.setTimeout(() => void poll(), 1000);
      } catch (requestError) {
        if (stopped) return;
        const message = getErrorMessage(
          requestError,
          "Falha ao consultar o progresso.",
        );
        setError(message);
        setJob((current) =>
          current ? { ...current, status: "failed", error: message } : current,
        );
      }
    };

    timeoutId = window.setTimeout(() => void poll(), 500);
    return () => {
      stopped = true;
      window.clearTimeout(timeoutId);
    };
  }, [job?.id, job?.status]);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setJob(null);
    completedJobId.current = null;

    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
      setError("Selecione um vídeo no formato MP4, AVI ou MKV.");
      return;
    }
    if (file.size === 0) {
      setError("O arquivo selecionado está vazio.");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError("O vídeo excede o limite de 2 GB.");
      return;
    }
    if (!cameraId) {
      setError("Cadastre e selecione uma câmera para associar as visitas e zonas ROI.");
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    try {
      const created = await importRecording(file, cameraId, setUploadProgress);
      setJob(created);
    } catch (requestError) {
      setError(getErrorMessage(requestError, "Não foi possível enviar o vídeo."));
    } finally {
      setUploading(false);
    }
  };

  const busy = uploading || job?.status === "queued" || job?.status === "processing";
  const progress = uploading ? uploadProgress : job?.progress ?? 0;
  const statusText = uploading
    ? `Enviando vídeo… ${uploadProgress}%`
    : job?.status === "queued"
      ? "Aguardando na fila…"
      : job?.status === "processing"
        ? `Analisando vídeo offline… ${Math.floor(job.progress)}%`
        : job?.status === "completed"
          ? `Análise concluída · ${job.visits_created} visita(s) registrada(s)`
          : job?.status === "failed"
            ? "A análise não foi concluída."
            : null;

  return (
    <section className="mb-5 rounded-xl border border-dark-700 bg-dark-800 p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <span className="rounded-lg bg-emerald-500/10 p-2 text-emerald-300">
          <Film className="h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-base font-semibold text-[var(--color-text-primary)]">
            Importar gravação / cartão de memória
          </h2>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            Analise um arquivo local MP4, AVI ou MKV usando a câmera selecionada e
            suas zonas de leitura.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <label className="block text-xs text-[var(--color-text-muted)]">
          Associar à câmera
          <select
            value={cameraId}
            onChange={(event) => setCameraId(event.target.value)}
            disabled={busy || cameras.length === 0}
            className="mt-1 w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-emerald-500/50 disabled:opacity-60"
          >
            {cameras.length === 0 ? <option value="">Nenhuma câmera cadastrada</option> : null}
            {cameras.map((camera) => (
              <option key={camera.id} value={camera.id}>
                {camera.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-emerald-500/40 bg-dark-900 px-4 py-3 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/5 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50">
          {uploading ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          {uploading ? "Enviando…" : "Selecionar vídeo para análise"}
          <input
            type="file"
            accept=".mp4,.avi,.mkv,video/mp4,video/x-msvideo,video/x-matroska"
            disabled={busy || cameras.length === 0}
            className="sr-only"
            onChange={(event) => {
              void handleFile(event.target.files?.[0]);
              event.currentTarget.value = "";
            }}
          />
        </label>
      </div>

      {cameras.length === 0 ? (
        <p className="mt-2 text-xs text-amber-200">
          Cadastre uma câmera antes de importar: ela define a zona ROI e a associação
          dos eventos na Galeria.
        </p>
      ) : null}

      <p className="mt-3 text-xs text-emerald-200/80">
        Processamento e detecção YOLO acontecem localmente neste computador. O vídeo
        importado não é enviado a serviços externos. Os horários usam a última
        modificação do arquivo como referência e o tempo relativo dentro do vídeo.
      </p>

      {statusText ? (
        <div className="mt-4 space-y-2" aria-live="polite">
          <div className="flex items-center gap-2 text-sm text-[var(--color-text-primary)]">
            {job?.status === "completed" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            ) : busy ? (
              <LoaderCircle className="h-4 w-4 animate-spin text-emerald-400" />
            ) : null}
            <span>{statusText}</span>
          </div>
          <div
            role="progressbar"
            aria-label="Progresso da importação e análise"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.floor(progress)}
            className="h-2 overflow-hidden rounded-full bg-dark-900"
          >
            <div
              className="h-full rounded-full bg-emerald-500 transition-[width] duration-300"
              style={{ width: `${Math.min(progress, 100)}%` }}
            />
          </div>
          {job?.status === "completed" ? (
            <p className="text-xs text-emerald-300">
              A Galeria foi atualizada com as visitas encontradas.
            </p>
          ) : null}
          {job?.status === "failed" && job.error ? (
            <p role="alert" className="flex items-start gap-2 text-xs text-red-300">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {job.error}
            </p>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="mt-3 text-sm text-red-300">
          {error}
        </p>
      ) : null}
    </section>
  );
}
