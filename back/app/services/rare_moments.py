"""Curadoria de "Momentos Raros / Fotos de Postal" do Alaris Core.

A rotina faz três coisas, sempre **localmente**:

1. **Mede a nitidez** de cada captura com a variância do Laplaciano (o mesmo
   proxy clássico usado pelo seletor de melhor quadro) e guarda o resultado na
   coluna ``visits.sharpness`` — cada foto é avaliada uma única vez;
2. **Seleciona os destaques** da semana combinando nitidez, confiança da IA e
   raridade da espécie no histórico local (1-2 avistagens = rara);
3. **Monta a foto de postal** para download: moldura elegante, legenda
   ornitológica e a marca d'água oficial do Bem-Te-Vi.

A varredura roda em segundo plano (a cada poucas horas) para que a galeria
abra instantaneamente. Um endpoint manual permite forçar a curadoria.
"""

from __future__ import annotations

import io
import logging
import math
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.core.config import get_settings
from app.infra.database.connection import db_session
from app.infra.database.repository import _clip_url, _media_url

logger = logging.getLogger(__name__)

# Limiares alinhados ao AnalyticsRepository (raridade por avistagens).
RARE_MAX_SIGHTINGS = 2
UNCOMMON_MAX_SIGHTINGS = 9

# Escala de normalização da nitidez para o escore 0-100 exibido no card.
_SHARPNESS_REFERENCE = 600.0

# Dimensões da foto de postal (px).
_POSTCARD_MAX_W = 1280
_POSTCARD_MAX_H = 900
_POSTCARD_PAD = 56
_POSTCARD_CAPTION = 132


def _photo_path(visit_id: str, thumbnail_path: str | None) -> Path | None:
    """Melhor arquivo disponível da visita: recorte tratado ou thumbnail."""
    settings = get_settings()
    crop = settings.crops_dir / f"{visit_id}.jpg"
    if crop.is_file():
        return crop
    if thumbnail_path:
        normalized = str(thumbnail_path).replace("\\", "/").lstrip("/")
        candidate = settings.captures_dir / normalized
        if candidate.is_file():
            return candidate
    return None


def laplacian_variance(path: Path) -> float | None:
    """Variância do Laplaciano da imagem (nitidez), tolerante a falhas.

    A leitura usa ``np.fromfile`` + ``cv2.imdecode`` para funcionar com acentos
    e espaços no caminho (o ``cv2.imread`` falha em alguns caminhos no Windows).
    A imagem é reduzida para no máximo 720 px de largura: suficiente para o
    escore e muito mais rápido em fotos 4K.
    """
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
        if image is None:
            return None
        height, width = image.shape[:2]
        if width > 720 and width > 0:
            scale = 720.0 / float(width)
            image = cv2.resize(
                image,
                (720, max(1, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        return float(cv2.Laplacian(image, cv2.CV_64F).var())
    except Exception:
        logger.exception("Falha ao medir a nitidez de %s", path)
        return None


def _rarity(ecological_status: str | None, sightings: int) -> str:
    status = (ecological_status or "").lower()
    if any(
        token in status
        for token in ("rara", "amea", "vulner", "endanger", "critic")
    ):
        return "Rara"
    if sightings <= RARE_MAX_SIGHTINGS:
        return "Rara"
    if sightings <= UNCOMMON_MAX_SIGHTINGS:
        return "Incomum"
    return "Comum"


def _sharpness_score(sharpness: float) -> int:
    """Normaliza a variância do Laplaciano em uma nota 0-100 legível."""
    if sharpness <= 0:
        return 0
    normalized = 100.0 * math.log1p(sharpness) / math.log1p(_SHARPNESS_REFERENCE)
    return int(max(0, min(100, round(normalized))))


def _display_species(common_name: str | None, raw: str | None) -> str:
    if common_name:
        return common_name
    cleaned = (raw or "").strip()
    if not cleaned or cleaned.lower() in {"bird", "passaro", "pássaro"}:
        return "Pássaro Desconhecido"
    return cleaned


class RareMomentsService:
    """Escore de nitidez, curadoria semanal e geração das fotos de postal."""

    def __init__(self) -> None:
        self.db_path = get_settings().db_path
        self._score_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Nitidez
    # ------------------------------------------------------------------ #
    def score_pending(self, limit: int = 120) -> int:
        """Calcula a nitidez de capturas ainda não avaliadas.

        Devolve quantas fotos foram medidas com sucesso. É seguro chamar em
        paralelo: um lock evita que duas varreduras meçam as mesmas fotos.
        """
        limit = max(1, min(int(limit), 500))
        with self._score_lock:
            with db_session(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT id, thumbnail_path
                    FROM visits
                    WHERE sharpness IS NULL
                      AND thumbnail_path IS NOT NULL
                      AND visitor_kind = 'bird'
                    ORDER BY detected_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

            if not rows:
                return 0

            scored: list[tuple[float, str]] = []
            for row in rows:
                path = _photo_path(row["id"], row["thumbnail_path"])
                if path is None:
                    continue
                value = laplacian_variance(path)
                if value is None:
                    continue
                scored.append((value, row["id"]))

            if scored:
                with db_session(self.db_path) as conn:
                    conn.executemany(
                        "UPDATE visits SET sharpness = ? WHERE id = ?",
                        [(value, visit_id) for value, visit_id in scored],
                    )
            return len(scored)

    def pending_count(self) -> int:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM visits
                WHERE sharpness IS NULL
                  AND thumbnail_path IS NOT NULL
                  AND visitor_kind = 'bird'
                """
            ).fetchone()
        return int(row["c"]) if row else 0

    # ------------------------------------------------------------------ #
    # Curadoria
    # ------------------------------------------------------------------ #
    def _candidates(self, days: int) -> list[dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    v.id, v.camera_id, v.species, v.confidence, v.detected_at,
                    v.thumbnail_path, v.clip_path, v.sharpness, v.location_label,
                    c.name AS camera_name, c.location_label AS camera_location,
                    bs.common_name, bs.scientific_name, bs.ecological_status,
                    (
                        SELECT COUNT(*) FROM visits s
                        WHERE s.visitor_kind = 'bird' AND (
                            (v.species_id IS NOT NULL AND s.species_id = v.species_id)
                            OR (v.species_id IS NULL AND s.species = v.species)
                        )
                    ) AS sightings
                FROM visits v
                LEFT JOIN cameras c ON c.id = v.camera_id
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                WHERE v.visitor_kind = 'bird'
                  AND v.detected_at >= ?
                  AND v.thumbnail_path IS NOT NULL
                ORDER BY v.detected_at DESC
                LIMIT 400
                """,
                (since,),
            ).fetchall()
        return [dict(row) for row in rows]

    def highlights(self, days: int = 7, limit: int = 24) -> dict[str, Any]:
        """Seleciona as melhores capturas da janela, com diversidade de espécies.

        A nota de curadoria soma nitidez (0-100), bônus por raridade e um leve
        peso para a confiança da IA. Para a galeria não virar "10 fotos do mesmo
        sabiá", cada espécie entra no máximo 2 vezes na primeira passada; se
        sobrarem vagas, as demais capturas completam a lista.
        """
        settings = get_settings()
        days = max(1, min(int(days), 90))
        limit = max(6, min(int(limit), 60))

        candidates = self._candidates(days)
        scanned = 0

        # Avalia sob demanda as fotos novas (primeira abertura após a migração).
        missing = [row for row in candidates if row.get("sharpness") is None]
        if missing:
            to_score = missing[:80]
            scored: list[tuple[float, str]] = []
            for row in to_score:
                path = _photo_path(row["id"], row["thumbnail_path"])
                if path is None:
                    continue
                value = laplacian_variance(path)
                if value is None:
                    continue
                row["sharpness"] = value
                scored.append((value, row["id"]))
            if scored:
                with db_session(self.db_path) as conn:
                    conn.executemany(
                        "UPDATE visits SET sharpness = ? WHERE id = ?",
                        [(value, visit_id) for value, visit_id in scored],
                    )
            scanned = len(scored)

        ranked: list[dict[str, Any]] = []
        for row in candidates:
            sharpness = float(row.get("sharpness") or 0.0)
            if sharpness <= 0:
                continue
            rarity = _rarity(row.get("ecological_status"), int(row["sightings"] or 0))
            bonus = 30 if rarity == "Rara" else 12 if rarity == "Incomum" else 0
            rank = (
                _sharpness_score(sharpness)
                + bonus
                + float(row.get("confidence") or 0.0) * 10.0
            )
            photo_path = _photo_path(row["id"], row["thumbnail_path"])
            thumbnail_url = (
                f"/api/visits/{row['id']}/crop"
                if photo_path and photo_path.parent == settings.crops_dir
                else _media_url(row.get("thumbnail_path"))
            )
            garden = (
                row.get("location_label")
                or row.get("camera_location")
                or row.get("camera_name")
            )
            ranked.append(
                {
                    "visit_id": row["id"],
                    "camera_id": row["camera_id"],
                    "camera_name": row.get("camera_name"),
                    "garden": garden,
                    "species": _display_species(
                        row.get("common_name"), row.get("species")
                    ),
                    "scientific_name": row.get("scientific_name"),
                    "detected_at": row["detected_at"],
                    "confidence": float(row.get("confidence") or 0.0),
                    "sharpness": round(sharpness, 2),
                    "sharpness_score": _sharpness_score(sharpness),
                    "rarity": rarity,
                    "is_rare": rarity == "Rara",
                    "thumbnail_url": thumbnail_url,
                    "clip_url": _clip_url(row.get("clip_path")),
                    "postcard_url": (
                        f"/api/gallery/rare-moments/{row['id']}/postcard"
                    ),
                    "reason": (
                        "Espécie rara + nitidez de postal"
                        if rarity == "Rara"
                        else "Espécie incomum + nitidez de postal"
                        if rarity == "Incomum"
                        else "Nitidez de postal"
                    ),
                    "_rank": rank,
                }
            )

        ranked.sort(key=lambda item: item["_rank"], reverse=True)

        # Diversidade: no máximo 2 capturas por espécie na primeira passada.
        selected: list[dict[str, Any]] = []
        per_species: dict[str, int] = {}
        for item in ranked:
            key = (item.get("scientific_name") or item["species"]).lower()
            if per_species.get(key, 0) >= 2:
                continue
            selected.append(item)
            per_species[key] = per_species.get(key, 0) + 1
            if len(selected) >= limit:
                break
        if len(selected) < limit:
            chosen = {item["visit_id"] for item in selected}
            for item in ranked:
                if item["visit_id"] in chosen:
                    continue
                selected.append(item)
                if len(selected) >= limit:
                    break

        for item in selected:
            item.pop("_rank", None)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "days": days,
            "moments": selected,
            "scanned": scanned,
        }

    # ------------------------------------------------------------------ #
    # Foto de postal
    # ------------------------------------------------------------------ #
    @staticmethod
    def _font(size: int, *, bold: bool = False, italic: bool = False) -> Any:
        candidates: list[str] = []
        if bold and italic:
            candidates = ["segoeuibi.ttf", "georgiab.ttf", "arialbi.ttf"]
        elif bold:
            candidates = ["segoeuib.ttf", "georgiab.ttf", "arialbd.ttf"]
        elif italic:
            candidates = ["segoeuii.ttf", "georgiai.ttf", "ariali.ttf"]
        else:
            candidates = ["segoeui.ttf", "georgia.ttf", "arial.ttf"]
        for name in candidates:
            path = Path("C:/Windows/Fonts") / name
            if path.is_file():
                try:
                    return ImageFont.truetype(str(path), size)
                except Exception:
                    continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # Pillow antigo
            return ImageFont.load_default()

    def _fetch_visit(self, visit_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT
                    v.id, v.camera_id, v.species, v.confidence, v.detected_at,
                    v.thumbnail_path, v.location_label,
                    v.local_date, v.local_hour,
                    c.name AS camera_name, c.location_label AS camera_location,
                    c.timezone AS camera_timezone,
                    bs.common_name, bs.scientific_name
                FROM visits v
                LEFT JOIN cameras c ON c.id = v.camera_id
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                WHERE v.id = ?
                """,
                (visit_id,),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _format_when(visit: dict[str, Any]) -> str:
        """Data/hora da visita no **fuso do jardim** (evita a hora UTC crua)."""
        raw = str(visit.get("detected_at") or "")
        try:
            moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        tz_name = visit.get("camera_timezone")
        if tz_name:
            try:
                from zoneinfo import ZoneInfo

                moment = moment.astimezone(ZoneInfo(str(tz_name)))
            except Exception:
                moment = moment.astimezone()
        else:
            moment = moment.astimezone()
        return moment.strftime("%d/%m/%Y · %H:%M")

    def build_postcard(self, visit_id: str) -> bytes | None:
        """Gera a foto de postal (JPEG) com moldura e marca d'água."""
        visit = self._fetch_visit(visit_id)
        if visit is None:
            return None
        path = _photo_path(visit_id, visit.get("thumbnail_path"))
        if path is None:
            return None

        try:
            with Image.open(path) as opened:
                photo = ImageOps.exif_transpose(opened).convert("RGB")
        except Exception:
            logger.exception("Falha ao abrir a foto da visita %s", visit_id)
            return None

        photo.thumbnail((_POSTCARD_MAX_W, _POSTCARD_MAX_H), Image.LANCZOS)
        width, height = photo.size

        # Marca d'água discreta no canto inferior direito da foto.
        overlay = Image.new("RGBA", photo.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        mark_font = self._font(22, bold=True)
        mark = "Bem-Te-Vi"
        box = draw.textbbox((0, 0), mark, font=mark_font)
        text_w, text_h = box[2] - box[0], box[3] - box[1]
        pad = 10
        bubble_w, bubble_h = text_w + pad * 2 + 18, text_h + pad * 2
        x = max(16, width - bubble_w - 22)
        y = max(16, height - bubble_h - 22)
        draw.rounded_rectangle(
            [x, y, x + bubble_w, y + bubble_h],
            radius=10,
            fill=(6, 24, 18, 155),
        )
        dot_x = x + pad + 3
        draw.ellipse(
            [dot_x, y + bubble_h / 2 - 4, dot_x + 8, y + bubble_h / 2 + 4],
            fill=(52, 211, 153, 235),
        )
        draw.text(
            (dot_x + 14, y + pad - box[1]),
            mark,
            font=mark_font,
            fill=(232, 245, 239, 240),
        )
        photo = Image.alpha_composite(photo.convert("RGBA"), overlay).convert("RGB")

        pad = _POSTCARD_PAD
        caption_h = _POSTCARD_CAPTION
        canvas_w = width + pad * 2
        canvas_h = pad + height + 24 + caption_h + 26
        canvas = Image.new("RGB", (canvas_w, canvas_h), (246, 241, 230))
        canvas.paste(photo, (pad, pad))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle(
            [pad - 1, pad - 1, pad + width, pad + height],
            outline=(214, 203, 181),
            width=2,
        )

        species = _display_species(visit.get("common_name"), visit.get("species"))
        scientific = visit.get("scientific_name") or ""
        garden = (
            visit.get("location_label")
            or visit.get("camera_location")
            or visit.get("camera_name")
            or "Jardim Bem-Te-Vi"
        )
        try:
            when = self._format_when(visit)
        except Exception:
            when = str(visit.get("detected_at") or "")

        title_font = self._font(40, bold=True)
        italic_font = self._font(24, italic=True)
        meta_font = self._font(21)
        brand_font = self._font(24, bold=True)
        small_font = self._font(15)

        left = pad + 2
        top = pad + height + 28
        draw.text((left, top), species, font=title_font, fill=(20, 38, 31))
        if scientific:
            draw.text(
                (left, top + 44),
                scientific,
                font=italic_font,
                fill=(103, 116, 108),
            )
        draw.text(
            (left, top + 78),
            f"{when}  ·  {garden}",
            font=meta_font,
            fill=(103, 116, 108),
        )

        # Assinatura oficial no canto direito da legenda.
        brand = "Bem-Te-Vi"
        brand_box = draw.textbbox((0, 0), brand, font=brand_font)
        brand_x = canvas_w - pad - (brand_box[2] - brand_box[0])
        draw.text((brand_x, top + 6), brand, font=brand_font, fill=(16, 122, 87))
        subtitle = "Alaris Core · observação de avifauna"
        sub_box = draw.textbbox((0, 0), subtitle, font=small_font)
        sub_x = canvas_w - pad - (sub_box[2] - sub_box[0])
        draw.text((sub_x, top + 38), subtitle, font=small_font, fill=(140, 150, 142))

        draw.line(
            [(pad, canvas_h - 24), (canvas_w - pad, canvas_h - 24)],
            fill=(226, 217, 199),
            width=1,
        )

        output = io.BytesIO()
        canvas.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue()


_service: RareMomentsService | None = None
_service_lock = threading.Lock()


def get_rare_moments_service() -> RareMomentsService:
    """Instância única (processo) da curadoria de Momentos Raros."""
    global _service
    with _service_lock:
        if _service is None:
            _service = RareMomentsService()
        return _service


class RareMomentsWorker(threading.Thread):
    """Varredura periódica de nitidez em segundo plano.

    A primeira passada começa após alguns segundos (deixa a API e o YOLO
    subirem) e depois repete a cada ``RARE_MOMENTS_SCAN_HOURS``.
    """

    def __init__(self, *, initial_delay: float = 25.0) -> None:
        super().__init__(name="rare-moments-curator", daemon=True)
        self._stop = threading.Event()
        self._initial_delay = max(0.0, initial_delay)

    def run(self) -> None:
        settings = get_settings()
        if self._stop.wait(self._initial_delay):
            return
        interval = max(3600.0, float(settings.rare_moments_scan_hours) * 3600.0)
        while not self._stop.is_set():
            try:
                scanned = get_rare_moments_service().score_pending(limit=160)
                if scanned:
                    logger.info(
                        "Momentos Raros: %s captura(s) avaliada(s) pelo Alaris Core",
                        scanned,
                    )
            except Exception:
                logger.exception("Falha na curadoria de Momentos Raros")
            if self._stop.wait(interval):
                break

    def stop(self) -> None:
        self._stop.set()
