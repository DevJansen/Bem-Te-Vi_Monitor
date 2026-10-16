import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Database,
  Film,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import type { Camera } from "@/types";
import { useOfflineAnalysis } from "@/context/OfflineAnalysisContext";
import { OfflineDropzone } from "@/components/offline/OfflineDropzone";
import { OfflineJobCard, ProgressBar } from "@/components/offline/OfflineJobCard";

type Props = {
  cameras: Camera[];
  onOpenGallery: () => void;
};

const MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".mp4", ".avi", ".mov", ".mkv"];

/**
 * Tela "Análise de Cartão de Memória".
 *
 * Reformulada com drag & drop moderno, lista persistente de jobs e cartões de
 * resultado detalhados. Todo o estado de progresso vem do backend (via
 * contexto global), então sobrevive à troca de aba e a recarregamentos.
 */
export function OfflineAnalysisScreen({ cameras, onOpenGallery }: Props) {
  const {
    jobs,
    uploads,
    loading,
    error,
    startUpload,
    removeJob,
    clearFinished,
    dismissUpload,
  } = useOfflineAnalysis();

  const [cameraId, setCameraId] = useState(cameras[0]?.id ?? "");
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!cameras.some((camera) => camera.id === cameraId) && cameras[0]) {
      setCameraId(cameras[0].id);
    }
  }, [cameraId, cameras]);

  const activeJobs = useMemo(
    () => jobs.filter((job) => job.status === "queued" || job.status === "processing"),
    [jobs],
  );
  const finishedJobs = useMemo(
    () => jobs.filter((job) => job.status === "completed" || job.status === "error"),
    [jobs],
  );
  const uploading = uploads.filter((item) => item.status === "uploading");
  const failedUploads = uploads.filter((item) => item.status === "error");
  const busy = uploading.length > 0 || activeJobs.length > 0;

  const handleFiles = (files: File[]) => {
    setNotice(null);
    if (cameras.length === 0) {
      setNotice("Cadastre uma câmera antes de importar: ela define as zonas de leitura.");
      return;
    }
    if (!cameraId) {
      setNotice("Selecione a câmera que corresponde a esta gravação.");
      return;
    }

    const accepted: File[] = [];
    const rejected: string[] = [];
    for (const file of files) {
      const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
      if (!ACCEPTED_EXTENSIONS.includes(extension)) {
        rejected.push(`${file.name} (formato não suportado)`);
        continue;
      }
      if (file.size === 0) {
        rejected.push(`${file.name} (arquivo vazio)`);
        continue;
      }
      if (file.size > MAX_FILE_BYTES) {
        rejected.push(`${file.name} (acima de 2 GB)`);
        continue;
      }
      accepted.push(file);
    }

    accepted.forEach((file) => startUpload(file, cameraId));
    if (rejected.length > 0) {
      setNotice(`Ignorado(s): ${rejected.join(" · ")}`);
    }
  };

  return (
    <section className="mb-5 space-y-4">
      {/* Cabeçalho */}
      <div className="animate-fade-in-up rounded-2xl border border-dark-700 bg-gradient-to-br from-dark-800 to-dark-800/40 p-5 sm:p-6">
        <div className="flex items-start gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-emerald-500/15 text-emerald-300">
            <Sparkles className="h-6 w-6" strokeWidth={1.75} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-lg font-semibold text-[var(--color-text-primary)]">
              Análise de Cartão de Memória
            </h2>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              Importe vídeos gravados na câmera e deixe a IA sensível encontrar e
              contar as aves automaticamente. As capturas vão direto para a Galeria.
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
          <label className="block text-xs font-medium text-[var(--color-text-muted)]">
            Associar à câmera
            <select
              value={cameraId}
              onChange={(event) => setCameraId(event.target.value)}
              disabled={cameras.length === 0 || busy}
              className="mt-1.5 w-full rounded-lg border border-dark-700 bg-dark-900 px-3 py-2.5 text-sm text-[var(--color-text-primary)] outline-none transition focus:border-emerald-500/50 disabled:opacity-60"
            >
              {cameras.length === 0 ? (
                <option value="">Nenhuma câmera cadastrada</option>
              ) : null}
              {cameras.map((camera) => (
                <option key={camera.id} value={camera.id}>
                  {camera.name}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-end">
            <p className="flex items-center gap-2 text-xs text-emerald-200/80">
              <ShieldCheck className="h-4 w-4 shrink-0" />
              Processamento e YOLO acontecem localmente neste computador. O vídeo não
              é enviado a serviços externos.
            </p>
          </div>
        </div>
      </div>

      {/* Área de arraste */}
      <OfflineDropzone onFiles={handleFiles} disabled={cameras.length === 0 || busy} />

      {cameras.length === 0 ? (
        <p className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Cadastre uma câmera antes de importar: ela define a zona ROI e a associação
          das capturas na Galeria.
        </p>
      ) : null}

      {notice ? (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {notice}
        </p>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </p>
      ) : null}

      {/* Lista de trabalhos */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-2 font-display text-sm font-semibold text-[var(--color-text-primary)]">
            <Database className="h-4 w-4 text-emerald-400" />
            Importações e resultados
            {activeJobs.length + uploading.length > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
                <LoaderCircle className="h-3 w-3 animate-spin" />
                {activeJobs.length + uploading.length} em andamento
              </span>
            ) : null}
          </h3>

          {finishedJobs.length > 0 ? (
            <button
              type="button"
              onClick={() => void clearFinished()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-dark-700 px-2.5 py-1.5 text-xs text-[var(--color-text-muted)] transition hover:border-red-500/30 hover:text-red-300"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Limpar concluídos
            </button>
          ) : null}
        </div>

        {/* Uploads em andamento / com falha */}
        {uploading.map((item) => (
          <div
            key={item.id}
            className="animate-fade-in-up rounded-2xl border border-dark-700 bg-dark-800/80 px-4 py-3"
          >
            <div className="flex items-center gap-2 text-sm">
              <UploadCloud className="h-4 w-4 shrink-0 text-emerald-400" />
              <span className="min-w-0 flex-1 truncate text-[var(--color-text-primary)]">
                Enviando {item.filename}
              </span>
              <span className="tabular-nums text-emerald-300">{item.progress}%</span>
            </div>
            <ProgressBar value={item.progress} className="mt-2 h-1.5" />
          </div>
        ))}

        {failedUploads.map((item) => (
          <div
            key={item.id}
            className="flex items-start gap-2 rounded-2xl border border-red-500/30 bg-red-500/5 px-4 py-3"
          >
            <X className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-red-200">
                Falha ao enviar {item.filename}
              </p>
              <p className="text-xs text-red-300/80">{item.error}</p>
            </div>
            <button
              type="button"
              onClick={() => dismissUpload(item.id)}
              aria-label="Dispensar"
              className="rounded-md p-1 text-[var(--color-text-muted)] transition hover:bg-dark-700"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}

        {jobs.map((job) => (
          <OfflineJobCard
            key={job.id}
            job={job}
            onOpenGallery={onOpenGallery}
            onRemove={() => void removeJob(job.id)}
          />
        ))}

        {!loading && jobs.length === 0 && uploads.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-dark-700 bg-dark-800/40 px-6 py-10 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-dark-700 text-emerald-400">
              <Film className="h-6 w-6" strokeWidth={1.75} />
            </span>
            <div>
              <p className="font-medium text-[var(--color-text-primary)]">
                Nenhuma análise por aqui ainda
              </p>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                Solte um vídeo acima para começar. O progresso aparece aqui e continua
                mesmo se você trocar de aba.
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Detecção local e sensível
            </span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
