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
from app.ai.fine_tuning import save_correction_sample
from app.ai.species_association import get_species_association_service
from app.ai.visit_media import resolve_visit_image_with_source
from app.ai.visual_embeddings import get_visual_embeddings_service
from app.core.config import get_settings
from app.domain.avifauna_sul import info_especie
from app.domain.fauna_taxonomy import descrever_visitante
from app.domain.models import (
    SpeciesConsultOut,
    VisitConfirmationOut,
    VisitConfirmationRequest,
    VisitOut,
    VisitReclassificationRequest,
    VisitSpeciesAssignment,
)
from app.domain.species_labels import is_generic_species
from app.infra.database.repository import VisitRepository
from app.services.anomaly_log import registrar_retorno_especie
from app.services.external_species_identifier import (
    ExternalIdentificationError,
    consult_species_profile,
    identify_bird_image_file,
)
from app.services.hd_crop import export_hd_crop, friendly_crop_filename
from app.services.species_catalog import EspecieNaoAveError, match_or_create_species

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/visits", tags=["visits"])


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
    """Associa (ou desassocia) uma visita a uma espécie do Catálogo Local.

    A associação manual é um ato de curadoria: a visita passa a exibir o selo
    **“Espécie Confirmada”** no painel e fica protegida contra sobrescritas da
    auto-associação visual.
    """
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
            # Selo de curadoria: a ave ganhou uma espécie real no catálogo.
            row = (
                _repo().update_metadata(
                    visit_id,
                    {
                        "identification_status": "Espécie Confirmada",
                        "assigned_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                or row
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


@router.post("/{visit_id}/reclassify", response_model=VisitOut)
def reclassify_visit(
    visit_id: str, payload: VisitReclassificationRequest
) -> VisitOut:
    """Corrige uma associação de espécie e ensina o Bem-Te-Vi Core.

    Fluxo (o mesmo do botão **“Associação Incorreta / Reclassificar”**):

    1. aplica a espécie correta à visita (o rótulo ``species`` também passa a
       exibir o nome do catálogo);
    2. grava o recorte tratado em ``app-data/fine_tuning/{espécie}/`` com a
       proveniência no ``index.jsonl`` (material local de retreinamento);
    3. enfileira a amostra no aprendizado ativo e recalcula a assinatura visual
       do indivíduo em segundo plano;
    4. registra o retorno da espécie no log de anomalias.
    """
    repository = _repo()
    previous = repository.get(visit_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")

    try:
        row = repository.assign_species(visit_id, payload.species_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Espécie não encontrada.") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")

    nome = row.get("assigned_species_common_name") or row.get("species")
    if not nome:
        raise HTTPException(
            status_code=422,
            detail="A espécie informada não possui nome popular no catálogo.",
        )
    nome = str(nome)
    anterior = (
        previous.get("assigned_species_common_name")
        or previous.get("species")
        or ""
    )

    # Selo de curadoria: a auto-associação não sobrescreve mais esta visita.
    updated = repository.update_metadata(
        visit_id,
        {
            "identification_status": "Reclassificado pelo usuário",
            "manual_reclassification": {
                "previous_species": str(anterior),
                "species_id": payload.species_id,
                "species_name": nome,
                "notes": (payload.notes or "").strip() or None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        },
    ) or row

    amostra = save_correction_sample(
        visit_id,
        species_name=nome,
        species_id=payload.species_id,
        source="manual_reclassification",
        notes=payload.notes,
    )
    if not amostra.get("saved"):
        logger.warning(
            "Reclassificação de %s não gerou amostra local de fine-tuning (%s)",
            visit_id,
            amostra.get("reason"),
        )

    registrar_retorno_especie(
        species=nome,
        scientific_name=row.get("assigned_species_scientific_name"),
        visit_id=visit_id,
        exclude_visit_id=visit_id,
    )
    _alimentar_inteligencia_adaptativa(
        visit_id,
        species_name=nome,
        species_id=payload.species_id,
        source="manual_reclassification",
        wait_for_embedding=False,
    )
    logger.info(
        "Visita %s reclassificada: '%s' → '%s' (amostra=%s)",
        visit_id,
        anterior,
        nome,
        amostra.get("path") or "não salva",
    )
    return VisitRepository.to_out(updated)


@router.post("/{visit_id}/auto-identify", response_model=VisitOut)
def auto_identify_visit(visit_id: str) -> VisitOut:
    """Reexecuta a auto-associação visual de uma visita sob demanda.

    Útil quando o catálogo ganhou novas fotos de referência depois da captura.
    A curadoria humana (confirmação, IA externa ou reclassificação) é sempre
    preservada — o serviço devolve a visita sem alterações nesses casos.
    """
    repository = _repo()
    row = repository.get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")

    resultado = get_species_association_service().associate_visit(visit_id)
    if not resultado.get("applied"):
        logger.info(
            "Auto-associação manual sem alteração em %s: %s",
            visit_id,
            resultado.get("reason"),
        )
    refreshed = repository.get(visit_id) or row
    return VisitRepository.to_out(refreshed)


@router.post("/{visit_id}/confirm", response_model=VisitConfirmationOut)
def confirm_visit(
    visit_id: str, payload: VisitConfirmationRequest
) -> VisitConfirmationOut:
    """Confirma a espécie de uma detecção e alimenta o aprendizado ativo.

    Diferente do `assign-species` (que reescreve o rótulo), este endpoint
    registra a **confirmação** do usuário: a detecção atual passa a ser uma
    amostra rotulada de alta qualidade para o fine-tuning do Bem-Te-Vi Core e
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

    # Selo de curadoria: a confirmação do observador é a evidência mais forte
    # que temos. A visita passa a exibir "Espécie Confirmada" no painel e fica
    # protegida contra sobrescritas da auto-associação visual.
    if species_name and not is_generic_species(species_name):
        repository.update_metadata(
            visit_id,
            {
                "identification_status": "Espécie Confirmada",
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

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


@router.get("/{visit_id}/crop/hd")
async def download_visit_crop_hd(visit_id: str) -> FileResponse:
    """Baixa o **recorte HD** da ave (JPEG otimizado em alta resolução).

    Diferente de ``GET /{visit_id}/crop`` (que serve o recorte exibido no
    painel), esta rota força a geração de uma versão ampliada e realçada do
    close-up — pronta para compartilhar, imprimir ou usar como material de
    retreinamento. O arquivo é devolvido como anexo (``Content-Disposition``),
    com nome amigável carregando a espécie e a data da visita.
    """
    row = _repo().get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")

    crop_path = export_hd_crop(visit_id)
    if crop_path is None or not crop_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Recorte em alta definição não disponível para esta visita.",
        )

    especie = (
        row.get("assigned_species_common_name")
        or row.get("species")
        or "ave"
    )
    filename = friendly_crop_filename(str(especie), visit_id)
    return FileResponse(
        crop_path,
        media_type="image/jpeg",
        filename=filename,
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _resolve_visit_image(row: dict) -> tuple[Path, str] | None:
    """Escolhe a melhor imagem tratada disponível para a identificação externa.

    Prefere o **recorte da ave** (close-up, já passou pelo enhancement) e, na
    falta, a **thumbnail oficial** em alta definição. Os caminhos são validados
    contra as pastas de mídia (proteção contra *path traversal*) pelo
    resolvedor compartilhado :mod:`app.ai.visit_media`. Devolve o caminho e um
    rótulo da origem (``recorte`` ou ``thumbnail``).
    """
    return resolve_visit_image_with_source(row)


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

    # Taxonomia do Bem-Te-Vi Core (o "anti-esquilo"): decide se é ave ou Visitante
    # Especial. Esquilos/gatos NÃO entram na Life List nem geram anomalia de ave.
    visitante = descrever_visitante(
        identification.common_name, identification.scientific_name
    )

    # Cadastro automático no Catálogo Local / Life List (apenas para aves). A
    # imagem tratada vira a foto de referência da espécie, quando nova.
    catalog_species_id: str | None = None
    if add_to_catalog and visitante.eh_ave:
        try:
            # Bem-Te-Vi Core Smart Match: se a espécie já está na Life List, o card
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
                if limpo and not is_generic_species(limpo):
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
