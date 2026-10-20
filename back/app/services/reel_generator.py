"""Gerador automático de Reels / Shorts verticais (9:16) para redes sociais.

Pega o clipe original de ~6 segundos da visita, aplica um corte vertical focado
na ave (bounding box), sobrepõe uma moldura elegante translúcida com a marca
d'água oficial do Bem-Ti-Vi, o nome popular/científico da espécie e a
temperatura do momento, e entrega um MP4 vertical 1080x1920 pronto para
Instagram, TikTok e YouTube Shorts.

O vídeo é gerado uma única vez por visita (cache em ``app-data/captures/reels``)
e reaproveitado nas próximas solicitações.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.ffmpeg import get_ffmpeg_path, get_ffprobe_path
from app.infra.database.repository import VisitRepository

logger = logging.getLogger(__name__)

# Dimensões do Reel vertical (9:16).
_REEL_WIDTH = 1080
_REEL_HEIGHT = 1920


def _resolve_clip(clip_relative: str | None) -> Path | None:
    """Resolve o caminho do clipe garantindo que fique dentro de ``clips/``.

    O banco grava o caminho relativo a ``captures`` (ex.: ``clips/x.mp4``),
    mas a pasta de clipes já é ``captures/clips``. Por isso o prefixo ``clips/``
    é removido antes da resolução.
    """
    if not clip_relative:
        return None
    cleaned = str(clip_relative).replace("\\", "/").strip()
    cleaned = cleaned.removeprefix("captures/").removeprefix("clips/")
    if not cleaned or "/" in cleaned or "\\" in cleaned:
        return None
    clips_dir = get_settings().clips_dir.resolve()
    candidate = (clips_dir / cleaned).resolve()
    if candidate.parent != clips_dir:
        return None
    return candidate


def _ffprobe_dimensions(path: Path) -> tuple[int, int]:
    """Obtém largura/altura do vídeo original via ffprobe."""
    ffprobe = get_ffprobe_path()
    if ffprobe is None:
        return 1280, 720
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        logger.debug("ffprobe indisponível para %s", path, exc_info=True)
    return 1280, 720


def _build_filter(
    src_w: int,
    src_h: int,
    bbox: list[float] | None,
    *,
    common_name: str,
    scientific_name: str,
    temperature: float | None,
    detected_at: str,
    brand: str,
) -> str:
    """Monta o filtro FFmpeg completo: crop vertical → escala → overlays.

    O crop é centrado na bounding box da ave quando disponível; caso contrário,
    usa o centro do quadro. A moldura translúcida cobre o topo e a base com
    gradiente escuro para legibilidade do texto.
    """
    # --- Crop vertical 9:16 centrado na ave ---
    target_ratio = 9 / 16
    src_ratio = src_w / src_h if src_h else 0.5625

    if bbox and len(bbox) == 4:
        # bounding box normalizada (0..1) ou absoluta — tenta detectar escala.
        x1, y1, x2, y2 = bbox
        if max(x1, y1, x2, y2) <= 1.0:
            cx = (x1 + x2) / 2 * src_w
            cy = (y1 + y2) / 2 * src_h
        else:
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
    else:
        cx, cy = src_w / 2, src_h / 2

    # Área de crop: mantém a proporção 9:16.
    if src_ratio > target_ratio:
        # Fonte mais larga que 9:16 → limita pela altura.
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        # Fonte mais alta que 9:16 → limita pela largura.
        crop_w = src_w
        crop_h = int(src_w / target_ratio)

    x = max(0, min(int(cx - crop_w / 2), src_w - crop_w))
    y = max(0, min(int(cy - crop_h / 2), src_h - crop_h))

    # --- Gradiente escuro no topo e na base ---
    # drawbox com cor preta e alpha cria faixas translúcidas.
    top_h = int(_REEL_HEIGHT * 0.18)
    bottom_h = int(_REEL_HEIGHT * 0.28)

    # --- Linhas de texto ---
    temp_str = f"{temperature:.1f} °C" if temperature is not None else ""
    date_str = detected_at[:10].replace("-", "/") if detected_at else ""

    # Filtro composto: crop → scale → drawbox(top) → drawbox(bottom) → texts.
    # O FFmpeg precisa de caminhos de fonte explícitos no Windows (fontconfig
    # não está configurado). Procuramos fontes padrão do sistema; se nenhuma
    # for encontrada, pulamos a sobreposição de texto (o vídeo ainda é gerado).
    filters = [
        f"crop={crop_w}:{crop_h}:{x}:{y}",
        f"scale={_REEL_WIDTH}:{_REEL_HEIGHT}",
        # Faixa superior translúcida.
        f"drawbox=x=0:y=0:w={_REEL_WIDTH}:h={top_h}:color=black@0.55:t=fill",
        # Faixa inferior translúcida.
        f"drawbox=x=0:y={_REEL_HEIGHT - bottom_h}:w={_REEL_WIDTH}:h={bottom_h}:color=black@0.60:t=fill",
    ]

    # Texto: marca d'água + espécie + científica + temperatura + data.
    # Posições relativas ao vídeo 1080x1920.
    safe_common = common_name.replace("'", "").replace(":", "").replace("\\", "")
    safe_sci = scientific_name.replace("'", "").replace(":", "").replace("\\", "") if scientific_name else ""
    safe_brand = brand.replace("'", "").replace(":", "").replace("\\", "")

    y_top = int(_REEL_HEIGHT * 0.04)
    y_bottom_start = _REEL_HEIGHT - bottom_h + int(bottom_h * 0.08)

    # Detecta fontes do sistema para o drawtext (fontconfig não funciona no Windows).
    regular_font = None
    bold_font = None
    from pathlib import Path

    font_candidates_regular = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    font_candidates_bold = [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    for candidate in font_candidates_regular:
        if candidate.is_file():
            regular_font = candidate
            break
    for candidate in font_candidates_bold:
        if candidate.is_file():
            bold_font = candidate
            break

    # FFmpeg no Windows não aceita barras invertidas no fontfile — usa POSIX.
    # O dois-pontos do drive (C:) precisa ser escapado (\:) senão o parser do
    # filtro interpreta como separador de opções.
    regular_font_str = regular_font.as_posix().replace(":", "\\:") if regular_font else None
    bold_font_str = bold_font.as_posix().replace(":", "\\:") if bold_font else None

    if safe_brand and regular_font_str:
        filters.append(
            f"drawtext=text='{safe_brand}':fontsize=28:fontcolor=white@0.9:"
            f"x=(w-text_w)/2:y={y_top}:fontfile='{regular_font_str}'"
        )
    if safe_common and bold_font_str:
        filters.append(
            f"drawtext=text='{safe_common}':fontsize=52:fontcolor=white:"
            f"x=(w-text_w)/2:y={y_bottom_start}:fontfile='{bold_font_str}'"
        )
    if safe_sci and regular_font_str:
        filters.append(
            f"drawtext=text='{safe_sci}':fontsize=36:fontcolor=white@0.85:"
            f"x=(w-text_w)/2:y={y_bottom_start + 65}:fontfile='{regular_font_str}'"
        )
    if temp_str and regular_font_str:
        filters.append(
            f"drawtext=text='{temp_str}':fontsize=32:fontcolor=white@0.9:"
            f"x=(w-text_w)/2:y={y_bottom_start + 120}:fontfile='{regular_font_str}'"
        )
    if date_str and regular_font_str:
        filters.append(
            f"drawtext=text='{date_str}':fontsize=24:fontcolor=white@0.7:"
            f"x=(w-text_w)/2:y={y_bottom_start + 170}:fontfile='{regular_font_str}'"
        )

    return ",".join(filters)


def generate_reel(
    visit_id: str,
    *,
    force: bool = False,
) -> dict[str, Any] | None:
    """Gera (ou reaproveita) o Reel vertical de uma visita.

    Retorna um dicionário com ``url``, ``path``, ``size_bytes`` e
    ``duration_seconds``, ou ``None`` quando o clipe não existe.
    """
    settings = get_settings()
    repo = VisitRepository(settings.db_path)

    visit = repo.get(visit_id)
    if visit is None:
        return None

    clip_relative = visit.get("clip_path")
    clip_path = _resolve_clip(clip_relative)
    if clip_path is None or not clip_path.is_file():
        logger.debug("Clipe não encontrado para visita %s", visit_id)
        return None

    reels_dir = settings.captures_dir / "reels"
    reels_dir.mkdir(parents=True, exist_ok=True)
    reel_path = reels_dir / f"{visit_id}.mp4"

    if reel_path.is_file() and reel_path.stat().st_size > 0 and not force:
        return _reel_info(reel_path)

    ffmpeg = get_ffmpeg_path()
    if ffmpeg is None:
        logger.error("FFmpeg não disponível para gerar Reel.")
        return None

    src_w, src_h = _ffprobe_dimensions(clip_path)
    bbox = visit.get("bbox")
    common_name = visit.get("assigned_species_common_name") or visit.get("species") or "Ave"
    scientific_name = visit.get("assigned_species_scientific_name") or visit.get("scientific_name") or ""
    temperature = visit.get("temperature")
    detected_at = visit.get("detectado_em") or visit.get("detected_at") or ""
    brand = "Bem-Ti-Vi"

    vf = _build_filter(
        src_w,
        src_h,
        bbox,
        common_name=common_name,
        scientific_name=scientific_name,
        temperature=temperature,
        detected_at=detected_at,
        brand=brand,
    )

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y" if force else "-n",
        "-i", str(clip_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(reel_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        logger.error("Timeout ao gerar Reel para visita %s", visit_id)
        return None
    except subprocess.CalledProcessError as exc:
        logger.error(
            "FFmpeg falhou ao gerar Reel para visita %s: %s",
            visit_id,
            exc.stderr.decode("utf-8", errors="replace")[:300],
        )
        return None

    return _reel_info(reel_path)


def _reel_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "url": f"/api/media/reel/{path.stem}",
        "path": str(path),
        "size_bytes": stat.st_size,
        "generated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def remove_reel(visit_id: str) -> None:
    """Remove o Reel de uma visita (quando o registro é excluído)."""
    reels_dir = get_settings().captures_dir / "reels"
    path = reels_dir / f"{visit_id}.mp4"
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("Não foi possível remover o Reel %s", path, exc_info=True)
