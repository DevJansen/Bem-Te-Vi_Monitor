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


def find_or_create_species(
    *,
    common_name: str,
    scientific_name: str,
    description: str = "",
    reference_image_source: Path | str | None = None,
) -> dict:
    """Devolve a espécie do catálogo, criando-a se ainda não existir.

    ``reference_image_source`` (opcional) é copiada para ``reference_birds`` e
    usada como foto de referência da nova espécie. Falhas ao copiar a imagem não
    impedem o cadastro — a espécie é criada mesmo assim.
    """
    repo = BirdSpeciesRepository(get_settings().db_path)
    existente = _buscar_existente(repo, scientific_name, common_name)
    if existente is not None:
        return existente

    settings = get_settings()
    settings.ensure_directories()
    species_id = str(uuid.uuid4())
    relative_path: str | None = None

    if reference_image_source is not None:
        origem = Path(reference_image_source)
        if origem.is_file():
            destino = settings.reference_birds_dir / f"{species_id}.jpg"
            try:
                shutil.copyfile(origem, destino)
                relative_path = f"reference_birds/{species_id}.jpg"
            except OSError:
                logger.exception(
                    "Falha ao copiar a imagem de referência da espécie %s", species_id
                )

    return repo.create(
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
