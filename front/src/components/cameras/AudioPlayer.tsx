import { useEffect, useRef, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";
import { cameraAudioUrl } from "@/services/api";
import { cn } from "@/utils/cn";

type Props = {
  cameraId: string;
};

/**
 * Player de áudio ao vivo do jardim (Bioacústica).
 * Permite ativar/desativar o som (mute/unmute) e ajustar o volume
 * individualmente de cada câmera em tempo real.
 */
export function AudioPlayer({ cameraId }: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [muted, setMuted] = useState(true);
  const [volume, setVolume] = useState(0.5);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = muted;
    audio.volume = volume;
  }, [muted, volume]);

  const toggleMute = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (muted) {
      audio.muted = false;
      audio.volume = volume;
      setMuted(false);
      const p = audio.play();
      if (p) {
        p.catch((err) => {
          console.warn("Audio play failed:", err);
          setError("Clique para ativar o áudio");
        });
      }
    } else {
      audio.muted = true;
      setMuted(true);
    }
  };

  return (
    <div className="mt-3 flex items-center gap-2 rounded-lg border border-dark-700 bg-dark-900/60 px-3 py-2">
      <audio
        ref={audioRef}
        src={cameraAudioUrl(cameraId)}
        preload="auto"
        crossOrigin="anonymous"
        className="hidden"
        onError={(e) => {
          console.warn("Audio error:", e);
          setError("Erro ao carregar áudio");
        }}
        onCanPlay={() => setError(null)}
      />
      <button
        type="button"
        onClick={toggleMute}
        aria-label={muted ? "Ativar som" : "Mutar som"}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-emerald-400 transition hover:bg-emerald-500/10"
      >
        {muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
      </button>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={volume}
        onChange={(e) => setVolume(Number(e.target.value))}
        disabled={muted}
        aria-label="Volume do áudio"
        className={cn(
          "h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-dark-700 accent-emerald-500",
          muted && "opacity-40",
        )}
      />
      <span className="w-16 text-right text-[10px] tabular-nums text-[var(--color-text-muted)]">
        {error ? error : muted ? "Mudo" : `${Math.round(volume * 100)}%`}
      </span>
    </div>
  );
}
