import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Pause, Play, Volume2, VolumeX } from "lucide-react";
import { cn } from "@/utils/cn";

type Props = {
  src: string;
  className?: string;
  /** Rótulo acessível (ex.: "Canto de Sabiá-laranjeira"). */
  label?: string;
};

function formatSeconds(value: number): string {
  if (!Number.isFinite(value) || value < 0) return "0:00";
  const total = Math.floor(value);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Player compacto do clipe de áudio de uma detecção sonora.
 *
 * Construído sobre o elemento `<audio>` nativo, mas com controles próprios no
 * estilo *dark* do Bem-Te-Vi: botão play/pause, barra de progresso arrastável,
 * volume com mute e tempos. O som começa sempre em volume moderado e sem
 * autoplay (política dos navegadores) — o observador escolhe quando ouvir.
 */
export function AudioClipPlayer({ src, className, label }: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.9);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState(false);

  // Reinicia o estado quando o clipe muda (paginação/troca de card).
  useEffect(() => {
    setPlaying(false);
    setCurrent(0);
    setDuration(0);
    setError(false);
  }, [src]);

  const toggle = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio || error) return;
    if (audio.paused) {
      try {
        setLoading(true);
        // Garante que o volume/mute valham já no play (evita corrida com o state).
        audio.volume = volume;
        audio.muted = muted;
        await audio.play();
        setPlaying(true);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    } else {
      audio.pause();
      setPlaying(false);
    }
  }, [error, muted, volume]);

  const seek = useCallback((value: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = value;
    setCurrent(value);
  }, []);

  const onVolume = useCallback(
    (value: number) => {
      const audio = audioRef.current;
      setVolume(value);
      if (audio) audio.volume = value;
      if (value > 0 && muted) {
        setMuted(false);
        if (audio) audio.muted = false;
      }
    },
    [muted],
  );

  const toggleMute = useCallback(() => {
    const audio = audioRef.current;
    setMuted((prev) => {
      const next = !prev;
      if (audio) audio.muted = next;
      return next;
    });
  }, []);

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border border-dark-700 bg-dark-900/70 px-2.5 py-2",
        className,
      )}
      aria-label={label ? `Player: ${label}` : "Player de áudio"}
    >
      <audio
        ref={audioRef}
        src={src}
        preload="none"
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
        onEnded={() => {
          setPlaying(false);
          setCurrent(0);
        }}
        onError={() => setError(true)}
      />

      <button
        type="button"
        onClick={() => void toggle()}
        disabled={error}
        aria-label={playing ? "Pausar canto" : "Reproduzir canto"}
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition",
          error
            ? "cursor-not-allowed bg-dark-700 text-[var(--color-text-muted)]"
            : "bg-violet-500/20 text-violet-200 hover:bg-violet-500/30",
        )}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : playing ? (
          <Pause className="h-4 w-4" />
        ) : (
          <Play className="h-4 w-4 translate-x-[1px]" />
        )}
      </button>

      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <input
          type="range"
          min={0}
          max={duration || 0}
          step={0.05}
          value={Math.min(current, duration || 0)}
          onChange={(e) => seek(Number(e.target.value))}
          disabled={error || duration === 0}
          aria-label="Progresso do áudio"
          className="h-1 w-full cursor-pointer appearance-none rounded-full bg-dark-700 accent-violet-400 disabled:opacity-50"
        />
        <div className="flex items-center justify-between text-[10px] tabular-nums text-[var(--color-text-muted)]">
          <span>{error ? "Áudio indisponível" : formatSeconds(current)}</span>
          <span>{formatSeconds(duration)}</span>
        </div>
      </div>

      <button
        type="button"
        onClick={toggleMute}
        aria-label={muted ? "Ativar som" : "Silenciar"}
        className="shrink-0 text-[var(--color-text-muted)] hover:text-violet-200"
      >
        {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
      </button>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={muted ? 0 : volume}
        onChange={(e) => onVolume(Number(e.target.value))}
        aria-label="Volume"
        className="hidden h-1 w-16 cursor-pointer appearance-none rounded-full bg-dark-700 accent-violet-400 sm:block"
      />
    </div>
  );
}
