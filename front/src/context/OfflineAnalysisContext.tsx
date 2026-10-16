import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { OfflineJob } from "@/types";
import {
  clearFinishedOfflineJobs,
  deleteOfflineJob,
  fetchOfflineJobs,
  getErrorMessage,
  uploadOfflineVideo,
} from "@/services/api";

/** Upload em andamento/erro controlado pelo navegador (antes de virar job). */
export type PendingUpload = {
  id: string;
  filename: string;
  progress: number;
  status: "uploading" | "error";
  error: string | null;
};

type OfflineAnalysisContextValue = {
  /** Jobs conhecidos pelo backend (mais recentes primeiro). */
  jobs: OfflineJob[];
  /** Uploads ainda em transferência ou com erro no navegador. */
  uploads: PendingUpload[];
  /** Jobs concluídos nesta sessão (para o cartão flutuante de sucesso). */
  successes: OfflineJob[];
  loading: boolean;
  error: string | null;
  /** Quantidade de trabalhos ativos (uploads + jobs na fila/processando). */
  activeCount: number;
  startUpload: (file: File, cameraId: string) => void;
  refresh: () => Promise<void>;
  removeJob: (id: string) => Promise<void>;
  clearFinished: () => Promise<void>;
  dismissUpload: (id: string) => void;
  dismissSuccess: (id: string) => void;
};

const OfflineAnalysisContext = createContext<OfflineAnalysisContextValue | null>(
  null,
);

const ACTIVE_POLL_MS = 1200;
const IDLE_POLL_MS = 6000;
const SUCCESS_VISIBLE_MS = 12000;

type Props = {
  children: ReactNode;
  /** Disparado uma única vez quando um job termina (para atualizar a Galeria). */
  onJobCompleted?: () => void;
};

export function OfflineAnalysisProvider({ children, onJobCompleted }: Props) {
  const [jobs, setJobs] = useState<OfflineJob[]>([]);
  const [uploads, setUploads] = useState<PendingUpload[]>([]);
  const [successes, setSuccesses] = useState<OfflineJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Refs usados pelo laço de polling adaptativo e pela detecção de conclusão.
  const jobsRef = useRef<OfflineJob[]>([]);
  const uploadsRef = useRef<PendingUpload[]>([]);
  const activeIdsRef = useRef<Set<string>>(new Set());
  const notifiedRef = useRef<Set<string>>(new Set());
  const onCompletedRef = useRef(onJobCompleted);
  onCompletedRef.current = onJobCompleted;
  jobsRef.current = jobs;
  uploadsRef.current = uploads;

  const refresh = useCallback(async () => {
    try {
      const data = await fetchOfflineJobs();
      setJobs(data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao consultar as análises."));
    } finally {
      setLoading(false);
    }
  }, []);

  // Detecta conclusões: um job que estava ativo e agora está "completed".
  useEffect(() => {
    const active = new Set<string>();
    const finished: OfflineJob[] = [];
    for (const job of jobs) {
      if (job.status === "queued" || job.status === "processing") {
        active.add(job.id);
      } else if (
        job.status === "completed" &&
        activeIdsRef.current.has(job.id) &&
        !notifiedRef.current.has(job.id)
      ) {
        notifiedRef.current.add(job.id);
        finished.push(job);
      }
    }
    activeIdsRef.current = active;
    if (finished.length === 0) return;

    setSuccesses((current) => [...finished, ...current]);
    onCompletedRef.current?.();
    const timers = finished.map((job) =>
      window.setTimeout(() => {
        setSuccesses((current) => current.filter((item) => item.id !== job.id));
      }, SUCCESS_VISIBLE_MS),
    );
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [jobs]);

  // Polling adaptativo: rápido enquanto há trabalho, lento quando ocioso.
  useEffect(() => {
    let stopped = false;
    let timer = 0;
    const tick = async () => {
      await refresh();
      if (stopped) return;
      const busy =
        jobsRef.current.some(
          (job) => job.status === "queued" || job.status === "processing",
        ) ||
        uploadsRef.current.some((item) => item.status === "uploading");
      timer = window.setTimeout(tick, busy ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    };
    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [refresh]);

  const startUpload = useCallback((file: File, cameraId: string) => {
    const id = `upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setUploads((current) => [
      ...current,
      { id, filename: file.name, progress: 0, status: "uploading", error: null },
    ]);
    void (async () => {
      try {
        const job = await uploadOfflineVideo(file, cameraId, (percent) => {
          setUploads((current) =>
            current.map((item) =>
              item.id === id ? { ...item, progress: percent } : item,
            ),
          );
        });
        setUploads((current) => current.filter((item) => item.id !== id));
        setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
        // Marca como ativo para que a conclusão seja celebrada corretamente.
        activeIdsRef.current.add(job.id);
      } catch (err) {
        const message = getErrorMessage(err, "Não foi possível enviar o vídeo.");
        setUploads((current) =>
          current.map((item) =>
            item.id === id ? { ...item, status: "error", error: message } : item,
          ),
        );
      }
    })();
  }, []);

  const removeJob = useCallback(async (id: string) => {
    try {
      await deleteOfflineJob(id);
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao remover a análise."));
      return;
    }
    setJobs((current) => current.filter((job) => job.id !== id));
  }, []);

  const clearFinished = useCallback(async () => {
    try {
      await clearFinishedOfflineJobs();
    } catch (err) {
      setError(getErrorMessage(err, "Falha ao limpar o histórico."));
      return;
    }
    await refresh();
  }, [refresh]);

  const dismissUpload = useCallback((id: string) => {
    setUploads((current) => current.filter((item) => item.id !== id));
  }, []);

  const dismissSuccess = useCallback((id: string) => {
    setSuccesses((current) => current.filter((item) => item.id !== id));
  }, []);

  const activeCount =
    jobs.filter(
      (job) => job.status === "queued" || job.status === "processing",
    ).length + uploads.filter((item) => item.status === "uploading").length;

  return (
    <OfflineAnalysisContext.Provider
      value={{
        jobs,
        uploads,
        successes,
        loading,
        error,
        activeCount,
        startUpload,
        refresh,
        removeJob,
        clearFinished,
        dismissUpload,
        dismissSuccess,
      }}
    >
      {children}
    </OfflineAnalysisContext.Provider>
  );
}

export function useOfflineAnalysis(): OfflineAnalysisContextValue {
  const context = useContext(OfflineAnalysisContext);
  if (context === null) {
    throw new Error(
      "useOfflineAnalysis deve ser usado dentro de <OfflineAnalysisProvider>.",
    );
  }
  return context;
}
