"""Associação automática de espécie por similaridade visual (Bem-Te-Vi Core).

O detector do YOLO responde apenas ``bird`` para a maioria das capturas — o
rótulo genérico não diz **qual** ave pousou no comedouro. Este módulo fecha essa
lacuna comparando a assinatura visual (embedding) do recorte tratado com as
fotos de referência do Catálogo Local ("Minhas Aves"):

1. O recorte da visita é convertido em um vetor normalizado (MobileNetV3-Small
   ou descritor OpenCV de fallback — o mesmo extrator da re-identificação
   individual, em :mod:`app.ai.visual_embeddings`).
2. O vetor é comparado, por **similaridade de cosseno**, com o embedding de
   cada ``bird_species.reference_image_path``.
3. Se o melhor escore for maior ou igual a
   :attr:`Settings.species_match_threshold` (padrão **65%**), a visita recebe o
   nome popular da espécie, o vínculo com o catálogo e o selo
   ``Identificado pelo Bem-Te-Vi Core``.

Princípios de projeto:

* **Cache inteligente** — as fotos de referência são lidas uma única vez e
  mantidas em memória. O cache é invalidado automaticamente quando o catálogo
  muda (nova espécie, troca de foto ou remoção), pela assinatura
  ``(id, caminho, mtime)``.
* **Nunca sobrescreve curadoria humana** — visitas confirmadas, identificadas
  pela IA externa ou já associadas manualmente são preservadas.
* **Degradação graciosa** — sem imagem nítida, sem catálogo ou sem ``torch`` o
  módulo simplesmente não associa; jamais interrompe a captura.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.ai.visit_media import resolve_visit_image
from app.ai.visual_embeddings import (
    VisualEmbeddingService,
    get_visual_embeddings_service,
    image_sharpness,
    is_generic_species,
    read_image_bgr,
)
from app.core.config import Settings, get_settings
from app.domain.avifauna_sul import descrever
from app.infra.database.repository import BirdSpeciesRepository, VisitRepository

logger = logging.getLogger(__name__)

# Status que representam uma decisão humana/definitiva: a auto-associação não
# deve mexer neles, mesmo que o embedding aponte para outra espécie.
_PROTECTED_STATUSES = {
    "Espécie Confirmada",
    "Confirmado pelo usuário",
    "Identificado por IA Externa",
    "Reclassificado pelo usuário",
    "Visitante Especial",
    # Rótulo gravado antes do rebranding (motor "Alaris Core") — visitas antigas
    # continuam protegidas para não perder a associação já aceita.
    "Identificado pelo Alaris Core",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_metadata(row: dict[str, Any]) -> dict[str, Any]:
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return metadata if isinstance(metadata, dict) else {}


@dataclass(frozen=True)
class SpeciesCandidate:
    """Candidata devolvida pela comparação visual.

    ``accepted`` indica se o escore atingiu o limiar configurado. Mesmo quando
    ``False``, o objeto é útil para telemetria/log (sabemos qual espécie chegou
    mais perto e com qual similaridade).
    """

    species_id: str
    common_name: str
    scientific_name: str | None
    score: float
    model: str
    reference_path: str | None
    accepted: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "species_id": self.species_id,
            "common_name": self.common_name,
            "scientific_name": self.scientific_name,
            "score": round(float(self.score), 4),
            "model": self.model,
            "reference_path": self.reference_path,
            "accepted": bool(self.accepted),
        }


@dataclass(frozen=True)
class _Reference:
    """Embedding de uma foto de referência do catálogo."""

    species_id: str
    common_name: str
    scientific_name: str | None
    reference_path: str
    vector: np.ndarray


class SpeciesAssociationService:
    """Compara capturas com as fotos de referência do Catálogo Local."""

    def __init__(
        self,
        settings: Settings | None = None,
        embeddings: VisualEmbeddingService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.db_path
        self._embeddings = embeddings or get_visual_embeddings_service()
        self._lock = threading.Lock()
        self._references: list[_Reference] = []
        self._cache_signature: tuple[tuple[str, str, int, str], ...] | None = None
        self._model_name = ""

    # ------------------------------------------------------------------ #
    # Cache de referências
    # ------------------------------------------------------------------ #
    def _signature(
        self, rows: list[dict[str, Any]]
    ) -> tuple[tuple[str, str, int, str], ...]:
        """Assinatura barata do catálogo para invalidar o cache.

        Inclui o caminho e o ``mtime`` da foto: substituir a imagem de referência
        por uma foto melhor força o recálculo do embedding sem reiniciar a API.
        """
        items: list[tuple[str, str, int, str]] = []
        for row in rows:
            reference = row.get("reference_image_path")
            if not reference:
                continue
            path = self.settings.reference_birds_dir / Path(str(reference)).name
            try:
                mtime = int(path.stat().st_mtime_ns)
            except OSError:
                mtime = 0
            items.append(
                (
                    str(row.get("id") or ""),
                    str(reference),
                    mtime,
                    str(row.get("common_name") or ""),
                )
            )
        return tuple(sorted(items))

    def invalidate_cache(self) -> None:
        """Limpa o cache (chamado quando o catálogo muda por fora)."""
        with self._lock:
            self._references = []
            self._cache_signature = None

    def _load_references(self) -> list[_Reference]:
        """Carrega (ou reaproveita) os embeddings das fotos de referência."""
        repository = BirdSpeciesRepository(self.db_path)
        try:
            rows = repository.list_all()
        except Exception:
            logger.exception("Falha ao listar o Catálogo Local para associação")
            return []

        signature = self._signature(rows)
        # O lock cobre a carga inteira: duas visitas simultâneas não repetem o
        # trabalho pesado de extrair os embeddings das referências.
        with self._lock:
            if signature == self._cache_signature:
                return self._references

            limit = int(self.settings.species_match_max_references)
            references: list[_Reference] = []
            for row in rows[:limit]:
                relative = row.get("reference_image_path")
                if not relative:
                    continue
                path = self.settings.reference_birds_dir / Path(str(relative)).name
                if not path.is_file():
                    continue
                image = read_image_bgr(path)
                if image is None:
                    logger.debug("Foto de referência ilegível: %s", path)
                    continue
                vector, model = self._embeddings.extract_embedding(image)
                if vector is None:
                    continue
                references.append(
                    _Reference(
                        species_id=str(row["id"]),
                        common_name=str(row.get("common_name") or ""),
                        scientific_name=row.get("scientific_name"),
                        reference_path=str(relative),
                        vector=vector,
                    )
                )
                self._model_name = model or self._model_name

            self._references = references
            self._cache_signature = signature
            logger.info(
                "Associação de espécie: %d referência(s) visual(is) carregada(s)%s.",
                len(references),
                f" com {self._model_name}" if self._model_name else "",
            )
            return references

    # ------------------------------------------------------------------ #
    # Comparação
    # ------------------------------------------------------------------ #
    def _best_candidate(self, image: np.ndarray) -> SpeciesCandidate | None:
        """Melhor correspondência para uma imagem BGR (aceita ou não)."""
        if not self.settings.species_auto_association_enabled:
            return None
        if image is None or image.size == 0:
            return None

        sharpness = image_sharpness(image)
        if (
            sharpness is not None
            and sharpness < float(self.settings.species_match_min_sharpness)
        ):
            logger.debug(
                "Associação ignorada: nitidez %.1f abaixo do mínimo %.1f",
                sharpness,
                self.settings.species_match_min_sharpness,
            )
            return None

        embedding, model = self._embeddings.extract_embedding(image)
        if embedding is None:
            return None

        references = self._load_references()
        if not references:
            return None

        threshold = float(self.settings.species_match_threshold)
        best: _Reference | None = None
        best_score = -1.0
        for reference in references:
            # Vetores já vêm normalizados (L2), então o produto escalar é a
            # similaridade de cosseno — sem divisões extras no laço quente.
            if reference.vector.size != embedding.size:
                continue
            score = float(np.dot(reference.vector, embedding))
            if score > best_score:
                best_score = score
                best = reference

        if best is None:
            return None
        return SpeciesCandidate(
            species_id=best.species_id,
            common_name=best.common_name,
            scientific_name=best.scientific_name,
            score=best_score,
            model=model or self._model_name,
            reference_path=best.reference_path,
            accepted=best_score >= threshold,
        )

    def identify_image(self, image: np.ndarray) -> SpeciesCandidate | None:
        """Associa uma imagem BGR à espécie mais próxima do catálogo."""
        try:
            return self._best_candidate(image)
        except Exception:
            logger.exception("Falha na associação visual de espécie")
            return None

    def identify_path(self, path: Path | str) -> SpeciesCandidate | None:
        """Atalho para :meth:`identify_image` a partir de um arquivo."""
        image = read_image_bgr(Path(path))
        if image is None:
            return None
        return self.identify_image(image)

    # ------------------------------------------------------------------ #
    # Aplicação na visita
    # ------------------------------------------------------------------ #
    def _can_associate(
        self, row: dict[str, Any], allow_overwrite: bool
    ) -> tuple[bool, str]:
        """Decide se a visita pode receber a associação automática."""
        if not self.settings.species_auto_association_enabled:
            return False, "auto_associacao_desabilitada"
        if (row.get("visitor_kind") or "bird") != "bird":
            return False, "visitante_especial"
        metadata = _read_metadata(row)
        status = metadata.get("identification_status")
        if isinstance(status, str) and status in _PROTECTED_STATUSES:
            return False, "curadoria_humana"
        if not allow_overwrite:
            if row.get("species_id"):
                return False, "ja_associada"
            if not is_generic_species(row.get("species")):
                return False, "especie_ja_identificada"
        return True, "elegivel"

    def associate_visit(
        self,
        visit_id: str,
        *,
        image_path: Path | str | None = None,
        allow_overwrite: bool = False,
    ) -> dict[str, Any]:
        """Auto-associa a espécie de uma visita já persistida.

        Devolve um dicionário sempre serializável:

        - ``applied``: a visita recebeu (ou já tinha) a associação visual;
        - ``reason``: motivo quando não foi possível;
        - ``score``/``species``: melhor candidata encontrada.

        A função nunca levanta exceção: associação visual é um recurso
        opcional e não pode derrubar a captura.
        """
        result: dict[str, Any] = {
            "visit_id": visit_id,
            "applied": False,
            "reason": None,
            "score": None,
            "threshold": float(self.settings.species_match_threshold),
            "species": None,
        }
        try:
            repository = VisitRepository(self.db_path)
            row = repository.get(visit_id)
            if row is None:
                result["reason"] = "visita_nao_encontrada"
                return result

            allowed, reason = self._can_associate(row, allow_overwrite)
            if not allowed:
                result["reason"] = reason
                return result

            path = Path(image_path) if image_path else resolve_visit_image(
                row, self.settings
            )
            if path is None or not path.is_file():
                result["reason"] = "imagem_indisponivel"
                return result

            candidate = self.identify_path(path)
            if candidate is None:
                result["reason"] = "sem_referencias_ou_baixa_nitidez"
                return result

            result["score"] = round(float(candidate.score), 4)
            result["species"] = candidate.as_dict()
            if not candidate.accepted or not candidate.common_name:
                result["reason"] = "abaixo_do_limiar"
                return result

            updated = repository.assign_species(visit_id, candidate.species_id)
            if updated is None:
                result["reason"] = "falha_ao_associar"
                return result

            # Status ecológico regional coerente com a espécie encontrada.
            ecological: dict[str, Any] | None = None
            try:
                ecological = descrever(
                    common_name=candidate.common_name,
                    scientific_name=candidate.scientific_name,
                )
            except Exception:
                logger.debug(
                    "Falha ao descrever o status ecológico de %s",
                    candidate.common_name,
                    exc_info=True,
                )

            metadata: dict[str, Any] = {
                "auto_association": {
                    **candidate.as_dict(),
                    "applied": True,
                    "threshold": float(self.settings.species_match_threshold),
                    "identified_at": _utc_now(),
                    "image_path": str(path),
                },
                "identification_status": "Identificado pelo Bem-Te-Vi Core",
            }
            if ecological is not None:
                metadata["ecological"] = ecological
            repository.update_metadata(visit_id, metadata)

            result["applied"] = True
            result["reason"] = "associada"
            result["species"] = candidate.as_dict()
            logger.info(
                "Auto-associação: visita %s → %s (similaridade %.1f%%)",
                visit_id,
                candidate.common_name,
                candidate.score * 100,
            )
            return result
        except Exception:
            logger.exception("Falha ao auto-associar a visita %s", visit_id)
            result["reason"] = "erro_interno"
            return result


_service_lock = threading.Lock()
_service: SpeciesAssociationService | None = None


def get_species_association_service() -> SpeciesAssociationService:
    """Instância única (thread-safe) do serviço de associação de espécie."""
    global _service
    with _service_lock:
        if _service is None:
            _service = SpeciesAssociationService()
        return _service


def invalidate_species_association_cache() -> None:
    """Invalida o cache de referências após mudanças no Catálogo Local."""
    global _service
    with _service_lock:
        service = _service
    if service is not None:
        service.invalidate_cache()
