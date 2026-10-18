import { useEffect, useRef, useState } from "react";
import {
  Activity,
  Eye,
  EyeOff,
  Mic,
  Volume2,
  VolumeX,
  Loader2,
} from "lucide-react";
import type { Camera } from "@/types";
import { cameraAudioUrl, toggleCameraAi, toggleCameraBioacoustics } from "@/services/api";
import { cn } from "@/utils/cn";

type Props = {
  camera: Camera;
  onCameraUpdated?: (updated: Camera) => void;
  /** Modo compacto para cards menores do grid */
  compact?: boolean;
  className?: string;
};

/**
 * Barra de ferramentas flutuante de controles operacionais em tempo real:
 * 1. Toggle Alaris Core (Ligar/Pausar IA de visão computacional e gravação)
 * 2. Player de Áudio Ao Vivo (Mute/Unmute e volume do som ambiente)
 * 3. Toggle Bioacústica BirdNET (Monitorar e identificar cantos de aves pelo áudio)
 */
export function CameraControlToolbar({
  camera,
  onCameraUpdated,
  compact = false,
  className,
}: Props) {
  // Estado local otimista para IA e Bioacústica
  const [aiEnabled, setAiEnabled] = useState<boolean>(camera.ai_enabled !== false);
  const [audioMonitoring, setAudioMonitoring] = useState<boolean>(
    Boolean(camera.audio_enabled),
  );
  const [togglingAi, setTogglingAi] = useState(false);
  const [togglingBio, setTogglingBio] = useState(false);

  // Player de Áudio Ao Vivo (Som ambiente do jardim / live)
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [volume, setVolume] = useState(0.6);
  const [audioConnecting, setAudioConnecting] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [showVolumeSlider, setShowVolumeSlider] = useState(false);

  // Sincroniza com as propriedades da câmera recebidas do polling
  useEffect(() => {
    setAiEnabled(camera.ai_enabled !== false);
  }, [camera.ai_enabled]);

  useEffect(() => {
    setAudioMonitoring(Boolean(camera.audio_enabled));
  }, [camera.audio_enabled]);

  // Atualiza volume e mute no elemento de áudio
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = volume;
    audio.muted = !isPlayingAudio;
  }, [volume, isPlayingAudio]);

  // 1. Toggle Alaris Core (IA Visual)
  const handleToggleAi = async () => {
    if (togglingAi) return;
    const nextState = !aiEnabled;
    setAiEnabled(nextState);
    setTogglingAi(true);
    try {
      const updated = await toggleCameraAi(camera.id, nextState);
      if (onCameraUpdated) onCameraUpdated(updated);
    } catch (err) {
      console.error("Falha ao alternar Alaris Core:", err);
      setAiEnabled(!nextState); // Rollback
    } finally {
      setTogglingAi(false);
    }
  };

  // 2. Player de Áudio Ao Vivo (Mute/Unmute)
  const handleToggleAudioPlay = () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlayingAudio) {
      audio.pause();
      setIsPlayingAudio(false);
      setAudioConnecting(false);
    } else {
      setAudioError(null);
      setAudioConnecting(true);
      audio.muted = false;
      audio.volume = volume;
      // Adiciona timestamp para forçar nova conexão de áudio limpa
      audio.src = `${cameraAudioUrl(camera.id)}?t=${Date.now()}`;
      const playPromise = audio.play();
      if (playPromise) {
        playPromise
          .then(() => {
            setIsPlayingAudio(true);
            setAudioConnecting(false);
          })
          .catch((err) => {
            console.warn("Falha ao iniciar áudio ao vivo:", err);
            setAudioConnecting(false);
            setAudioError("Clique para reproduzir");
          });
      }
    }
  };

  // 3. Toggle Bioacústica BirdNET
  const handleToggleBirdNet = async () => {
    if (togglingBio) return;
    const nextState = !audioMonitoring;
    setAudioMonitoring(nextState);
    setTogglingBio(true);
    try {
      const updated = await toggleCameraBioacoustics(camera.id, nextState);
      if (onCameraUpdated) onCameraUpdated(updated);
    } catch (err) {
      console.error("Falha ao alternar Bioacústica BirdNET:", err);
      setAudioMonitoring(!nextState); // Rollback
    } finally {
      setTogglingBio(false);
    }
  };

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5 rounded-xl border border-white/10 bg-dark-950/85 p-1.5 shadow-2xl backdrop-blur-md transition-all duration-300",
        className,
      )}
    >
      {/* Áudio Element invisível */}
      <audio
        ref={audioRef}
        preload="none"
        crossOrigin="anonymous"
        onPlaying={() => {
          setIsPlayingAudio(true);
          setAudioConnecting(false);
          setAudioError(null);
        }}
        onError={() => {
          setAudioConnecting(false);
          setAudioError("Sem áudio");
        }}
      />

      {/* 1. Toggle Switch Alaris Core (IA Visual) */}
      <button
        type="button"
        onClick={handleToggleAi}
        disabled={togglingAi}
        title={
          aiEnabled
            ? "Alaris Core Ativo — Clique para pausar o processamento de IA e gravações (economiza GPU/CPU)"
            : "Alaris Core Pausado — Clique para ativar o monitoramento por IA (YOLOv8)"
        }
        className={cn(
          "group relative inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-200",
          aiEnabled
            ? "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.2)] hover:bg-emerald-500/25"
            : "border border-dark-700 bg-dark-900/80 text-[var(--color-text-muted)] hover:border-dark-600 hover:text-[var(--color-text-primary)]",
        )}
      >
        {togglingAi ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-400" />
        ) : aiEnabled ? (
          <Eye className="h-3.5 w-3.5 text-emerald-400 transition group-hover:scale-110" />
        ) : (
          <EyeOff className="h-3.5 w-3.5 text-zinc-400" />
        )}
        <span className="hidden sm:inline">
          {aiEnabled ? "Alaris IA" : "IA Pausada"}
        </span>
        {aiEnabled && (
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse-soft" />
        )}
      </button>

      {/* 2. Player e Seletor de Áudio Ao Vivo (Mute / Unmute) */}
      <div
        className="relative flex items-center"
        onMouseEnter={() => isPlayingAudio && setShowVolumeSlider(true)}
        onMouseLeave={() => setShowVolumeSlider(false)}
      >
        <button
          type="button"
          onClick={handleToggleAudioPlay}
          title={
            isPlayingAudio
              ? "Mutar som ambiente do jardim"
              : "Ouvir som ambiente ao vivo do jardim ou live"
          }
          className={cn(
            "group inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-200",
            isPlayingAudio
              ? "border border-cyan-500/40 bg-cyan-500/15 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.2)] hover:bg-cyan-500/25"
              : "border border-dark-700 bg-dark-900/80 text-[var(--color-text-muted)] hover:border-dark-600 hover:text-[var(--color-text-primary)]",
          )}
        >
          {audioConnecting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400" />
          ) : isPlayingAudio ? (
            <Volume2 className="h-3.5 w-3.5 text-cyan-400 transition group-hover:scale-110" />
          ) : (
            <VolumeX className="h-3.5 w-3.5 text-zinc-400" />
          )}

          <span className="hidden sm:inline">
            {audioConnecting
              ? "Conectando..."
              : isPlayingAudio
                ? "Som Ao Vivo"
                : "Mudo"}
          </span>

          {/* Mini equalizador animado quando ouvindo */}
          {isPlayingAudio && !audioConnecting && (
            <span className="flex items-end gap-0.5 h-2.5">
              <span className="w-0.5 h-1.5 bg-cyan-400 rounded-full animate-[pulse_0.6s_ease-in-out_infinite]" />
              <span className="w-0.5 h-2.5 bg-cyan-400 rounded-full animate-[pulse_0.4s_ease-in-out_infinite]" />
              <span className="w-0.5 h-1 bg-cyan-400 rounded-full animate-[pulse_0.8s_ease-in-out_infinite]" />
            </span>
          )}
        </button>

        {/* Slider flutuante de volume suave (aparece no hover quando ativo) */}
        {isPlayingAudio && (showVolumeSlider || !compact) && (
          <div className="absolute left-full ml-1.5 z-20 flex items-center gap-1.5 rounded-lg border border-dark-700 bg-dark-900/95 px-2.5 py-1.5 shadow-xl backdrop-blur-md">
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              aria-label="Volume do som ambiente"
              className="h-1.5 w-16 cursor-pointer appearance-none rounded-full bg-dark-700 accent-cyan-400"
            />
            <span className="text-[10px] tabular-nums font-mono text-[var(--color-text-muted)]">
              {Math.round(volume * 100)}%
            </span>
          </div>
        )}
      </div>

      {/* 3. Toggle Switch de Bioacústica (BirdNET) */}
      <button
        type="button"
        onClick={handleToggleBirdNet}
        disabled={togglingBio}
        title={
          audioMonitoring
            ? "Bioacústica BirdNET Ativa — Identificando cantos de aves no stream. Clique para pausar."
            : "Monitorar Áudio (BirdNET) — Clique para ativar a identificação sonora contínua nesta câmera"
        }
        className={cn(
          "group relative inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-200",
          audioMonitoring
            ? "border border-indigo-500/40 bg-indigo-500/15 text-indigo-300 shadow-[0_0_12px_rgba(99,102,241,0.25)] hover:bg-indigo-500/25"
            : "border border-dark-700 bg-dark-900/80 text-[var(--color-text-muted)] hover:border-dark-600 hover:text-[var(--color-text-primary)]",
        )}
      >
        {togglingBio ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
        ) : audioMonitoring ? (
          <Activity className="h-3.5 w-3.5 text-indigo-400 transition group-hover:scale-110" />
        ) : (
          <Mic className="h-3.5 w-3.5 text-zinc-400" />
        )}

        <span className="hidden sm:inline">
          {audioMonitoring ? "BirdNET Ativo" : "BirdNET"}
        </span>

        {audioMonitoring && (
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-ping" />
        )}
      </button>

      {audioError && (
        <span className="text-[10px] text-amber-400/80 px-1 truncate max-w-[90px]">
          {audioError}
        </span>
      )}
    </div>
  );
}
