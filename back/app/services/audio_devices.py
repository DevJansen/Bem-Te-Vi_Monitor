"""Descoberta e resolução de dispositivos de áudio para o BirdNET.

A análise sonora pode capturar o áudio de uma câmera RTSP/ONVIF (pela própria
URL do stream) ou de um dispositivo de entrada do sistema (microfone USB, placa
de som, webcam com microfone). O ``ffmpeg`` é usado nos dois casos; este módulo
concentra apenas a parte específica de cada sistema operacional.

Backends usados por plataforma:

- **Windows**: DirectShow — ``-f dshow -i audio=<nome>``
- **Linux**: ALSA — ``-f alsa -i <dispositivo>``
- **macOS**: AVFoundation — ``-f avfoundation -i :<índice>``

A enumeração é feita invocando o ``ffmpeg`` e interpretando a saída, com cache
curto para evitar chamadas repetidas ao subprocesso.
"""

from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Tempo de vida do cache de dispositivos (segundos).
_CACHE_TTL_SECONDS = 30.0
_cache_lock = threading.Lock()
_cache: tuple[float, list["AudioDevice"]] | None = None


@dataclass(frozen=True)
class AudioDevice:
    """Dispositivo de entrada de áudio disponível no sistema.

    ``name`` é o nome amigável exibido ao usuário. ``alternative`` é o
    identificador técnico do DirectShow (``@device_cm_{...}``), usado quando o
    nome amigável contém caracteres que quebrariam a sintaxe do ffmpeg.
    """

    name: str
    alternative: str | None = None

    def dshow_token(self) -> str:
        """Valor a passar em ``audio=<token>`` no DirectShow."""
        if self.alternative and (":" in self.name or '"' in self.name):
            return self.alternative
        return self.name


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def platform_backend() -> str:
    """Nome do backend de áudio do sistema operacional atual."""
    system = platform.system().lower()
    if system == "windows":
        return "dshow"
    if system == "darwin":
        return "avfoundation"
    return "alsa"


def _run_ffmpeg_list(backend: str) -> str:
    """Executa a listagem de dispositivos do ffmpeg e devolve a saída bruta."""
    if backend == "avfoundation":
        command = [
            _ffmpeg(),
            "-hide_banner",
            "-f",
            "avfoundation",
            "-list_devices",
            "true",
            "-i",
            "",
        ]
    else:
        command = [
            _ffmpeg(),
            "-hide_banner",
            "-list_devices",
            "true",
            "-f",
            backend,
            "-i",
            "dummy",
        ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
    except Exception:
        logger.exception("Falha ao listar dispositivos de áudio (%s)", backend)
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def _parse_dshow(output: str) -> list[AudioDevice]:
    """Extrai os dispositivos de áudio do DirectShow.

    Cada dispositivo aparece como ``"Nome" (audio)`` e, na linha seguinte, o
    ``Alternative name "@device_cm_{...}"``.
    """
    devices: list[AudioDevice] = []
    lines = output.splitlines()
    for index, line in enumerate(lines):
        match = re.search(r'"(.+?)"\s+\(audio\)', line)
        if not match:
            continue
        name = match.group(1)
        alternative: str | None = None
        if index + 1 < len(lines):
            alt = re.search(r'Alternative name\s+"(.+?)"', lines[index + 1])
            if alt:
                alternative = alt.group(1)
        devices.append(AudioDevice(name=name, alternative=alternative))
    return devices


def _parse_avfoundation(output: str) -> list[AudioDevice]:
    """Extrai os dispositivos de áudio do AVFoundation (macOS)."""
    devices: list[AudioDevice] = []
    in_audio_section = False
    for line in output.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio_section = True
            continue
        if not in_audio_section:
            continue
        match = re.search(r"\[(\d+)\]\s+(.+)$", line)
        if match:
            devices.append(AudioDevice(name=match.group(2).strip()))
    return devices


def _alsa_devices() -> list[AudioDevice]:
    """Dispositivos ALSA (Linux).

    Usa o ``arecord -l`` quando disponível e sempre inclui o dispositivo
    ``default``, que costuma funcionar via PulseAudio/PipeWire.
    """
    devices: list[AudioDevice] = [AudioDevice(name="default")]
    arecord = shutil.which("arecord")
    if not arecord:
        return devices
    try:
        result = subprocess.run(
            [arecord, "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        text = result.stdout.decode("utf-8", errors="replace")
        for line in text.splitlines():
            match = re.match(r"card (\d+): (\S+).*device (\d+):", line)
            if match:
                devices.append(
                    AudioDevice(name=f"plughw:{match.group(1)},{match.group(3)}")
                )
    except Exception:
        logger.exception("Falha ao listar dispositivos ALSA")
    return devices


def list_input_devices(force: bool = False) -> list[AudioDevice]:
    """Lista os dispositivos de entrada de áudio disponíveis (com cache curto)."""
    global _cache
    now = time.monotonic()
    with _cache_lock:
        if not force and _cache and now - _cache[0] < _CACHE_TTL_SECONDS:
            return list(_cache[1])

    backend = platform_backend()
    if backend == "alsa":
        devices = _alsa_devices()
    else:
        output = _run_ffmpeg_list(backend)
        devices = (
            _parse_dshow(output)
            if backend == "dshow"
            else _parse_avfoundation(output)
        )

    with _cache_lock:
        _cache = (now, devices)
    return list(devices)


def resolve_audio_input_args(device: str | None) -> list[str]:
    """Argumentos de entrada do ffmpeg para o dispositivo de áudio escolhido.

    ``device`` é o nome amigável salvo nas configurações; quando vazio, usa o
    primeiro dispositivo disponível. Levanta ``RuntimeError`` com uma mensagem
    amigável quando nenhum dispositivo existe.
    """
    backend = platform_backend()
    devices = list_input_devices()

    if device:
        matched = next(
            (
                item
                for item in devices
                if item.name == device or item.alternative == device
            ),
            None,
        )
        if matched is None:
            # Valor informado manualmente que não aparece na enumeração.
            if backend == "dshow":
                return ["-f", "dshow", "-i", f"audio={device}"]
            if backend == "avfoundation":
                return ["-f", "avfoundation", "-i", f":{device}"]
            return ["-f", "alsa", "-i", device]
        chosen = matched
    elif devices:
        chosen = devices[0]
    else:
        raise RuntimeError(
            "Nenhum dispositivo de áudio encontrado. Conecte um microfone ou "
            "webcam com microfone e verifique as permissões do sistema."
        )

    if backend == "dshow":
        return ["-f", "dshow", "-i", f"audio={chosen.dshow_token()}"]
    if backend == "avfoundation":
        index = devices.index(chosen) if chosen in devices else 0
        return ["-f", "avfoundation", "-i", f":{index}"]
    return ["-f", "alsa", "-i", chosen.name]


def build_audio_input_devices(selected: str = "") -> dict[str, object]:
    """Payload de resposta com a plataforma e os dispositivos disponíveis."""
    devices = list_input_devices()
    return {
        "platform": platform_backend(),
        "devices": [
            {"name": item.name, "identifier": item.alternative} for item in devices
        ],
        "selected": selected or "",
    }
