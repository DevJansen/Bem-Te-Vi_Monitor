"""Reidentificação individual por assinaturas visuais.

Além de saber **qual espécie** pousou no comedouro, o Bem-Te-Vi Core passa a
reconhecer **quem** voltou. Para cada captura nítida, o módulo extrai um vetor
de características (embedding) e compara, por similaridade de cosseno, com os
indivíduos já vistos daquela espécie na galeria "Minhas Aves".

Dois extratores são suportados, com escolha automática:

1. **MobileNetV3-Small** (``torchvision``) — embedding de 576 dimensões,
   rápido o bastante para CPU e com boa capacidade de separar padrões de
   plumagem. Os pesos pré-treinados são baixados na primeira utilização.
2. **Descritor OpenCV** (fallback offline) — histogramas de cor HSV em grade
   espacial + orientação de gradientes (180 dimensões). Não depende de
   ``torch``/internet e mantém o recurso funcional em instalações mínimas.

Indivíduos recorrentes são apresentados como **“Conhecido do Jardim”**, com
histórico próprio (primeira/última visita, nº de avistagens e similaridade).
O centróide de cada indivíduo é atualizado de forma incremental e normalizada,
sem guardar todas as imagens em memória.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.config import get_settings
from app.infra.database.connection import db_session
from app.infra.database.repository import VisitRepository

logger = logging.getLogger(__name__)

_GENERIC_SPECIES = {
    "bird",
    "passaro",
    "passaros",
    "passaro desconhecido",
    "pássaro desconhecido",
    "ave",
    "aves",
    "ave (genérica)",
    "ave (generica)",
    "ave nao identificada",
    "ave não identificada",
    "não identificada",
    "nao identificada",
    "unidentified",
    "unknown",
    "desconhecida",
    "desconhecido",
}

# Dimensões de entrada da MobileNetV3 (padrão ImageNet).
_INPUT_SIZE = 224
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_generic(name: str | None) -> bool:
    cleaned = (name or "").strip()
    return not cleaned or cleaned.casefold() in _GENERIC_SPECIES


def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    """Normaliza um vetor para norma 1 (similaridade = produto escalar)."""
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        return vector
    return vector / norm


def _read_image(path: Path) -> np.ndarray | None:
    """Lê uma imagem em BGR de forma segura para caminhos Unicode (Windows)."""
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
        if buffer.size == 0:
            return None
        return cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception:
        logger.debug("Imagem ilegível para embedding: %s", path, exc_info=True)
        return None


def image_sharpness(image: np.ndarray) -> float | None:
    """Variância do Laplaciano (nitidez), calculada em resolução reduzida."""
    if image is None or image.size == 0:
        return None
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]
        if width > 720:
            scale = 720.0 / float(width)
            gray = cv2.resize(
                gray,
                (720, max(1, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return None


class _OpenCvDescriptor:
    """Descritor offline de cor + textura (sem dependências de deep learning)."""

    name = "opencv_hsv_gradient_v1"
    dimension = 180

    def extract(self, image: np.ndarray) -> np.ndarray:
        resized = cv2.resize(image, (128, 128), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        features: list[np.ndarray] = []

        # Cor por célula espacial (grade 4x4): preserva a distribuição de
        # plumagem no corpo da ave (cabeça, peito, asas, cauda).
        height, width = hsv.shape[:2]
        cell_h, cell_w = height // 4, width // 4
        for row in range(4):
            for col in range(4):
                cell = hsv[
                    row * cell_h : (row + 1) * cell_h,
                    col * cell_w : (col + 1) * cell_w,
                ]
                for channel in range(3):
                    values = cell[:, :, channel].astype(np.float32)
                    features.append(
                        np.array(
                            [values.mean() / 255.0, values.std() / 128.0],
                            dtype=np.float32,
                        )
                    )

        # Histogramas globais (matiz ponderada pela saturação).
        hue = cv2.calcHist(
            [hsv], [0], hsv[:, :, 1] > 24, [32], [0, 180]
        ).reshape(-1)
        saturation = cv2.calcHist([hsv], [1], None, [16], [0, 256]).reshape(-1)
        value = cv2.calcHist([hsv], [2], None, [16], [0, 256]).reshape(-1)
        for histogram in (hue, saturation, value):
            total = float(histogram.sum())
            features.append(
                (histogram / total if total > 0 else histogram).astype(np.float32)
            )

        # Textura: orientação e magnitude dos gradientes (Sobel).
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        magnitude = cv2.magnitude(sobel_x, sobel_y)
        orientation = (np.arctan2(sobel_y, sobel_x) + np.pi) * (
            18.0 / (2.0 * np.pi)
        )
        histogram, _ = np.histogram(
            orientation.ravel(),
            bins=18,
            range=(0, 18),
            weights=magnitude.ravel(),
        )
        total = float(histogram.sum())
        features.append(
            (histogram / total if total > 0 else histogram).astype(np.float32)
        )
        features.append(
            np.array(
                [float(magnitude.mean()) / 255.0, float(magnitude.std()) / 255.0],
                dtype=np.float32,
            )
        )
        return _l2_normalize(np.concatenate(features))


class _MobileNetExtractor:
    """Extrator MobileNetV3-Small (torchvision) com pooling global."""

    name = "mobilenet_v3_small"
    dimension = 576

    def __init__(self) -> None:
        import torch
        from torchvision import models

        weights = models.MobileNet_V3_Small_Weights.DEFAULT
        network = models.mobilenet_v3_small(weights=weights)
        network.classifier = torch.nn.Identity()
        network.eval()
        self._torch = torch
        self._network = network

    def extract(self, image: np.ndarray) -> np.ndarray:
        torch = self._torch
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(
            rgb, (_INPUT_SIZE, _INPUT_SIZE), interpolation=cv2.INTER_AREA
        )
        tensor = (
            torch.from_numpy(resized.astype(np.float32) / 255.0)
            .permute(2, 0, 1)
            .unsqueeze(0)
        )
        mean = torch.from_numpy(_IMAGENET_MEAN).view(1, 3, 1, 1)
        std = torch.from_numpy(_IMAGENET_STD).view(1, 3, 1, 1)
        tensor = (tensor - mean) / std
        with torch.no_grad():
            features = self._network(tensor)
        return _l2_normalize(features.squeeze(0).cpu().numpy())


class VisualEmbeddingService:
    """Gera assinaturas visuais e mantém os indivíduos do jardim."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.db_path = self.settings.db_path
        self._lock = threading.Lock()
        self._extractor: Any | None = None
        self._extractor_name = ""
        self._torch_unavailable = False

    # ------------------------------------------------------------------ #
    # Extrator
    # ------------------------------------------------------------------ #
    def _get_extractor(self) -> tuple[Any | None, str]:
        """Carrega o melhor extrator disponível (thread-safe e preguiçoso)."""
        with self._lock:
            if self._extractor is not None:
                return self._extractor, self._extractor_name
            if not self._torch_unavailable:
                try:
                    extractor: Any = _MobileNetExtractor()
                    self._extractor = extractor
                    self._extractor_name = extractor.name
                    logger.info(
                        "Extrator de assinaturas visuais: %s (%sD)",
                        extractor.name,
                        extractor.dimension,
                    )
                    return self._extractor, self._extractor_name
                except Exception as exc:
                    self._torch_unavailable = True
                    logger.warning(
                        "MobileNetV3 indisponível (%s); usando descritor OpenCV "
                        "offline para reidentificação individual.",
                        exc,
                    )
            extractor = _OpenCvDescriptor()
            self._extractor = extractor
            self._extractor_name = extractor.name
            return self._extractor, self._extractor_name

    def extract_embedding(
        self, image: np.ndarray
    ) -> tuple[np.ndarray | None, str]:
        """Extrai a assinatura normalizada de uma imagem BGR."""
        if image is None or image.size == 0:
            return None, ""
        extractor, name = self._get_extractor()
        if extractor is None:
            return None, ""
        try:
            vector = extractor.extract(image)
            if vector is None or vector.size == 0:
                return None, name
            return _l2_normalize(vector), name
        except Exception:
            logger.exception("Falha ao extrair a assinatura visual")
            return None, name

    # ------------------------------------------------------------------ #
    # Localização da imagem e do indivíduo
    # ------------------------------------------------------------------ #
    def _best_image_path(self, row: dict[str, Any]) -> Path | None:
        settings = self.settings
        metadata: dict[str, Any] = {}
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            metadata = {}
        crop_relative = metadata.get("crop_path")
        if isinstance(crop_relative, str) and crop_relative.strip():
            candidate = (settings.app_data_dir / crop_relative).resolve()
            try:
                candidate.relative_to(settings.app_data_dir.resolve())
            except ValueError:
                candidate = None  # type: ignore[assignment]
            if candidate is not None and candidate.is_file():
                return candidate
        canonical = settings.crops_dir / f"{row['id']}.jpg"
        if canonical.is_file():
            return canonical
        thumbnail = row.get("thumbnail_path")
        if thumbnail:
            normalized = str(thumbnail).replace("\\", "/").lstrip("/")
            candidate = (settings.captures_dir / normalized).resolve()
            try:
                candidate.relative_to(settings.captures_dir.resolve())
            except ValueError:
                return None
            if candidate.is_file():
                return candidate
        return None

    def _species_of(
        self, row: dict[str, Any], common_name: str | None
    ) -> tuple[str, str | None, str | None]:
        common = (
            common_name
            or row.get("assigned_species_common_name")
            or row.get("species")
            or ""
        ).strip()
        return (
            common,
            row.get("species_id"),
            row.get("assigned_species_scientific_name"),
        )

    @staticmethod
    def _decode_centroid(blob: Any, dimension: int) -> np.ndarray | None:
        if blob is None:
            return None
        try:
            vector = np.frombuffer(blob, dtype=np.float32)
        except (TypeError, ValueError):
            return None
        if vector.size == 0:
            return None
        if dimension > 0 and vector.size != dimension:
            return None
        return _l2_normalize(vector)

    def _existing_sample(self, visit_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT s.*, i.nickname AS individual_nickname,
                       i.samples_count AS individual_samples,
                       i.last_seen_at AS individual_last_seen
                FROM bird_embedding_samples s
                LEFT JOIN bird_individuals i ON i.id = s.individual_id
                WHERE s.visit_id = ?
                """,
                (visit_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _sample_result(row: dict[str, Any], threshold: float) -> dict[str, Any]:
        similarity = row.get("similarity")
        return {
            "individual_id": row.get("individual_id"),
            "nickname": row.get("individual_nickname"),
            "known": bool(
                similarity is not None and float(similarity) >= threshold
            ),
            "similarity": round(float(similarity), 4)
            if similarity is not None
            else None,
            "samples_count": int(row.get("individual_samples") or 0),
            "model": row.get("model"),
            "species": row.get("common_name"),
            "skipped": None,
        }

    # ------------------------------------------------------------------ #
    # Registro de uma visita
    # ------------------------------------------------------------------ #
    def register_visit(
        self,
        visit_id: str,
        *,
        common_name: str | None = None,
        scientific_name: str | None = None,
        image_path: Path | str | None = None,
        force: bool = False,
    ) -> dict[str, Any] | None:
        """Cria/atualiza a assinatura visual de uma visita.

        A inferência acontece **antes** da transação do SQLite: nenhuma conexão
        fica presa durante a extração. Falhas retornam ``None`` (ou um dicionário
        com ``skipped``) e nunca interrompem o pipeline de captura.
        """
        if not self.settings.visual_embeddings_enabled:
            return None
        threshold = float(self.settings.individual_match_threshold)

        repository = VisitRepository(self.db_path)
        row = repository.get(visit_id)
        if row is None or (row.get("visitor_kind") or "bird") != "bird":
            return None

        existing = self._existing_sample(visit_id)
        if existing is not None and not force:
            return self._sample_result(existing, threshold)

        common, species_id, catalog_scientific = self._species_of(row, common_name)
        if _is_generic(common):
            return {"skipped": "generic_species", "individual_id": None}
        scientific = scientific_name or catalog_scientific

        path = Path(image_path) if image_path else self._best_image_path(row)
        if path is None or not path.is_file():
            return {"skipped": "missing_image", "individual_id": None}

        image = _read_image(path)
        if image is None:
            return {"skipped": "unreadable_image", "individual_id": None}

        sharpness = image_sharpness(image)
        minimum_sharpness = float(self.settings.individual_min_sharpness)
        if sharpness is None or sharpness < minimum_sharpness:
            logger.debug(
                "Assinatura visual ignorada (nitidez %.1f < %.1f): %s",
                sharpness or 0.0,
                minimum_sharpness,
                path,
            )
            return {
                "skipped": "low_sharpness",
                "sharpness": round(float(sharpness or 0.0), 2),
                "individual_id": None,
            }

        embedding, model_name = self.extract_embedding(image)
        if embedding is None:
            return {"skipped": "embedding_failed", "individual_id": None}

        dimension = int(embedding.size)
        detected_at = row.get("detected_at") or utc_now()
        now = utc_now()

        with db_session(self.db_path) as conn:
            if species_id:
                candidates = conn.execute(
                    """
                    SELECT id, nickname, centroid, dimension, samples_count,
                           first_seen_at
                    FROM bird_individuals
                    WHERE species_id = ?
                    ORDER BY samples_count DESC, last_seen_at DESC
                    LIMIT ?
                    """,
                    (species_id, int(self.settings.individual_max_candidates)),
                ).fetchall()
            else:
                candidates = conn.execute(
                    """
                    SELECT id, nickname, centroid, dimension, samples_count,
                           first_seen_at
                    FROM bird_individuals
                    WHERE species_id IS NULL
                      AND common_name = ? COLLATE NOCASE
                    ORDER BY samples_count DESC, last_seen_at DESC
                    LIMIT ?
                    """,
                    (common, int(self.settings.individual_max_candidates)),
                ).fetchall()

            best_row: dict[str, Any] | None = None
            best_similarity = -1.0
            for candidate in candidates:
                centroid = self._decode_centroid(
                    candidate["centroid"], int(candidate["dimension"] or 0)
                )
                if centroid is None:
                    continue
                if centroid.size != embedding.size:
                    continue
                similarity = float(np.dot(centroid, embedding))
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_row = dict(candidate)

            matched = best_row is not None and best_similarity >= threshold
            if matched and best_row is not None:
                individual_id = str(best_row["id"])
                nickname = best_row.get("nickname")
                old_count = int(best_row.get("samples_count") or 0)
                old_centroid = self._decode_centroid(
                    best_row.get("centroid"), int(best_row.get("dimension") or 0)
                )
                new_count = old_count + 1
                if old_centroid is not None and old_centroid.size == embedding.size:
                    centroid = _l2_normalize(
                        old_centroid * float(old_count) + embedding
                    )
                else:
                    centroid = embedding
                    new_count = 1
                conn.execute(
                    """
                    UPDATE bird_individuals
                       SET centroid = ?, dimension = ?, samples_count = ?,
                           last_seen_at = ?,
                           scientific_name = COALESCE(?, scientific_name),
                           updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        centroid.astype(np.float32).tobytes(),
                        dimension,
                        new_count,
                        detected_at,
                        scientific,
                        now,
                        individual_id,
                    ),
                )
                similarity_value = round(best_similarity, 4)
                known = True
            else:
                individual_id = uuid.uuid4().hex
                total = conn.execute(
                    "SELECT COUNT(*) AS total FROM bird_individuals "
                    "WHERE common_name = ? COLLATE NOCASE",
                    (common,),
                ).fetchone()
                index = int(total["total"] or 0) + 1
                nickname = f"Conhecido do Jardim • {common} #{index:02d}"
                conn.execute(
                    """
                    INSERT INTO bird_individuals (
                        id, species_id, common_name, scientific_name, nickname,
                        centroid, dimension, samples_count, first_seen_at,
                        last_seen_at, representative_visit_id, created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        individual_id,
                        species_id,
                        common,
                        scientific,
                        nickname,
                        embedding.astype(np.float32).tobytes(),
                        dimension,
                        detected_at,
                        detected_at,
                        visit_id,
                        now,
                        now,
                    ),
                )
                similarity_value = None
                known = False

            conn.execute(
                """
                INSERT INTO bird_embedding_samples (
                    id, visit_id, individual_id, species_id, common_name,
                    embedding, dimension, similarity, model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(visit_id) DO UPDATE SET
                    individual_id = excluded.individual_id,
                    species_id = excluded.species_id,
                    common_name = excluded.common_name,
                    embedding = excluded.embedding,
                    dimension = excluded.dimension,
                    similarity = excluded.similarity,
                    model = excluded.model,
                    created_at = excluded.created_at
                """,
                (
                    uuid.uuid4().hex,
                    visit_id,
                    individual_id,
                    species_id,
                    common,
                    embedding.astype(np.float32).tobytes(),
                    dimension,
                    similarity_value,
                    model_name,
                    now,
                ),
            )
            samples_count = conn.execute(
                "SELECT samples_count FROM bird_individuals WHERE id = ?",
                (individual_id,),
            ).fetchone()
            count = int(samples_count["samples_count"] or 0) if samples_count else 1

        result = {
            "individual_id": individual_id,
            "nickname": nickname,
            "known": known,
            "similarity": similarity_value,
            "samples_count": count,
            "model": model_name,
            "species": common,
            "skipped": None,
        }

        # Metadados da visita: enriquecem o card da Galeria e o histórico
        # individual sem exigir uma segunda consulta ao banco.
        try:
            repository.update_metadata(
                visit_id,
                {
                    "individual": {
                        "id": individual_id,
                        "nickname": nickname,
                        "known": known,
                        "similarity": similarity_value,
                        "samples": count,
                        "model": model_name,
                        "species": common,
                    }
                },
            )
        except Exception:
            logger.debug(
                "Falha ao gravar o indivíduo nos metadados da visita %s",
                visit_id,
                exc_info=True,
            )
        return result

    # ------------------------------------------------------------------ #
    # Consultas
    # ------------------------------------------------------------------ #
    def list_individuals(
        self, *, species_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Lista os indivíduos conhecidos, mais recentes primeiro."""
        limit = max(1, min(int(limit), 200))
        where = "WHERE i.species_id = ?" if species_id else ""
        params: list[Any] = [species_id] if species_id else []
        with db_session(self.db_path) as conn:
            params.append(limit)
            rows = conn.execute(
                f"""
                SELECT
                    i.*,
                    (
                        SELECT COUNT(*) FROM bird_embedding_samples s
                        WHERE s.individual_id = i.id
                    ) AS sightings,
                    (
                        SELECT AVG(s.similarity) FROM bird_embedding_samples s
                        WHERE s.individual_id = i.id AND s.similarity IS NOT NULL
                    ) AS avg_similarity,
                    (
                        SELECT s.visit_id FROM bird_embedding_samples s
                        WHERE s.individual_id = i.id
                        ORDER BY s.created_at DESC LIMIT 1
                    ) AS latest_visit_id
                FROM bird_individuals i
                {where}
                ORDER BY i.last_seen_at DESC, i.created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

            result: list[dict[str, Any]] = []
            ids = [str(row["id"]) for row in rows]
            recent_by_individual: dict[str, list[dict[str, Any]]] = {}
            if ids:
                placeholders = ",".join("?" for _ in ids)
                recent_rows = conn.execute(
                    f"""
                    SELECT s.individual_id, s.visit_id, s.similarity,
                           v.detected_at, v.confidence, v.thumbnail_path,
                           v.species, v.location_label
                    FROM bird_embedding_samples s
                    JOIN visits v ON v.id = s.visit_id
                    WHERE s.individual_id IN ({placeholders})
                    ORDER BY v.detected_at DESC
                    """,
                    ids,
                ).fetchall()
                for recent in recent_rows:
                    bucket = recent_by_individual.setdefault(
                        str(recent["individual_id"]), []
                    )
                    if len(bucket) >= 4:
                        continue
                    bucket.append(
                        {
                            "visit_id": recent["visit_id"],
                            "detected_at": recent["detected_at"],
                            "confidence": float(recent["confidence"] or 0.0),
                            "similarity": (
                                round(float(recent["similarity"]), 4)
                                if recent["similarity"] is not None
                                else None
                            ),
                            "crop_url": (
                                f"/api/visits/{recent['visit_id']}/crop"
                            ),
                            "location_label": recent["location_label"],
                        }
                    )

        for row in rows:
            individual_id = str(row["id"])
            latest_visit_id = row["latest_visit_id"]
            sightings = int(row["sightings"] or 0)
            result.append(
                {
                    "id": individual_id,
                    "species_id": row["species_id"],
                    "common_name": row["common_name"],
                    "scientific_name": row["scientific_name"],
                    "nickname": row["nickname"]
                    or f"Conhecido do Jardim • {row['common_name']}",
                    "sightings": sightings,
                    "is_recurring": sightings >= 2,
                    "first_seen_at": row["first_seen_at"],
                    "last_seen_at": row["last_seen_at"],
                    "representative_visit_id": row["representative_visit_id"],
                    "latest_visit_id": latest_visit_id,
                    "avg_similarity": (
                        round(float(row["avg_similarity"]), 4)
                        if row["avg_similarity"] is not None
                        else None
                    ),
                    "crop_url": (
                        f"/api/visits/{latest_visit_id}/crop"
                        if latest_visit_id
                        else None
                    ),
                    "recent_visits": recent_by_individual.get(individual_id, []),
                }
            )
        return result

    def individual_history(
        self, individual_id: str, *, limit: int = 60
    ) -> dict[str, Any] | None:
        """Histórico completo de um indivíduo (visitas + similaridade)."""
        limit = max(1, min(int(limit), 200))
        with db_session(self.db_path) as conn:
            individual = conn.execute(
                "SELECT * FROM bird_individuals WHERE id = ?", (individual_id,)
            ).fetchone()
            if individual is None:
                return None
            rows = conn.execute(
                """
                SELECT s.visit_id, s.similarity, s.created_at AS matched_at,
                       v.detected_at, v.confidence, v.thumbnail_path,
                       v.location_label, v.temperature, v.humidity,
                       v.weather_code
                FROM bird_embedding_samples s
                JOIN visits v ON v.id = s.visit_id
                WHERE s.individual_id = ?
                ORDER BY v.detected_at DESC
                LIMIT ?
                """,
                (individual_id, limit),
            ).fetchall()

        visits = [
            {
                "visit_id": row["visit_id"],
                "detected_at": row["detected_at"],
                "confidence": float(row["confidence"] or 0.0),
                "similarity": (
                    round(float(row["similarity"]), 4)
                    if row["similarity"] is not None
                    else None
                ),
                "crop_url": f"/api/visits/{row['visit_id']}/crop",
                "location_label": row["location_label"],
                "temperature": row["temperature"],
                "humidity": row["humidity"],
                "weather_code": row["weather_code"],
            }
            for row in rows
        ]
        return {
            "id": individual["id"],
            "species_id": individual["species_id"],
            "common_name": individual["common_name"],
            "scientific_name": individual["scientific_name"],
            "nickname": individual["nickname"],
            "sightings": int(individual["samples_count"] or len(visits)),
            "first_seen_at": individual["first_seen_at"],
            "last_seen_at": individual["last_seen_at"],
            "visits": visits,
        }

    def status(self) -> dict[str, Any]:
        """Contadores do recurso para o painel de Configurações."""
        with db_session(self.db_path) as conn:
            samples = conn.execute(
                "SELECT COUNT(*) AS total FROM bird_embedding_samples"
            ).fetchone()
            individuals = conn.execute(
                "SELECT COUNT(*) AS total FROM bird_individuals"
            ).fetchone()
            recurring = conn.execute(
                "SELECT COUNT(*) AS total FROM bird_individuals "
                "WHERE samples_count >= 2"
            ).fetchone()
        # Não força o carregamento do extrator (que pode baixar os pesos da
        # MobileNet): apenas informa o que já está ativo ou o padrão previsto.
        with self._lock:
            model_name = self._extractor_name or "auto (mobilenet_v3_small)"
        return {
            "enabled": bool(self.settings.visual_embeddings_enabled),
            "samples": int(samples["total"] or 0) if samples else 0,
            "individuals": int(individuals["total"] or 0) if individuals else 0,
            "recurring": int(recurring["total"] or 0) if recurring else 0,
            "model": model_name,
            "threshold": float(self.settings.individual_match_threshold),
        }


_service: VisualEmbeddingService | None = None
_service_lock = threading.Lock()


def get_visual_embeddings_service() -> VisualEmbeddingService:
    """Instância única (singleton) do serviço de assinaturas visuais."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = VisualEmbeddingService()
    return _service


__all__ = [
    "VisualEmbeddingService",
    "get_visual_embeddings_service",
    "image_sharpness",
]
