"""Clipes de áudio e espectrogramas das detecções sonoras (BirdNET).

O analisador de áudio processa o stream em blocos de poucos segundos. Para que
o observador possa **ouvir** o canto que o BirdNET identificou — e para que a IA
externa consiga **analisar** a detecção — este módulo:

* grava o bloco de amostras PCM como um arquivo ``.wav`` (formato que qualquer
  navegador reproduz nativamente, sem precisar do ffmpeg) na pasta
  ``captures/audio/``; e
* desenha um **espectrograma** (JPEG) do mesmo bloco, para enviá-lo à IA externa
  quando o observador pedir uma análise profunda daquela detecção.

Nada aqui depende de bibliotecas opcionais: o WAV usa o módulo ``wave`` da
biblioteca padrão e o espectrograma usa apenas ``numpy`` e ``cv2``.
"""

from __future__ import annotations

import logging
import time
import uuid
import wave
from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Parâmetros do áudio (idênticos aos do worker de bioacústica).
SAMPLE_RATE = 48_000
SAMPLE_WIDTH = 2  # 16 bits
CHANNELS = 1

# Parâmetros da STFT do espectrograma.
_FFT_SIZE = 1024
_HOP = 256
_SPEC_WIDTH = 640
_SPEC_HEIGHT = 320


def save_audio_clip(samples: bytes) -> str | None:
    """Grava um bloco PCM (16 bits mono 48 kHz) como WAV e devolve o caminho relativo.

    O caminho é relativo à pasta de capturas (ex.: ``audio/<id>.wav``), o mesmo
    padrão usado pelos clipes. Devolve ``None`` se não houver amostras.
    """
    if not samples:
        return None
    settings = get_settings()
    try:
        settings.ensure_directories()
    except OSError:
        logger.exception("Não foi possível preparar a pasta de áudio")
        return None

    name = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:12]}.wav"
    destination = settings.audio_dir / name
    try:
        with wave.open(str(destination), "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(samples)
    except (OSError, wave.Error):
        logger.exception("Falha ao gravar o clipe de áudio")
        return None
    return f"audio/{name}"


def resolve_audio_clip(relative: str | None) -> Path | None:
    """Resolve o caminho absoluto de um clipe de áudio validando a pasta."""
    if not relative:
        return None
    settings = get_settings()
    candidate = (settings.captures_dir / relative.replace("\\", "/")).resolve()
    try:
        candidate.relative_to(settings.audio_dir.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _spectrogram_image(samples: np.ndarray) -> np.ndarray | None:
    """Desenha o espectrograma (escala de cor *magma*) a partir das amostras."""
    if samples.size < _FFT_SIZE * 2:
        return None

    window = np.hanning(_FFT_SIZE).astype(np.float32)
    n_frames = 1 + (samples.size - _FFT_SIZE) // _HOP
    if n_frames < 2:
        return None

    # Enquadramento eficiente com truques de *stride* (sem loop em Python).
    frames = np.lib.stride_tricks.sliding_window_view(samples, _FFT_SIZE)[::_HOP]
    frames = frames[:n_frames] * window
    espectro = np.abs(np.fft.rfft(frames, axis=1)).T  # freq x tempo

    espectro = np.log1p(espectro)
    minimo = float(espectro.min())
    maximo = float(espectro.max())
    if maximo - minimo < 1e-6:
        return None
    normalizado = (espectro - minimo) / (maximo - minimo)

    # Frequência baixa embaixo: invertemos o eixo vertical.
    img = (np.flipud(normalizado) * 255.0).astype(np.uint8)
    img = cv2.resize(img, (_SPEC_WIDTH, _SPEC_HEIGHT), interpolation=cv2.INTER_LINEAR)
    return cv2.applyColorMap(img, cv2.COLORMAP_MAGMA)


def spectrogram_jpeg_bytes(samples: bytes) -> bytes | None:
    """Espectrograma em JPEG a partir de amostras PCM cruas (para a IA externa)."""
    if not samples:
        return None
    audio = np.frombuffer(samples, dtype=np.int16).astype(np.float32)
    if audio.size == 0:
        return None
    imagem = _spectrogram_image(audio)
    if imagem is None:
        return None
    ok, buffer = cv2.imencode(".jpg", imagem, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    return buffer.tobytes() if ok else None


def spectrogram_jpeg_from_wav(path: Path) -> bytes | None:
    """Espectrograma em JPEG a partir de um arquivo WAV existente."""
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
    except (OSError, wave.Error):
        logger.exception("Falha ao ler o clipe de áudio %s", path)
        return None
    return spectrogram_jpeg_bytes(frames)
