"""Testes do pacote de identificação visual do Bem-Te-Vi Core.

Cobre os quatro pilares do refactor:

1. **Auto-associação de espécie** (re-ID visual contra o Catálogo Local);
2. **Reclassificação** com gravação da amostra em ``data/fine_tuning``;
3. **Exportação do recorte HD**;
4. **Renderização das caixas/selos** (cores por status e rótulo dinâmico).

Os testes rodam com um extrator de embeddings **falso** (determinístico e sem
torch), garantindo execução rápida e offline.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.fine_tuning import fine_tuning_stats, save_correction_sample
from app.ai.species_association import SpeciesAssociationService
from app.ai.visit_media import resolve_visit_image
from app.core.config import Settings
from app.infra.ai.annotate import (
    CONFIRMED_BGR,
    PENDING_BGR,
    draw_bird_detections,
)
from app.infra.database.migrations import apply_migrations
from app.infra.database.repository import BirdSpeciesRepository, VisitRepository
from app.services.hd_crop import export_hd_crop, friendly_crop_filename

# --------------------------------------------------------------------------- #
# Infraestrutura de teste
# --------------------------------------------------------------------------- #


class _FakeEmbeddings:
    """Extrator determinístico: vetor = cor média da imagem (normalizado)."""

    def extract_embedding(self, image: np.ndarray):
        if image is None or image.size == 0:
            return None, "fake"
        media = image.reshape(-1, image.shape[-1]).mean(axis=0)
        vector = media.astype(np.float32)
        norm = float(np.linalg.norm(vector))
        if norm > 1e-9:
            vector = vector / norm
        return vector, "fake_cor"


def _imagem(cor: tuple[int, int, int], ruido: int = 6) -> np.ndarray:
    """Imagem sintética colorida (com ruído para ter nitidez)."""
    rng = np.random.default_rng(42)
    base = np.zeros((160, 160, 3), dtype=np.float32)
    base[:, :] = cor
    base += rng.normal(0, ruido, base.shape)
    return np.clip(base, 0, 255).astype(np.uint8)


def _salvar_jpg(caminho: Path, imagem: np.ndarray) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    ok, buffer = cv2.imencode(".jpg", imagem)
    assert ok
    buffer.tofile(str(caminho))
    return caminho


@pytest.fixture()
def ambiente(tmp_path: Path):
    """App-data isolado com banco migrado, câmera e visita de teste."""
    settings = Settings(
        app_data_dir=tmp_path,
        species_match_min_sharpness=0.0,
        species_match_threshold=0.65,
        active_learning_enabled=True,
    )
    settings.ensure_directories()

    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        apply_migrations(conn)
        conn.execute(
            """
            INSERT INTO cameras (
                id, name, source_type, stream_url, is_active,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "cam-1",
                "Comedouro",
                "usb",
                "0",
                1,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.commit()

    yield settings
    # O serviço de embeddings real é singleton global: isolamos o cache.
    from app.ai.species_association import invalidate_species_association_cache

    invalidate_species_association_cache()


def _criar_visita(settings: Settings, *, visit_id: str, cor, species="bird"):
    """Cria uma visita com recorte tratado e devolve a linha do banco."""
    crop = _salvar_jpg(settings.crops_dir / f"{visit_id}.jpg", _imagem(cor))
    repository = VisitRepository(settings.db_path)
    repository.create(
        visit_id=visit_id,
        camera_id="cam-1",
        species=species,
        confidence=0.42,
        detected_at="2026-01-01T12:00:00+00:00",
        dwell_seconds=3.0,
        clip_path=None,
        thumbnail_path=None,
        bbox=[10, 10, 120, 120],
        zone_id=None,
        metadata={"crop_path": f"crops/{visit_id}.jpg"},
    )
    assert crop.is_file()
    return repository.get(visit_id)


# --------------------------------------------------------------------------- #
# 1. Auto-associação de espécie
# --------------------------------------------------------------------------- #


def test_auto_associacao_atribui_especie_do_catalogo(ambiente: Settings):
    """Recorte parecido com a foto de referência recebe o nome da espécie."""
    settings = ambiente
    reference = _salvar_jpg(
        settings.reference_birds_dir / "especie-1.jpg", _imagem((40, 90, 200))
    )
    BirdSpeciesRepository(settings.db_path).create(
        common_name="Cardeal-do-norte",
        scientific_name="Cardinalis cardinalis",
        description="",
        reference_image_path="reference_birds/especie-1.jpg",
        species_id="especie-1",
    )
    assert reference.is_file()

    _criar_visita(settings, visit_id="visita-1", cor=(38, 92, 198))
    service = SpeciesAssociationService(
        settings=settings, embeddings=_FakeEmbeddings()
    )
    resultado = service.associate_visit("visita-1")

    assert resultado["applied"] is True
    assert resultado["species"]["common_name"] == "Cardeal-do-norte"
    assert resultado["score"] >= 0.65

    row = VisitRepository(settings.db_path).get("visita-1")
    assert row["species"] == "Cardeal-do-norte"
    assert row["species_id"] == "especie-1"
    metadata = json.loads(row["metadata_json"])
    assert metadata["identification_status"] == "Identificado pelo Bem-Te-Vi Core"
    assert metadata["auto_association"]["applied"] is True
    assert metadata["auto_association"]["score"] >= 0.65


def test_auto_associacao_ignora_abaixo_do_limiar(ambiente: Settings):
    """Ave sem semelhança com o catálogo permanece sem espécie."""
    settings = ambiente
    _salvar_jpg(
        settings.reference_birds_dir / "especie-2.jpg", _imagem((250, 40, 40))
    )
    BirdSpeciesRepository(settings.db_path).create(
        common_name="Sabiá-laranjeira",
        scientific_name="Turdus rufus",
        description="",
        reference_image_path="reference_birds/especie-2.jpg",
        species_id="especie-2",
    )

    _criar_visita(settings, visit_id="visita-2", cor=(20, 200, 60))
    service = SpeciesAssociationService(
        settings=settings, embeddings=_FakeEmbeddings()
    )
    resultado = service.associate_visit("visita-2")

    assert resultado["applied"] is False
    assert resultado["reason"] == "abaixo_do_limiar"
    row = VisitRepository(settings.db_path).get("visita-2")
    assert row["species"] == "bird"
    assert row["species_id"] is None


def test_auto_associacao_nao_sobrescreve_curadoria_humana(ambiente: Settings):
    """Visita já confirmada pelo observador nunca é reescrita pelo Core."""
    settings = ambiente
    _salvar_jpg(
        settings.reference_birds_dir / "especie-3.jpg", _imagem((40, 90, 200))
    )
    BirdSpeciesRepository(settings.db_path).create(
        common_name="Cardeal-do-norte",
        scientific_name="Cardinalis cardinalis",
        description="",
        reference_image_path="reference_birds/especie-3.jpg",
        species_id="especie-3",
    )
    _criar_visita(settings, visit_id="visita-3", cor=(40, 90, 200))
    VisitRepository(settings.db_path).update_metadata(
        "visita-3", {"identification_status": "Espécie Confirmada"}
    )

    service = SpeciesAssociationService(
        settings=settings, embeddings=_FakeEmbeddings()
    )
    resultado = service.associate_visit("visita-3")

    assert resultado["applied"] is False
    assert resultado["reason"] == "curadoria_humana"


# --------------------------------------------------------------------------- #
# 2. Reclassificação + pasta de retreinamento
# --------------------------------------------------------------------------- #


def test_reclassificacao_salva_amostra_em_fine_tuning(ambiente: Settings):
    """A correção grava o recorte em ``fine_tuning/{espécie}/`` com índice."""
    settings = ambiente
    _criar_visita(settings, visit_id="visita-4", cor=(40, 90, 200))

    resultado = save_correction_sample(
        "visita-4",
        species_name="Cardeal-do-norte",
        species_id="especie-4",
        source="manual_reclassification",
        notes="erro de associação",
        settings=settings,
    )
    assert resultado["saved"] is True
    destino = settings.fine_tuning_dir / "Cardeal-do-norte" / "visita-4.jpg"
    assert destino.is_file()

    indice = (settings.fine_tuning_dir / "index.jsonl").read_text(encoding="utf-8")
    entrada = json.loads(indice.strip().splitlines()[-1])
    assert entrada["species_name"] == "Cardeal-do-norte"
    assert entrada["notes"] == "erro de associação"

    stats = fine_tuning_stats(settings)
    assert stats["total"] == 1
    assert stats["by_species"]["Cardeal-do-norte"] == 1


def test_reclassificacao_move_amostra_entre_especies(ambiente: Settings):
    """Reclassificar de novo move o arquivo (não deixa amostra duplicada)."""
    settings = ambiente
    _criar_visita(settings, visit_id="visita-5", cor=(40, 90, 200))

    save_correction_sample("visita-5", species_name="Cardeal-do-norte", settings=settings)
    save_correction_sample("visita-5", species_name="Sabiá-laranjeira", settings=settings)

    antigo = settings.fine_tuning_dir / "Cardeal-do-norte" / "visita-5.jpg"
    novo = settings.fine_tuning_dir / "Sabiá-laranjeira" / "visita-5.jpg"
    assert not antigo.exists()
    assert novo.is_file()
    assert fine_tuning_stats(settings)["total"] == 1


# --------------------------------------------------------------------------- #
# 3. Recorte HD
# --------------------------------------------------------------------------- #


def test_exportacao_hd_gera_jpeg_ampliado(ambiente: Settings):
    """O export HD Amplia o recorte e grava um JPEG em app-data/crops."""
    settings = ambiente
    _criar_visita(settings, visit_id="visita-6", cor=(40, 90, 200))

    caminho = export_hd_crop("visita-6", settings=settings)
    assert caminho is not None
    assert caminho.is_file()
    assert caminho.name == "visita-6_hd.jpg"

    imagem = cv2.imread(str(caminho))
    assert imagem is not None
    assert min(imagem.shape[:2]) >= 160  # nunca reduz a resolução
    assert friendly_crop_filename("Cardeal-do-norte", "visita-6").endswith(".jpg")


# --------------------------------------------------------------------------- #
# 4. Caixas e selos (renderização)
# --------------------------------------------------------------------------- #


class _DetecaoFake:
    """Duck-typing da ``Detection`` usada pelo módulo de anotação."""

    def __init__(self, class_name: str, confidence: float, track_id: int = 1):
        self.class_name = class_name
        self.confidence = confidence
        self.track_id = track_id
        self.bbox = (10.0, 10.0, 150.0, 150.0)
        self.class_id = 14


def _cores_presentes(imagem: np.ndarray, cor, tolerancia: int = 26) -> bool:
    """Indica se alguma pixel está próxima da cor BGR informada."""
    diferenca = np.abs(imagem.astype(int) - np.array(cor, dtype=int))
    return bool(np.any(diferenca.max(axis=2) <= tolerancia))


def test_caixa_confirmada_usa_ciano_e_pre_associacao_usa_ambra(ambiente: Settings):
    """Ave com espécie → ciano; ave genérica → âmbar (pré-associação)."""
    settings = ambiente
    frame = _imagem((30, 30, 30))

    confirmada = draw_bird_detections(
        frame,
        [_DetecaoFake("bird", 0.88)],
        species_by_track={1: "Cardeal-do-norte"},
    )
    assert _cores_presentes(confirmada, CONFIRMED_BGR)

    pre = draw_bird_detections(
        frame,
        [_DetecaoFake("bird", 0.25)],
        species_by_track={1: "Pássaro Desconhecido"},
    )
    assert _cores_presentes(pre, PENDING_BGR)
    assert not _cores_presentes(pre, CONFIRMED_BGR)


def test_resolve_imagem_tratada_da_visita(ambiente: Settings):
    """A mídia da visita é resolvida pelo recorte (com validação de caminho)."""
    settings = ambiente
    _criar_visita(settings, visit_id="visita-7", cor=(40, 90, 200))
    row = VisitRepository(settings.db_path).get("visita-7")
    caminho = resolve_visit_image(row, settings)
    assert caminho is not None
    assert caminho.name == "visita-7.jpg"
