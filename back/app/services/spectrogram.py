"""Espectrogramas visuais dos cantos identificados pelo BirdNET.

O módulo transforma o clipe WAV de uma detecção sonora em uma **imagem PNG**
com tempo no eixo horizontal, frequência no eixo vertical e intensidade em dB.
O arquivo é gerado uma única vez por detecção e reutilizado pelo visualizador
da aba **Detecção Sonora** e pela análise da IA externa.

Dois renderizadores são suportados:

* **Librosa + Matplotlib** (preferencial): espectrograma melódico com escala de
  magnitude em dB, paleta *magma* e eixos em português. É o mesmo tipo de
  gráfico usado por bioacústicos para comparar cantos e chamados.
* **OpenCV + NumPy** (reserva): mantém o recurso funcionando mesmo em
  instalações mínimas, sem Matplotlib. Usa a STFT já implementada em
  :mod:`app.services.audio_clips`.

O desenho é sempre feito fora da transação do banco e nunca interrompe a
captura: falhas retornam ``None`` e são registradas no log.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import uuid
import wave
from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings
from app.services.audio_clips import resolve_audio_clip

logger = logging.getLogger(__name__)

# Nomes de arquivo seguros (UUIDs das detecções). Evita path traversal.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

# Um único renderizador por vez: o Matplotlib não é thread-safe.
_RENDER_LOCK = threading.Lock()


def _render_with_librosa(
    audio_path: Path,
    destination: Path,
    *,
    title: str,
) -> bool:
    """Tenta desenhar o espectrograma com Librosa + Matplotlib.

    Devolve ``True`` quando o PNG foi gravado. Qualquer ausência de dependência
    ou falha de renderização faz o chamador cair no renderizador OpenCV.
    """
    try:
        import librosa
        import librosa.display
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover - depende do ambiente opcional
        logger.debug("Librosa/Matplotlib indisponíveis para o espectrograma")
        return False

    figure = None
    try:
        samples, sample_rate = librosa.load(
            str(audio_path), sr=None, mono=True, dtype=np.float32
        )
        if samples.size == 0 or not sample_rate:
            return False

        n_fft = 1024 if sample_rate >= 22_050 else 512
        hop_length = max(128, n_fft // 4)
        spectrum = librosa.amplitude_to_db(
            np.abs(librosa.stft(samples, n_fft=n_fft, hop_length=hop_length)),
            ref=np.max,
        )

        figure, axis = plt.subplots(figsize=(8.2, 3.3), dpi=140)
        figure.patch.set_facecolor("#0b1220")
        axis.set_facecolor("#0b1220")
        image = librosa.display.specshow(
            spectrum,
            sr=sample_rate,
            hop_length=hop_length,
            x_axis="time",
            y_axis="hz",
            cmap="magma",
            ax=axis,
        )
        axis.set_title(
            title or "Espectrograma do canto",
            color="#e2e8f0",
            fontsize=11,
            pad=10,
        )
        axis.set_xlabel("Tempo (s)", color="#94a3b8", fontsize=9)
        axis.set_ylabel("Frequência (Hz)", color="#94a3b8", fontsize=9)
        axis.tick_params(colors="#94a3b8", labelsize=8)
        for spine in axis.spines.values():
            spine.set_color("#334155")

        colorbar = figure.colorbar(image, ax=axis, format="%+2.0f dB", pad=0.012)
        colorbar.outline.set_edgecolor("#334155")
        colorbar.ax.tick_params(colors="#94a3b8", labelsize=7)

        figure.tight_layout()
        destination.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(
            destination,
            format="png",
            facecolor=figure.get_facecolor(),
            bbox_inches="tight",
            pad_inches=0.08,
        )
        return destination.is_file() and destination.stat().st_size > 0
    except Exception:
        logger.exception("Falha ao renderizar espectrograma com Librosa")
        return False
    finally:
        if figure is not None:
            try:
                import matplotlib.pyplot as plt

                plt.close(figure)
            except Exception:
                pass


def _render_with_opencv(audio_path: Path, destination: Path) -> bool:
    """Reserva sem Matplotlib: Lê o WAV e grava a STFT colorida em PNG."""
    try:
        with wave.open(str(audio_path), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            channels = max(1, wav.getnchannels())
            width = max(1, wav.getsampwidth())
        if not frames:
            return False

        if width == 2:
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
        elif width == 1:
            audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0)
        else:
            return False
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)

        # STFT curta e barata: 1024 pontos, salto de 256 (mesma escala visual
        # usada pelo analisador de áudio).
        fft_size, hop = 1024, 256
        if audio.size < fft_size * 2:
            return False
        window = np.hanning(fft_size).astype(np.float32)
        frames_view = np.lib.stride_tricks.sliding_window_view(
            audio, fft_size
        )[::hop]
        frames_view = frames_view * window
        spectrum = np.abs(np.fft.rfft(frames_view, axis=1)).T
        spectrum = np.log1p(spectrum)

        minimum = float(spectrum.min())
        maximum = float(spectrum.max())
        if maximum - minimum < 1e-6:
            return False
        normalized = (spectrum - minimum) / (maximum - minimum)
        image = (np.flipud(normalized) * 255.0).astype(np.uint8)
        image = cv2.resize(image, (820, 330), interpolation=cv2.INTER_LINEAR)
        colored = cv2.applyColorMap(image, cv2.COLORMAP_MAGMA)

        destination.parent.mkdir(parents=True, exist_ok=True)
        return bool(cv2.imwrite(str(destination), colored))
    except Exception:
        logger.exception("Falha ao renderizar espectrograma com OpenCV")
        return False


def generate_spectrogram_png(
    audio_path: Path,
    destination: Path,
    *,
    title: str = "Espectrograma do canto",
) -> Path | None:
    """Gera (ou reaproveita) o PNG do espectrograma de um clipe WAV.

    O destino é sempre um arquivo dentro de ``app-data/spectrograms``. Se o
    arquivo já existir e não estiver vazio, ele é devolvido imediatamente.
    """
    try:
        if destination.is_file() and destination.stat().st_size > 0:
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)

        with _RENDER_LOCK:
            # Outra thread pode ter gerado enquanto esperávamos o lock.
            if destination.is_file() and destination.stat().st_size > 0:
                return destination

            # Grava em um arquivo temporário e só então publica o nome final.
            # Assim o navegador nunca lê um PNG pela metade.
            temporary = destination.with_name(
                f".{destination.stem}.{uuid.uuid4().hex}.tmp.png"
            )
            try:
                ok = _render_with_librosa(
                    audio_path, temporary, title=title
                )
                if not ok:
                    ok = _render_with_opencv(audio_path, temporary)
                if ok and temporary.is_file() and temporary.stat().st_size > 0:
                    os.replace(temporary, destination)
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

        if destination.is_file() and destination.stat().st_size > 0:
            return destination
        return None
    except Exception:
        logger.exception("Falha inesperada ao gerar o espectrograma")
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def ensure_detection_spectrogram(
    detection_id: str,
    audio_relative: str | None,
    *,
    title: str | None = None,
    force: bool = False,
) -> Path | None:
    """Garante o espectrograma de uma detecção sonora no disco.

    ``audio_relative`` é o caminho relativo gravado no banco (ex.:
    ``audio/123.wav``). O arquivo de saída é determinístico:
    ``app-data/spectrograms/<detection_id>.png``.
    """
    if not detection_id or not _SAFE_ID.match(detection_id):
        return None
    audio_path = resolve_audio_clip(audio_relative)
    if audio_path is None:
        return None

    destination = get_settings().spectrograms_dir / f"{detection_id}.png"
    if force and destination.exists():
        try:
            destination.unlink()
        except OSError:
            logger.debug("Não foi possível remover o espectrograma antigo", exc_info=True)

    return generate_spectrogram_png(
        audio_path,
        destination,
        title=title or "Espectrograma do canto · Bem-Te-Vi",
    )


def detection_spectrogram_path(detection_id: str) -> Path | None:
    """Caminho do PNG já gerado para a detecção (sem gerar nada)."""
    if not detection_id or not _SAFE_ID.match(detection_id):
        return None
    path = get_settings().spectrograms_dir / f"{detection_id}.png"
    return path if path.is_file() and path.stat().st_size > 0 else None


def remove_detection_spectrogram(detection_id: str) -> None:
    """Remove o PNG ao excluir a detecção (higiene de disco)."""
    path = detection_spectrogram_path(detection_id)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug(
            "Não foi possível remover o espectrograma da detecção %s",
            detection_id,
            exc_info=True,
        )
