"""Geração de resumos do dia (time-lapse) a partir dos clipes das visitas.

Esta é a camada de mídia: sabe **nomear**, **listar**, **construir** e **apagar**
os arquivos ``timelapse_YYYY-MM-DD.mp4`` da pasta
``app-data/captures/timelapses/``. A orquestração (consultar o banco de dados e
agendar a geração no fim do dia) fica em ``app.services.timelapse_service``.

A montagem usa o FFmpeg via ``subprocess`` com o *demuxer* ``concat``: junta
todos os clipes do dia em uma única sequência e acelera o resultado com o filtro
``setpts``. Como câmeras diferentes podem gravar em resoluções distintas, os
quadros são normalizados (``scale`` + ``pad``) para um tamanho único antes de
serem recodificados em H.264, garantindo um MP4 que qualquer navegador
reproduz.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Prefixo/extensão dos resumos do dia (ex.: `timelapse_2026-10-15.mp4`).
TIMELAPSE_PREFIX = "timelapse_"
TIMELAPSE_EXTENSION = ".mp4"
# Arquivo auxiliar (JSON) com os metadados de cada resumo.
_SIDECAR_SUFFIX = ".json"
_FILENAME_RE = re.compile(r"^timelapse_(\d{4}-\d{2}-\d{2})\.mp4$")

# Resolução e taxa de quadros de saída normalizadas. Clipes de câmeras
# diferentes podem ter tamanhos distintos; o `scale`+`pad` garante um vídeo
# uniforme (barras pretas preenchem as sobras quando a proporção difere).
OUTPUT_WIDTH = 1280
OUTPUT_HEIGHT = 720
OUTPUT_FPS = 30


def timelapse_filename(day: date) -> str:
    """Nome do arquivo do resumo para um dia (``timelapse_YYYY-MM-DD.mp4``)."""
    return f"{TIMELAPSE_PREFIX}{day.isoformat()}{TIMELAPSE_EXTENSION}"


def timelapse_path(day: date) -> Path:
    """Caminho completo do resumo do dia na pasta de time-lapses."""
    return get_settings().timelapses_dir / timelapse_filename(day)


def is_timelapse_filename(name: str) -> bool:
    """Confere se o nome segue o padrão ``timelapse_YYYY-MM-DD.mp4``."""
    return bool(_FILENAME_RE.match(name))


def day_from_filename(name: str) -> date | None:
    """Extrai a data (``YYYY-MM-DD``) do nome do arquivo, ou ``None``."""
    match = _FILENAME_RE.match(name)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def timelapse_url(filename: str) -> str:
    """URL de streaming usada pelo player do navegador."""
    return f"/api/videos/timelapse/{filename}"


def resolve_clip_path(clip_path: str | None) -> Path | None:
    """Resolve o caminho de um clipe gravado no banco para um arquivo real.

    O banco guarda o caminho relativo à pasta de capturas (ex.:
    ``clips/abc.mp4``). Por robustez, também aceita caminhos absolutos e o caso
    em que só o nome do arquivo foi salvo.
    """
    if not clip_path:
        return None
    settings = get_settings()
    raw = Path(clip_path)
    if raw.is_absolute():
        return raw
    # Só o nome do arquivo: os clipes ficam na subpasta `clips/`.
    if raw.parent == Path("."):
        return settings.clips_dir / raw.name
    return settings.captures_dir / raw


def list_timelapse_files() -> list[Path]:
    """Lista os resumos existentes, do mais recente para o mais antigo."""
    directory = get_settings().timelapses_dir
    if not directory.exists():
        return []
    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and is_timelapse_filename(path.name)
    ]
    # A data embutida no nome ordena corretamente em ordem lexicográfica.
    files.sort(key=lambda path: path.name, reverse=True)
    return files


def _sidecar_path(video: Path) -> Path:
    """Caminho do JSON auxiliar que acompanha o vídeo (mesmo nome, ``.json``)."""
    return video.with_suffix(_SIDECAR_SUFFIX)


def _write_sidecar(video: Path, metadata: dict[str, Any]) -> None:
    """Grava os metadados do resumo ao lado do MP4 (falha vira aviso no log)."""
    try:
        _sidecar_path(video).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.warning("Não foi possível gravar os metadados de %s", video.name)


def load_metadata(video: Path) -> dict[str, Any]:
    """Lê os metadados do resumo; completa com dados do arquivo quando faltam."""
    day = day_from_filename(video.name)
    metadata: dict[str, Any] = {
        "filename": video.name,
        "day": day.isoformat() if day else "",
        "size_bytes": 0,
        "duration_seconds": None,
        "clips_count": 0,
        "speed": 1.0,
        "generated_at": None,
    }
    sidecar = _sidecar_path(video)
    if sidecar.is_file():
        try:
            metadata.update(json.loads(sidecar.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            logger.warning("Falha ao ler os metadados do time-lapse %s", sidecar)

    # O arquivo manda: tamanho e data de criação são sempre lidos do disco.
    try:
        stat = video.stat()
        metadata["size_bytes"] = int(stat.st_size)
        if not metadata.get("generated_at"):
            metadata["generated_at"] = datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat()
    except OSError:
        pass
    return metadata


def _probe_duration(path: Path) -> float | None:
    """Lê a duração do MP4 com o ``ffprobe`` (``None`` se indisponível/falhar)."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        logger.exception("Falha ao executar o ffprobe em %s", path)
        return None
    if result.returncode != 0:
        return None
    try:
        return round(float(result.stdout.decode("utf-8", "ignore").strip()), 2)
    except ValueError:
        return None


def _concat_listing(clips: list[Path]) -> str:
    """Monta o arquivo de entrada do demuxer ``concat`` (um ``file`` por clipe)."""
    lines: list[str] = []
    for clip in clips:
        # O FFmpeg aceita barras normais no Windows; aspas simples são escapadas.
        safe = clip.as_posix().replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    return "\n".join(lines) + "\n"


def _usable_clips(clips: list[Path]) -> list[Path]:
    """Filtra apenas clipes existentes e com conteúdo."""
    usable: list[Path] = []
    for clip in clips:
        try:
            if clip.is_file() and clip.stat().st_size > 0:
                usable.append(clip)
        except OSError:
            continue
    return usable


def build_timelapse(
    clips: list[Path],
    day: date,
    speed: float,
) -> dict[str, Any] | None:
    """Concatena e acelera os clipes do dia em ``timelapse_YYYY-MM-DD.mp4``.

    Devolve os metadados do arquivo gerado, ou ``None`` em caso de falha. Nunca
    lança exceção: problemas de FFmpeg/arquivo viram log + ``None`` para não
    derrubar o pipeline nem o agendador em segundo plano.
    """
    settings = get_settings()
    settings.ensure_directories()

    valid_clips = _usable_clips(clips)
    if not valid_clips:
        logger.info("Nenhum clipe válido para o time-lapse de %s", day)
        return None

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        logger.warning(
            "ffmpeg não encontrado; não foi possível gerar o time-lapse de %s",
            day,
        )
        return None

    output = timelapse_path(day)
    speed = max(1.0, float(speed))

    # Lista de entrada do demuxer `concat` (arquivo temporário na própria pasta).
    list_file = settings.timelapses_dir / f".concat_{day.isoformat()}.txt"
    try:
        list_file.write_text(_concat_listing(valid_clips), encoding="utf-8")
    except OSError:
        logger.exception("Não foi possível escrever a lista de concatenação")
        return None

    # Normaliza a geometria e acelera o vídeo (`setpts=PTS/speed`).
    filter_chain = (
        f"setpts=PTS/{speed:.4f},"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={OUTPUT_FPS}"
    )
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-vf",
        filter_chain,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        logger.exception(
            "Não foi possível executar o ffmpeg para o time-lapse de %s", day
        )
        output.unlink(missing_ok=True)
        return None
    finally:
        list_file.unlink(missing_ok=True)

    if result.returncode != 0:
        logger.error(
            "ffmpeg falhou ao gerar o time-lapse de %s: %s",
            day,
            result.stderr.decode("utf-8", "ignore").strip(),
        )
        output.unlink(missing_ok=True)
        return None

    duration = _probe_duration(output)
    if duration is None or not output.is_file() or output.stat().st_size == 0:
        logger.error("O time-lapse de %s não pôde ser validado", day)
        output.unlink(missing_ok=True)
        return None

    metadata: dict[str, Any] = {
        "filename": output.name,
        "day": day.isoformat(),
        "size_bytes": int(output.stat().st_size),
        "duration_seconds": duration,
        "clips_count": len(valid_clips),
        "speed": round(speed, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_sidecar(output, metadata)
    logger.info(
        "Time-lapse de %s gerado (%d clipes, %.1fs, %.1f MB)",
        day,
        len(valid_clips),
        duration,
        metadata["size_bytes"] / 1_048_576,
    )
    return metadata


def delete_timelapse(video: Path) -> bool:
    """Remove o MP4 do resumo e o JSON auxiliar. Devolve ``True`` se removeu."""
    if not video.is_file():
        return False
    try:
        video.unlink()
    except OSError:
        logger.exception("Falha ao remover o time-lapse %s", video.name)
        return False
    _sidecar_path(video).unlink(missing_ok=True)
    return True
