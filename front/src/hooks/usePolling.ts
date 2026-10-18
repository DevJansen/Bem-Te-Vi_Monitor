import { useCallback, useEffect, useRef, useState } from "react";

type Fetcher<T> = () => Promise<T>;

export function usePolling<T>(
  fetcher: Fetcher<T>,
  intervalMs: number,
  enabled = true,
): {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let active = true;
    const tick = async () => {
      try {
        const result = await fetcherRef.current();
        if (!active) return;
        setData(result);
        setError(null);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Falha ao carregar");
      } finally {
        if (active) setLoading(false);
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), intervalMs);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [intervalMs, enabled]);

  return {
    data,
    error,
    loading,
    refresh: async () => {
      setLoading(true);
      await run();
    },
    setData,
  };
}
