"""Local media storage helpers for clips and thumbnails."""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from app.core.config import get_settings
from app.core.ffmpeg import get_ffmpeg_path

logger = logging.getLogger(__name__)

# Codecs do OpenCV tentados em ordem ao gravar o `.mp4`:
# `avc1`/`H264` (H.264, compatível com navegadores) e `mp4v` (último recurso).
_OPENCV_CODECS = ("avc1", "H264", "mp4v")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def relative_to_captures(path: Path) -> str:
    settings = get_settings()
    try:
        rel = path.resolve().relative_to(settings.captures_dir.resolve())
        return str(rel).replace("\\", "/")
    except Exception:
        return path.name


def save_thumbnail(
    frame: np.ndarray, camera_id: str, visit_id: str, *, quality: int = 85
) -> Path | None:
    settings = get_settings()
    settings.ensure_directories()
    out = settings.thumbs_dir / f"{camera_id}_{visit_id}_{_stamp()}.jpg"
    try:
        ok = cv2.imwrite(
            str(out), frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
        )
        if not ok:
            logger.error("Failed to write thumbnail %s", out)
            return None
        return out
    except Exception:
        logger.exception("Thumbnail save error")
        return None


def save_bird_crop(
    frame: np.ndarray,
    bbox: tuple[float, float, float, float],
    visit_id: str,
    *,
    quality: int = 85,
    margin: float = 0.0,
    min_dimension: int = 0,
    max_dimension: int = 1024,
    enhance: bool = True,
) -> str | None:
    """Salva o recorte da ave em app-data/crops e retorna seu caminho relativo.

    Crop inteligente: ``margin`` adiciona contexto ao redor da caixa (fração do
    tamanho dela), ``min_dimension`` amplia recortes pequenos até uma resolução
    nítida (alta definição) e ``max_dimension`` limita o tamanho final. Os
    padrões preservam o comportamento anterior (corte exato, máx. 1024 px).

    Com ``enhance=True`` (padrão), o recorte passa por um pós-processamento
    cirúrgico de nitidez (:func:`app.infra.ai.enhancement.realcar_recorte_da_ave`):
    CLAHE no canal de luminância + máscara de nitidez. Assim a plumagem fica
    nítida o bastante para o observador humano **e** para a IA externa (Gemini).
    """
    settings = get_settings()
    try:
        settings.ensure_directories()
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        # Margem proporcional ao tamanho da caixa: dá contexto (poleiro, bico,
        # patas) sem cortar a ave.
        if margin > 0:
            pad_x = max(0.0, x2 - x1) * float(margin)
            pad_y = max(0.0, y2 - y1) * float(margin)
            x1, y1, x2, y2 = x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y
        left = max(0, min(width, int(np.floor(x1))))
        top = max(0, min(height, int(np.floor(y1))))
        right = max(0, min(width, int(np.ceil(x2))))
        bottom = max(0, min(height, int(np.ceil(y2))))
        if right <= left or bottom <= top:
            logger.warning("Invalid bird bounding box for crop visit=%s", visit_id)
            return None

        crop = frame[top:bottom, left:right]
        if crop.size == 0:
            logger.warning("Empty bird crop for visit=%s", visit_id)
            return None

        crop_height, crop_width = crop.shape[:2]
        maior = max(crop_width, crop_height)
        scale = 1.0
        if max_dimension and maior > max_dimension:
            scale = max_dimension / float(maior)
        elif min_dimension and maior < min_dimension:
            scale = min_dimension / float(maior)
        if abs(scale - 1.0) > 1e-3:
            interpolacao = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            crop = cv2.resize(
                crop,
                (
                    max(1, round(crop_width * scale)),
                    max(1, round(crop_height * scale)),
                ),
                interpolation=interpolacao,
            )

        # Pós-processamento cirúrgico do recorte: CLAHE + máscara de nitidez.
        # Nitidez aplicada depois do redimensionamento para não perder detalhe.
        if enhance:
            from app.infra.ai.enhancement import realcar_recorte_da_ave

            tratado = realcar_recorte_da_ave(crop)
            if tratado is not None and getattr(tratado, "size", 0) > 0:
                crop = tratado

        output_path = settings.crops_dir / f"{visit_id}.jpg"
        if not cv2.imwrite(
            str(output_path),
            crop,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
        ):
            logger.error("Failed to write bird crop %s", output_path)
            return None
        return output_path.relative_to(settings.app_data_dir).as_posix()
    except Exception:
        logger.exception("Bird crop save error visit=%s", visit_id)
        return None


def _even(value: int) -> int:
    """Garante dimensão par (exigência do H.264 com yuv420p)."""
    return value if value % 2 == 0 else value - 1


def _prepare_frame(
    frame: np.ndarray,
    width: int,
    height: int,
    overlay_fn: Callable[[np.ndarray], np.ndarray] | None = None,
) -> np.ndarray | None:
    """Normaliza um quadro (canais e tamanho) para a codificação de vídeo.

    ``overlay_fn`` (opcional) aplica a tarja de identificação do Alaris sobre o
    quadro antes da codificação — é o que grava a espécie no clipe. A função
    nunca pode alterar o quadro original: deve devolver uma cópia.
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    if overlay_fn is not None:
        try:
            frame = overlay_fn(frame)
        except Exception:
            logger.exception("Falha ao aplicar a tarja de identificação no clipe")
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    if frame.shape[0] != height or frame.shape[1] != width:
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(frame)


def _is_valid_video(path: Path) -> bool:
    """Confere se o arquivo existe, não está vazio e pode ser decodificado."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                return False
            ok, _ = capture.read()
            return bool(ok)
        finally:
            capture.release()
    except Exception:
        logger.exception("Falha ao validar o vídeo %s", path)
        return False


def _encode_with_ffmpeg(
    frames: list[np.ndarray],
    width: int,
    height: int,
    fps: float,
    out_path: Path,
    overlay_fn: Callable[[np.ndarray], np.ndarray] | None = None,
) -> bool:
    """Resgate: codifica os quadros crus direto em H.264/MP4 via ffmpeg.

    Usado apenas quando o `cv2.VideoWriter` não conseguiu gerar um arquivo
    válido. Recebe os quadros pelo `stdin` do ffmpeg com `yuv420p` (obrigatório
    para navegadores) e `+faststart` (índice no início do arquivo).
    """
    ffmpeg = get_ffmpeg_path()
    if ffmpeg is None:
        return False

    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:.6f}",
        "-i",
        "-",
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
        str(out_path),
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except OSError:
        logger.exception("Não foi possível iniciar o ffmpeg para gerar o clipe")
        return False

    try:
        assert process.stdin is not None
        for frame in frames:
            prepared = _prepare_frame(frame, width, height, overlay_fn)
            if prepared is not None:
                process.stdin.write(prepared.tobytes())
        process.stdin.close()
    except (BrokenPipeError, OSError):
        # O ffmpeg pode encerrar o pipe antes do fim em caso de erro; o código
        # de retorno abaixo reporta o problema com mais detalhes.
        logger.warning("ffmpeg encerrou o pipe de entrada antes do fim")

    stderr = b""
    if process.stderr is not None:
        stderr = process.stderr.read()
    return_code = process.wait()
    if return_code != 0:
        logger.error(
            "ffmpeg falhou ao codificar o clipe: %s",
            stderr.decode("utf-8", "ignore").strip(),
        )
        out_path.unlink(missing_ok=True)
        return False
    return _is_valid_video(out_path)


def convert_to_web_mp4(input_path: Path | str, output_path: Path | str) -> bool:
    """Reencoda um vídeo para MP4 H.264 padrão web, usando o ffmpeg.

    Garante o formato que qualquer navegador reproduz: H.264 (`libx264`),
    `yuv420p` e `+faststart` (índice no início, permitindo avançar durante o
    download). Retorna `True` apenas se o arquivo final for decodificável.

    Observação: os clipes do Bem-Ti-Vi não têm faixa de áudio, por isso usamos
    `-an` em vez de codificar áudio (`-acodec aac`).
    """
    ffmpeg = get_ffmpeg_path()
    if ffmpeg is None:
        logger.info("ffmpeg não encontrado; mantendo o arquivo original")
        return False

    output = Path(output_path)
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vcodec",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(output),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError:
        logger.exception("Não foi possível executar o ffmpeg para converter o vídeo")
        return False

    if result.returncode != 0:
        logger.error(
            "ffmpeg falhou ao converter o vídeo: %s",
            result.stderr.decode("utf-8", "ignore").strip(),
        )
        output.unlink(missing_ok=True)
        return False
    return _is_valid_video(output)


def _write_with_opencv(
    frames: list[np.ndarray],
    width: int,
    height: int,
    fps: float,
    out_path: Path,
    overlay_fn: Callable[[np.ndarray], np.ndarray] | None = None,
) -> str | None:
    """Grava os quadros em `.mp4` com o `cv2.VideoWriter`.

    Tenta os codecs em ordem (`avc1`/`H264` → `mp4v`) e devolve o nome do codec
    que gerou um arquivo válido, ou `None` se nenhum funcionou.
    """
    for fourcc_name in _OPENCV_CODECS:
        try:
            fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
            writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
            if not writer.isOpened():
                writer.release()
                continue
            try:
                for frame in frames:
                    prepared = _prepare_frame(frame, width, height, overlay_fn)
                    if prepared is not None:
                        writer.write(prepared)
            finally:
                writer.release()
        except Exception:
            logger.exception("Erro ao gravar o clipe com OpenCV (%s)", fourcc_name)
            out_path.unlink(missing_ok=True)
            continue

        if _is_valid_video(out_path):
            return fourcc_name
        out_path.unlink(missing_ok=True)
    return None


def _warn_if_not_web_safe(codec_name: str, path: Path) -> None:
    """Avisa no log quando o clipe final não é H.264 (pode falhar no navegador)."""
    if codec_name.lower() in {"avc1", "h264"}:
        return
    logger.warning(
        "Clipe %s salvo em %s (não H.264); alguns navegadores podem não "
        "reproduzir. Instale o ffmpeg para gerar H.264 automaticamente.",
        path.name,
        codec_name,
    )


def save_clip_mp4(
    frames: list[np.ndarray],
    camera_id: str,
    visit_id: str,
    fps: float,
    *,
    overlay_fn: Callable[[np.ndarray], np.ndarray] | None = None,
) -> Path | None:
    """Salva o clipe da visita em MP4 compatível com navegadores (H.264).

    Fluxo:
    1. Grava os quadros com o OpenCV em um `.mp4` temporário (`avc1`/`H264` e,
       em último caso, `mp4v`);
    2. Reencoda o resultado para MP4 web-safe (H.264 + `yuv420p` + `faststart`)
       com o ffmpeg e salva o arquivo final na pasta da galeria;
    3. Se o ffmpeg não estiver disponível, mantém o arquivo do OpenCV.

    ``overlay_fn`` (opcional) grava a **tarja de identificação do Alaris** em
    cada quadro — assim o vídeo salvo já mostra a espécie. Clipes corrompidos ou
    vazios são descartados (retorna `None`).
    """
    valid_frames = [
        frame
        for frame in frames
        if frame is not None and getattr(frame, "size", 0) > 0
    ]
    if not valid_frames:
        logger.warning("Nenhum quadro válido para a visita %s", visit_id)
        return None

    settings = get_settings()
    settings.ensure_directories()

    stamp = _stamp()
    # Arquivo temporário (saída do OpenCV) e arquivo final na pasta da galeria.
    intermediate = settings.clips_dir / f".tmp_{camera_id}_{visit_id}_{stamp}.mp4"
    final = settings.clips_dir / f"{camera_id}_{visit_id}_{stamp}.mp4"

    height, width = valid_frames[0].shape[:2]
    # H.264 com yuv420p exige largura e altura pares.
    width = max(2, _even(width))
    height = max(2, _even(height))
    fps = max(float(fps), 1.0)

    try:
        # 1) Gravação com o OpenCV, sempre em `.mp4`.
        codec_name = _write_with_opencv(
            valid_frames, width, height, fps, intermediate, overlay_fn
        )

        if codec_name is not None and _is_valid_video(intermediate):
            # 2) Conversão pós-gravação para MP4 web-safe (H.264).
            if convert_to_web_mp4(intermediate, final):
                return final
            # 3) Sem ffmpeg: mantém o arquivo do OpenCV (renomeado).
            _warn_if_not_web_safe(codec_name, final)
            intermediate.replace(final)
            return final

        # Resgate: o OpenCV não conseguiu gravar; tenta o ffmpeg direto dos
        # quadros crus (sem arquivo intermediário).
        logger.warning(
            "OpenCV não gerou clipe válido (visita %s); usando ffmpeg", visit_id
        )
        if _encode_with_ffmpeg(valid_frames, width, height, fps, final, overlay_fn):
            return final

        final.unlink(missing_ok=True)
        logger.error("Não foi possível codificar o clipe da visita %s", visit_id)
        return None
    finally:
        # Nunca deixa o arquivo temporário para trás.
        intermediate.unlink(missing_ok=True)
