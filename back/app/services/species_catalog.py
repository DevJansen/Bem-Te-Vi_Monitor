"""Cadastro automático de espécies no Catálogo Local (Life List).

Reúne a lógica de "encontrar ou criar" uma espécie, usada quando a
identificação por IA externa (ex.: Google Gemini Vision) precisa preencher o
catálogo sem gerar duplicatas. A deduplicação compara o **nome científico**
(e, como reserva, o popular) ignorando maiúsculas/minúsculas e espaços extras.

Quando uma foto tratada da ave é informada, ela vira a **imagem de referência**
da nova espécie — assim o Álbum de Conquistas já nasce com a melhor foto
disponível, em alta definição.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.domain.avifauna_sul import classificar_status
from app.infra.database.repository import BirdSpeciesRepository

logger = logging.getLogger(__name__)


def _normalizar(texto: str | None) -> str:
    """Normaliza um nome para comparação (caixa, espaços e acentos triviais)."""
    return " ".join((texto or "").strip().casefold().split())


def _buscar_existente(
    repo: BirdSpeciesRepository, scientific_name: str, common_name: str
) -> dict | None:
    """Procura a espécie pelo nome científico e, em seguida, pelo popular."""
    alvo_cientifico = _normalizar(scientific_name)
    alvo_popular = _normalizar(common_name)
    for row in repo.list_all():
        if _normalizar(row.get("scientific_name")) == alvo_cientifico:
            return row
    for row in repo.list_all():
        if _normalizar(row.get("common_name")) == alvo_popular:
            return row
    return None


def _copiar_referencia(
    species_id: str, reference_image_source: Path | str | None
) -> str | None:
    """Copia a imagem tratada para ``reference_birds`` e devolve o caminho relativo.

    A foto de referência é o *melhor arquivo tratado* pelo Alaris Core (recorte
    ou thumbnail oficial). Falhas ao copiar não impedem o cadastro — apenas
    deixam a espécie sem foto de referência.
    """
    if reference_image_source is None:
        return None
    origem = Path(reference_image_source)
    if not origem.is_file():
        return None
    settings = get_settings()
    settings.ensure_directories()
    destino = settings.reference_birds_dir / f"{species_id}.jpg"
    try:
        shutil.copyfile(origem, destino)
    except OSError:
        logger.exception(
            "Falha ao copiar a imagem de referência da espécie %s", species_id
        )
        return None
    return f"reference_birds/{species_id}.jpg"


@dataclass(frozen=True)
class SpeciesMatch:
    """Resultado do *Smart Match* do Alaris Core.

    - ``created`` indica se a espécie é **nova** (novo card no Álbum de
      Conquistas) ou se já existia no catálogo (apenas incrementa o contador de
      visitas e associa a nova mídia à espécie existente).
    - ``reference_image_updated`` indica se a foto de referência foi definida ou
      enriquecida nesta chamada.
    """

    species: dict
    created: bool
    reference_image_updated: bool = False


def match_or_create_species(
    *,
    common_name: str,
    scientific_name: str,
    description: str = "",
    reference_image_source: Path | str | None = None,
) -> SpeciesMatch:
    """Compara a identificação com a Life List e devolve a espécie correspondente.

    Regra do **Alaris Core Smart Match**:

    - Se a espécie **já estiver cadastrada** (mesmo nome científico ou popular),
      devolve o card existente **sem duplicar** — o contador de visitas é
      derivado do vínculo da visita e a foto/vídeo passam a integrar a galeria
      daquela espécie. Se o card ainda não tinha foto de referência, ela é
      preenchida com a imagem tratada desta captura.
    - Se for **espécie nova**, cria o card estruturado no catálogo (Life List),
      já com o status ecológico regional e a melhor foto tratada disponível.
    """
    repo = BirdSpeciesRepository(get_settings().db_path)
    existente = _buscar_existente(repo, scientific_name, common_name)
    if existente is not None:
        updated = False
        # Enriquece a foto de referência apenas quando ela ainda não existe.
        if reference_image_source is not None and not existente.get(
            "reference_image_path"
        ):
            relative = _copiar_referencia(existente["id"], reference_image_source)
            if relative:
                refreshed = repo.set_reference_image(existente["id"], relative)
                if refreshed is not None:
                    existente = refreshed
                    updated = True
        return SpeciesMatch(
            species=existente, created=False, reference_image_updated=updated
        )

    species_id = str(uuid.uuid4())
    relative_path = _copiar_referencia(species_id, reference_image_source)
    created = repo.create(
        common_name=common_name.strip(),
        scientific_name=scientific_name.strip(),
        description=description.strip(),
        reference_image_path=relative_path,
        species_id=species_id,
        # Rótulo automático do status ecológico regional (avifauna do Sul).
        ecological_status=classificar_status(
            common_name=common_name, scientific_name=scientific_name
        ).value,
    )
    return SpeciesMatch(
        species=created,
        created=True,
        reference_image_updated=relative_path is not None,
    )


def find_or_create_species(
    *,
    common_name: str,
    scientific_name: str,
    description: str = "",
    reference_image_source: Path | str | None = None,
) -> dict:
    """Atalho de compatibilidade: devolve apenas a espécie (sem o ``created``)."""
    return match_or_create_species(
        common_name=common_name,
        scientific_name=scientific_name,
        description=description,
        reference_image_source=reference_image_source,
    ).species
