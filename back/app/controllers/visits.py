"""REST routes for bird visit events."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Path as FastAPIPath

from app.core.rate_limiter import limiter
from fastapi.responses import FileResponse

from app.ai.active_learning import (
    ActiveLearningError,
    get_active_learning_service,
)
from app.ai.visual_embeddings import get_visual_embeddings_service
from app.core.config import get_settings
from app.domain.avifauna_sul import info_especie
from app.domain.fauna_taxonomy import descrever_visitante
from app.domain.models import (
    SpeciesConsultOut,
    VisitConfirmationOut,
    VisitConfirmationRequest,
    VisitOut,
    VisitSpeciesAssignment,
)
from app.infra.database.repository import VisitRepository
from app.services.anomaly_log import registrar_retorno_especie
from app.services.external_species_identifier import (
    ExternalIdentificationError,
    consult_species_profile,
    identify_bird_image_file,
)
from app.services.species_catalog import EspecieNaoAveError, match_or_create_species

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/visits", tags=["visits"])

# Rótulos genéricos do detector que NÃO são um nome de espécie de verdade.
# A comparação é por texto literal em minúsculas; por isso listamos as variantes
# com e sem acento (a nomenclatura oficial exibida é "Pássaro Desconhecido").
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


def _repo() -> VisitRepository:
    return VisitRepository(get_settings().db_path)


def _alimentar_inteligencia_adaptativa(
    visit_id: str,
    *,
    species_name: str | None,
    species_id: str | None,
    source: str,
    wait_for_embedding: bool = True,
) -> dict[str, Any]:
    """Alimenta os módulos adaptativos após uma identificação/confirmação.

    Enfileira a amostra de treino (aprendizado ativo) e recalcula a assinatura
    visual (re-identificação individual). Falhas são absorvidas: a curadoria do
    usuário nunca quebra por causa de um módulo opcional.

    Com ``wait_for_embedding=False`` a extração (que pode carregar a MobileNet na
    primeira vez) roda em segundo plano, mantendo a resposta da API rápida.
    """
    resultado: dict[str, Any] = {
        "queued": False,
        "reason": None,
        "individual": None,
    }
    if species_name:
        try:
            amostra = get_active_learning_service().enqueue_visit(
                visit_id,
                species_name=species_name,
                species_id=species_id,
                source=source,
            )
            resultado["queued"] = amostra is not None
        except ActiveLearningError as exc:
            resultado["reason"] = str(exc)
        except Exception:
            logger.debug(
                "Falha ao enfileirar amostra de treino %s", visit_id, exc_info=True
            )

    def _registrar() -> dict[str, Any] | None:
        try:
            return get_visual_embeddings_service().register_visit(
                visit_id, common_name=species_name, force=True
            )
        except Exception:
            logger.debug(
                "Falha ao registrar a assinatura visual de %s",
                visit_id,
                exc_info=True,
            )
            return None

    if wait_for_embedding:
        resultado["individual"] = _registrar()
    else:
        threading.Thread(
            target=_registrar,
            name=f"visual-embedding-{visit_id[:8]}",
            daemon=True,
        ).start()
    return resultado


@router.put("/{visit_id}/assign-species", response_model=VisitOut)
def assign_visit_species(
    visit_id: str, payload: VisitSpeciesAssignment
) -> VisitOut:
    try:
        row = _repo().assign_species(visit_id, payload.species_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Espécie não encontrada.") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")
    # Log de anomalia: espécie reaparecendo após longo intervalo.
    if payload.species_id:
        nome = row.get("assigned_species_common_name") or row.get("species")
        if nome:
            registrar_retorno_especie(
                species=str(nome),
                scientific_name=row.get("assigned_species_scientific_name"),
                visit_id=visit_id,
                exclude_visit_id=visit_id,
            )
            # A confirmação manual do usuário é o sinal mais valioso de
            # aprendizado: vira amostra de treino e assinatura visual.
            _alimentar_inteligencia_adaptativa(
                visit_id,
                species_name=str(nome),
                species_id=payload.species_id,
                source="manual_assignment",
                wait_for_embedding=False,
            )
    return VisitRepository.to_out(row)


@router.post("/{visit_id}/confirm", response_model=VisitConfirmationOut)
def confirm_visit(
    visit_id: str, payload: VisitConfirmationRequest
) -> VisitConfirmationOut:
    """Confirma a espécie de uma detecção e alimenta o aprendizado ativo.

    Diferente do `assign-species` (que reescreve o rótulo), este endpoint
    registra a **confirmação** do usuário: a detecção atual passa a ser uma
    amostra rotulada de alta qualidade para o fine-tuning do Bem-Ti-Vi Core e
    também recebe a assinatura visual para a re-identificação individual.
    """
    repository = _repo()
    row = repository.get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")

    species_id = payload.species_id
    species_name = payload.species_name

    # Resolve o nome a partir do catálogo quando só o id foi informado.
    if species_id and not species_name:
        try:
            from app.infra.database.repository import BirdSpeciesRepository

            especie = BirdSpeciesRepository(get_settings().db_path).get(species_id)
        except Exception:
            especie = None
        if especie is not None:
            species_name = especie.get("common_name") or especie.get("name")
    if not species_name:
        species_name = row.get("assigned_species_common_name") or row.get("species")

    resultado = _alimentar_inteligencia_adaptativa(
        visit_id,
        species_name=str(species_name) if species_name else None,
        species_id=species_id,
        source="user_confirmation",
    )

    individual = resultado.get("individual") or {}
    return VisitConfirmationOut(
        visit_id=visit_id,
        confirmed=bool(species_name),
        species_name=str(species_name) if species_name else None,
        species_id=species_id,
        training_queued=bool(resultado.get("queued")),
        training_reason=resultado.get("reason"),
        individual_id=individual.get("individual_id"),
        individual_nickname=individual.get("nickname"),
        individual_known=bool(individual.get("known")),
    )


@router.get("", response_model=list[VisitOut])
async def list_visits(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    camera_id: str | None = None,
    species: str | None = None,
    visitor_kind: str | None = Query(
        default=None,
        description=(
            "Filtra por natureza do visitante: 'bird' (aves), 'mammal'/'other' "
            "(um grupo exato) ou 'special' (qualquer Visitante Especial)."
        ),
    ),
) -> list[VisitOut]:
    try:
        rows = _repo().list(
            limit=limit,
            offset=offset,
            camera_id=camera_id,
            species=species,
            visitor_kind=visitor_kind,
        )
        return [VisitRepository.to_out(r) for r in rows]
    except Exception as exc:
        logger.exception("list_visits failed")
        raise HTTPException(status_code=500, detail="Failed to list visits") from exc


@router.get("/day/{day}", response_model=list[VisitOut])
async def list_visits_by_day(
    day: str = FastAPIPath(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(default=50, ge=1, le=200),
    visitor_kind: str | None = None,
) -> list[VisitOut]:
    """Visitas de um dia específico (``YYYY-MM-DD``) para o Reel do Resumo do Dia."""
    try:
        rows = _repo().list_by_day(day, limit=limit, visitor_kind=visitor_kind)
        return [VisitRepository.to_out(r) for r in rows]
    except Exception as exc:
        logger.exception("list_visits_by_day failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível listar as visitas do dia.",
        ) from exc


@router.get("/today", response_model=list[VisitOut])
async def list_today_visits(
    limit: int = Query(default=50, ge=1, le=200),
    visitor_kind: str | None = Query(
        default=None,
        description=(
            "Filtra as visitas de hoje: 'bird' (só aves) ou 'special' "
            "(só Visitantes Especiais, ex.: esquilos)."
        ),
    ),
    camera_id: str | None = Query(
        default=None,
        description="Restringe a um jardim específico (camera_id).",
    ),
) -> list[VisitOut]:
    """Visitas de hoje (mais recentes primeiro), com a miniatura do YOLOv8."""
    try:
        rows = _repo().list_today(
            limit=limit, visitor_kind=visitor_kind, camera_id=camera_id
        )
        return [VisitRepository.to_out(r) for r in rows]
    except Exception as exc:
        logger.exception("list_today_visits failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível listar as visitas de hoje.",
        ) from exc


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(visit_id: str) -> VisitOut:
    row = _repo().get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    return VisitRepository.to_out(row)


@router.get("/{visit_id}/crop")
async def get_visit_crop(visit_id: str) -> FileResponse:
    """Serve o recorte ampliado da ave de uma visita.

    O caminho é reconstruído a partir do ``visit_id`` e validado contra a pasta
    de recortes (``app-data/crops``), impedindo qualquer acesso fora dela
    (proteção contra *path traversal*).
    """
    row = _repo().get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")

    crop_relative: str | None = None
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
        if isinstance(metadata, dict):
            crop_relative = metadata.get("crop_path")
    except (TypeError, ValueError):
        crop_relative = None

    expected = Path("crops") / f"{visit_id}.jpg"
    if crop_relative != expected.as_posix():
        raise HTTPException(status_code=404, detail="Recorte não disponível.")

    settings = get_settings()
    crop_path = (settings.app_data_dir / expected).resolve()
    if crop_path.parent != settings.crops_dir.resolve() or not crop_path.is_file():
        raise HTTPException(status_code=404, detail="Recorte não disponível.")

    return FileResponse(crop_path, media_type="image/jpeg")


def _resolve_visit_image(row: dict) -> tuple[Path, str] | None:
    """Escolhe a melhor imagem tratada disponível para a identificação externa.

    Prefere o **recorte da ave** (close-up, já passou pelo enhancement) e, na
    falta, a **thumbnail oficial** em alta definição. Os caminhos são validados
    contra as pastas de mídia (proteção contra *path traversal*). Devolve o
    caminho e um rótulo da origem (``recorte`` ou ``thumbnail``).
    """
    settings = get_settings()
    visit_id = row["id"]

    crops_dir = settings.crops_dir.resolve()
    crop_path = (settings.crops_dir / f"{visit_id}.jpg").resolve()
    if crop_path.parent == crops_dir and crop_path.is_file():
        return crop_path, "recorte"

    thumb_relative = row.get("thumbnail_path")
    if thumb_relative:
        candidate = (settings.captures_dir / thumb_relative).resolve()
        thumbs_dir = settings.thumbs_dir.resolve()
        try:
            candidate.relative_to(thumbs_dir)
        except ValueError:
            return None
        if candidate.is_file():
            return candidate, "thumbnail"
    return None


@router.post("/{visit_id}/identify-external", response_model=VisitOut)
@limiter.limit("5/minute")
def identify_visit_external(
    request: Request,
    visit_id: str,
    add_to_catalog: bool = Query(
        default=False,
        description="Cadastra a espécie no Catálogo Local e associa a visita.",
    ),
) -> VisitOut:
    """Identifica a espécie com a IA externa a partir da imagem **tratada**.

    Usa preferencialmente o recorte tratado da ave (ou a thumbnail oficial em
    alta definição) gerados pelo pipeline de gravação. Com ``add_to_catalog``,
    a espécie identificada é cadastrada no Catálogo Local (Life List) e
    associada automaticamente à visita.
    """
    repository = _repo()
    row = repository.get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visit not found")

    visit = VisitRepository.to_out(row)
    if visit.metadata.get("identification_status") == "Identificado por IA Externa":
        return visit

    settings = get_settings()
    if not settings.ai_external_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Configure a chave GEMINI_API_KEY (Configurações › "
                "Inteligência Artificial) para habilitar a identificação externa"
            ),
        )

    resolved = _resolve_visit_image(row)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail="A imagem tratada desta visita não está disponível para identificação",
        )
    image_path, image_source = resolved

    try:
        identification = identify_bird_image_file(image_path)
    except ExternalIdentificationError as exc:
        logger.warning("External identification failed visit=%s: %s", visit_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    species = f"{identification.common_name} ({identification.scientific_name})"

    # Taxonomia do Alaris Core (o "anti-esquilo"): decide se é ave ou Visitante
    # Especial. Esquilos/gatos NÃO entram na Life List nem geram anomalia de ave.
    visitante = descrever_visitante(
        identification.common_name, identification.scientific_name
    )

    # Cadastro automático no Catálogo Local / Life List (apenas para aves). A
    # imagem tratada vira a foto de referência da espécie, quando nova.
    catalog_species_id: str | None = None
    if add_to_catalog and visitante.eh_ave:
        try:
            # Alaris Core Smart Match: se a espécie já está na Life List, o card
            # existente é reaproveitado (sem duplicar); se é nova, nasce um card
            # estruturado no Álbum de Conquistas com a foto tratada.
            match = match_or_create_species(
                common_name=identification.common_name,
                scientific_name=identification.scientific_name,
                reference_image_source=image_path,
            )
            catalog_species_id = str(match.species["id"])
        except EspecieNaoAveError:
            logger.info(
                "Visitante Especial identificado (não-ave) visit=%s: %s",
                visit_id,
                identification.common_name,
            )
        except Exception:
            logger.exception(
                "Falha ao cadastrar a espécie no catálogo visit=%s", visit_id
            )

    updated = repository.update_external_identification(
        visit_id,
        species=species,
        scientific_name=identification.scientific_name,
        common_name=identification.common_name,
        species_id=catalog_species_id,
        image_source=image_source,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    # Log de anomalia (retorno de espécie após longo intervalo): só faz sentido
    # para aves — um esquilo que reaparece não é uma "anomalia ornitológica".
    if visitante.eh_ave:
        registrar_retorno_especie(
            species=identification.common_name,
            scientific_name=identification.scientific_name,
            visit_id=visit_id,
            exclude_visit_id=visit_id,
        )
        # A identificação externa de alta confiança também realimenta o Core:
        # vira amostra de treino e assinatura visual para o indivíduo.
        _alimentar_inteligencia_adaptativa(
            visit_id,
            species_name=identification.common_name,
            species_id=catalog_species_id,
            source="external_identification",
            wait_for_embedding=False,
        )
    return VisitRepository.to_out(updated)


def _resolver_nomes_ia(visit: VisitOut) -> tuple[str, str]:
    """Resolve o nome popular e o científico da visita para a consulta à IA.

    Prioriza a espécie associada no catálogo, depois a identificação externa e,
    por fim, a análise da IA — sempre ignorando os rótulos genéricos do detector
    (ex.: ``bird``), que não são um nome de espécie de verdade.
    """
    meta = visit.metadata or {}
    external = meta.get("external_identification")
    analysis = meta.get("ai_analysis")
    external = external if isinstance(external, dict) else {}
    analysis = analysis if isinstance(analysis, dict) else {}

    candidatos_popular = (
        visit.assigned_species_common_name,
        external.get("common_name"),
        analysis.get("species"),
        # Rótulo cru da visita: cobre identificações feitas por outros caminhos
        # (ex.: associação manual no catálogo) que não deixam metadados de IA.
        visit.species,
    )
    candidatos_cientifico = (
        visit.assigned_species_scientific_name,
        external.get("scientific_name"),
        analysis.get("scientific_name"),
    )

    def _primeiro_valido(candidatos: tuple[object, ...]) -> str:
        for candidato in candidatos:
            if isinstance(candidato, str):
                limpo = candidato.strip()
                if limpo and limpo.casefold() not in _GENERIC_SPECIES:
                    return limpo
        return ""

    popular = _primeiro_valido(candidatos_popular)
    cientifico = _primeiro_valido(candidatos_cientifico)
    # Sem nome científico informado, tenta a base regional (avifauna do Sul).
    if popular and not cientifico:
        info = info_especie(common_name=popular)
        if info is not None:
            cientifico = info.scientific_name
    return popular, cientifico


@router.post("/{visit_id}/ask-ai", response_model=SpeciesConsultOut)
def ask_ai_about_visit(
    visit_id: str,
    refresh: bool = Query(
        default=False,
        description="Ignora a ficha em cache e consulta a IA externa novamente.",
    ),
) -> SpeciesConsultOut:
    """Consulta detalhada da espécie na IA externa (Google Gemini / compatível).

    Estrutura um *prompt* ornitológico rico (nome científico, família, status de
    conservação, comportamento alimentar, habitat, curiosidades e dados
    biogeográficos) e devolve a ficha formatada. O resultado fica em cache nos
    metadados da visita; use ``refresh=true`` para forçar uma nova consulta.
    """
    repository = _repo()
    row = repository.get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visit not found")

    visit = VisitRepository.to_out(row)

    # Cache local: evita gastar chamadas de IA repetindo a mesma consulta.
    if not refresh:
        cached = visit.metadata.get("ai_consult")
        if isinstance(cached, dict) and cached.get("common_name"):
            return SpeciesConsultOut(**{**cached, "cached": True})

    settings = get_settings()
    if not settings.ai_external_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Configure a chave GEMINI_API_KEY (Configurações › "
                "Inteligência Artificial) para habilitar a consulta externa"
            ),
        )

    popular, cientifico = _resolver_nomes_ia(visit)
    if not popular and not cientifico:
        raise HTTPException(
            status_code=422,
            detail=(
                "Identifique a espécie desta visita antes de pedir a ficha "
                "ornitológica à IA externa."
            ),
        )

    # Envia a imagem tratada (recorte/thumbnail) para enriquecer a resposta.
    image_bytes: bytes | None = None
    image_source: str | None = None
    resolved = _resolve_visit_image(row)
    if resolved is not None:
        image_path, image_source = resolved
        try:
            image_bytes = image_path.read_bytes()
        except OSError:
            logger.debug(
                "Imagem tratada ilegível para a consulta visit=%s", visit_id
            )
            image_bytes = None
            image_source = None

    try:
        consult = consult_species_profile(
            common_name=popular,
            scientific_name=cientifico,
            image_bytes=image_bytes,
        )
    except ExternalIdentificationError as exc:
        logger.warning("Consulta externa falhou visit=%s: %s", visit_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload: dict[str, object] = {
        **consult.as_dict(),
        "provider": consult.provider,
        "model": consult.model,
        "image_source": image_source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }
    repository.update_metadata(visit_id, {"ai_consult": payload})
    return SpeciesConsultOut(**payload)
