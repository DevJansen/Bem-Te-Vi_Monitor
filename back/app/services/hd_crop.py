"""Exportação do recorte da ave em alta definição (download "Crop HD").

A Galeria exibe um close-up pequeno (por volta de 640–1024 px) para manter o
painel leve. Quando o observador clica em **Baixar Recorte HD (Crop)**, este
módulo monta uma versão otimizada para compartilhar/imprimir:

* reescala com **Lanczos** até o menor lado configurado (padrão 1080 px);
* aplica um *unsharp mask* suave (realça contorno de penas sem exagerar ruído);
* salva em JPEG de alta qualidade, com nome de arquivo amigável.

O arquivo é gerado **uma única vez** por visita (``crops/{id}_hd.jpg``) e
reaproveitado enquanto for mais novo que o recorte original. Caminhos são
sempre validados contra ``app-data/crops`` (proteção contra *path traversal*).
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from app.ai.visit_media import resolve_crop_path, resolve_visit_image
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Teto de segurança para não gerar arquivos gigantes a partir de recortes
# minúsculos (o upscale é limitado a 4x o menor lado original).
_MAX_UPSCALE_FACTOR = 4.0
_MAX_SIDE = 4096


def _read(path: Path) -> np.ndarray | None:
    """Leitura Unicode-safe de imagem BGR."""
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
        if buffer.size == 0:
            return None
        return cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception:
        logger.debug("Imagem ilegível para exportação HD: %s", path, exc_info=True)
        return None


def _write_jpeg(path: Path, image: np.ndarray, quality: int) -> bool:
    """Grava JPEG de forma Unicode-safe (Windows)."""
    try:
        ok, buffer = cv2.imencode(
            ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
        )
        if not ok:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        buffer.tofile(str(path))
        return True
    except Exception:
        logger.exception("Falha ao gravar o recorte HD em %s", path)
        return False


def _enhance(image: np.ndarray, min_side: int) -> np.ndarray:
    """Reescala e realça o recorte, preservando proporção e cores."""
    height, width = image.shape[:2]
    if height == 0 or width == 0:
        return image

    short_side = min(height, width)
    target = max(1, int(min_side))
    scale = 1.0
    if short_side < target:
        # Limita o upscale para não transformar um recorte 32×32 em borrão
        # gigante: no máximo 4x o menor lado original.
        target = min(target, int(round(short_side * _MAX_UPSCALE_FACTOR)))
        scale = target / float(short_side) if short_side else 1.0
    if abs(scale - 1.0) > 0.01:
        new_size = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        # Não deixa o lado maior estourar o teto de segurança.
        if max(new_size) > _MAX_SIDE:
            factor = _MAX_SIDE / float(max(new_size))
            new_size = (
                max(1, int(round(new_size[0] * factor))),
                max(1, int(round(new_size[1] * factor))),
            )
        interpolation = cv2.INTER_LANCZOS4 if scale > 1.0 else cv2.INTER_AREA
        image = cv2.resize(image, new_size, interpolation=interpolation)

    # Unsharp mask: realce discreto de bordas (penas, bico, olho).
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=1.2, sigmaY=1.2)
    image = cv2.addWeighted(image, 1.28, blurred, -0.28, 0)

    # CLAHE leve no canal de luminância: recupera detalhes em sombra sem
    # estourar as altas luzes do comedouro.
    try:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.4, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        image = cv2.cvtColor(
            cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR
        )
    except Exception:
        logger.debug("CLAHE indisponível no recorte HD", exc_info=True)
    return image


def export_hd_crop(
    visit_id: str,
    *,
    settings: Settings | None = None,
    force: bool = False,
) -> Path | None:
    """Garante e devolve o recorte HD da visita (``None`` se não houver mídia).

    O recorte original é preservado; o arquivo HD é um artefato derivado em
    ``app-data/crops/{visit_id}_hd.jpg``.
    """
    settings = settings or get_settings()
    visit_id = (visit_id or "").strip()
    if not visit_id:
        return None

    # Fonte: recorte canônico; se não existir, qualquer imagem tratada da visita
    # (thumbnail) ainda permite um export de qualidade.
    source = resolve_crop_path(visit_id, settings)
    if source is None:
        from app.infra.database.repository import VisitRepository

        row = VisitRepository(settings.db_path).get(visit_id)
        if row is None:
            return None
        source = resolve_visit_image(row, settings)
    if source is None or not source.is_file():
        return None

    crops_root = settings.crops_dir.resolve()
    destination = (crops_root / f"{visit_id}_hd.jpg").resolve()
    if destination.parent != crops_root:
        return None

    if not force and destination.is_file():
        try:
            if destination.stat().st_mtime_ns >= source.stat().st_mtime_ns:
                return destination
        except OSError:
            pass

    image = _read(source)
    if image is None:
        return None
    enhanced = _enhance(image, int(settings.hd_crop_min_side))
    if not _write_jpeg(destination, enhanced, int(settings.hd_crop_jpeg_quality)):
        return None
    logger.info(
        "Recorte HD gerado: %s (%dx%d)",
        destination,
        enhanced.shape[1],
        enhanced.shape[0],
    )
    return destination


def friendly_crop_filename(species: str | None, visit_id: str) -> str:
    """Nome de download amigável e seguro para o sistema de arquivos."""
    from app.ai.active_learning import safe_species_folder

    label = safe_species_folder(species or "ave")
    return f"bem-te-vi-core-{label}-{visit_id[:8]}-hd.jpg"
