"""Descoberta robusta dos binários do FFmpeg/FFprobe no sistema.

O FFmpeg raramente está no ``PATH`` da sessão em que o backend roda — o winget,
por exemplo, instala em ``%LOCALAPPDATA%\\Microsoft\\WinGet\\Packages`` e só
injeta no ``PATH`` de novos logins. Se o servidor for iniciado por um
script/serviço, ``shutil.which("ffmpeg")`` devolve ``None`` e os recursos que
dependem dele (gravação de clipes, time-lapse do dia e bioacústica) falham
silenciosamente.

Este módulo centraliza a busca para todos os pontos do sistema, tentando, em
ordem: o ``PATH``, as pastas do winget e alguns locais comuns de instalação.
"""

from __future__ import annotations

import glob
import os
import shutil

# Padrões do winget: ``...\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin\ffmpeg.exe``.
_WINGET_PATTERNS = (
    ("Microsoft", "WinGet", "Packages", "*ffmpeg*", "**", "bin"),
    ("Microsoft", "WinGet", "Packages", "*ffmpeg*", "**"),
)
# Locais comuns de instalação manual/chocolatey.
_COMMON_DIRS = (
    r"C:\ffmpeg\bin",
    r"C:\Program Files\ffmpeg\bin",
    r"C:\Program Files (x86)\ffmpeg\bin",
    r"C:\ProgramData\chocolatey\bin",
)


def _exe_name(base: str) -> str:
    """Acrescenta a extensão ``.exe`` no Windows."""
    return f"{base}.exe" if os.name == "nt" else base


def _bundled_ffmpeg() -> str | None:
    """FFmpeg empacotado via pip (``imageio-ffmpeg``), usado como último recurso.

    Garante que os recursos de áudio (BirdNET/bioacústica e enumeração de
    dispositivos) funcionem mesmo quando o usuário não instalou o FFmpeg no
    sistema. O pacote fornece apenas o ``ffmpeg`` — não o ``ffprobe``.
    """
    try:
        import imageio_ffmpeg  # type: ignore

        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - depende do ambiente de instalação
        return None
    return exe if exe and os.path.isfile(exe) else None


def _search(base: str) -> str | None:
    """Procura um executável do FFmpeg em PATH, winget e pastas comuns."""
    exe = _exe_name(base)
    found = shutil.which(base)
    if found:
        return found

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        for parts in _WINGET_PATTERNS:
            pattern = os.path.join(local_app_data, *parts, exe)
            matches = glob.glob(pattern, recursive=True)
            if matches:
                return matches[0]

    for directory in _COMMON_DIRS:
        candidate = os.path.join(directory, exe)
        if os.path.isfile(candidate):
            return candidate

    # Último recurso: binário embutido no pacote Python (sem instalação no SO).
    if base == "ffmpeg":
        return _bundled_ffmpeg()
    return None


def get_ffmpeg_path() -> str | None:
    """Caminho do executável ``ffmpeg`` (ou ``None`` se não encontrado)."""
    return _search("ffmpeg")


def get_ffprobe_path() -> str | None:
    """Caminho do executável ``ffprobe`` (ou ``None`` se não encontrado)."""
    return _search("ffprobe")
