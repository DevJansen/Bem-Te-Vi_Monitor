"""Pasta local de retreinamento (``data/fine_tuning``) das correções humanas.

Quando o observador corrige uma identificação ("Associação Incorreta /
Reclassificar"), o Bem-Te-Vi Core precisa guardar **a imagem que estava errada e o
rótulo correto**. Este módulo materializa esse par em disco, de forma simples e
auditável:

```
app-data/fine_tuning/
├── Cardeal-do-norte/
│   └── {visit_id}.jpg
├── index.jsonl                 # proveniência de cada amostra
```

O ``index.jsonl`` funciona como um mini catálogo append-only: uma linha JSON por
correção, com visita, espécie, origem, similaridade e data. Reclassificar a mesma
visita move a amostra para a pasta da nova espécie e remove o arquivo anterior,
evitando que o mesmo recorte ensine duas classes contraditórias.

Observação: a **fila operacional** do fine-tuning automático continua em
``app-data/training_queue`` (ver :mod:`app.ai.active_learning`). A pasta
``fine_tuning`` é a fonte de auditoria/retreinamento manual — deliberadamente
separada para que o usuário possa inspecionar, exportar ou versionar as
correções sem tocar na fila do treino.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ai.active_learning import safe_species_folder
from app.ai.visit_media import resolve_visit_image
from app.core.config import Settings, get_settings
from app.infra.database.repository import VisitRepository

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _index_path(settings: Settings) -> Path:
    return settings.fine_tuning_dir / "index.jsonl"


def _read_index(settings: Settings) -> list[dict[str, Any]]:
    """Lê o índice JSONL tolerando linhas corrompidas (nunca falha)."""
    path = _index_path(settings)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict):
                entries.append(data)
    except OSError:
        logger.exception("Falha ao ler o índice de fine-tuning")
    return entries


def _write_index(settings: Settings, entries: list[dict[str, Any]]) -> None:
    """Grava o índice de forma atômica (arquivo temporário + replace)."""
    path = _index_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".jsonl.tmp")
    payload = "\n".join(
        json.dumps(entry, ensure_ascii=False) for entry in entries
    )
    temporary.write_text((payload + "\n") if payload else "", encoding="utf-8")
    temporary.replace(path)


def _relative(path: Path, settings: Settings) -> str:
    """Caminho relativo ao ``app-data`` (formato usado nos metadados)."""
    try:
        return path.resolve().relative_to(settings.app_data_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _remove_previous_samples(
    entries: list[dict[str, Any]],
    visit_id: str,
    destination: Path,
    settings: Settings,
) -> list[dict[str, Any]]:
    """Remove arquivos antigos da mesma visita e devolve o índice limpo."""
    kept: list[dict[str, Any]] = []
    for entry in entries:
        if str(entry.get("visit_id")) != visit_id:
            kept.append(entry)
            continue
        previous = entry.get("image_path")
        if not isinstance(previous, str) or not previous:
            continue
        candidate = (settings.app_data_dir / previous).resolve()
        if candidate == destination.resolve():
            continue
        if candidate.is_file():
            try:
                candidate.unlink()
            except OSError:
                logger.debug("Não foi possível remover amostra antiga %s", candidate)
    return kept


def save_correction_sample(
    visit_id: str,
    *,
    species_name: str,
    species_id: str | None = None,
    source: str = "manual_reclassification",
    notes: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Copia o recorte corrigido para ``fine_tuning/{espécie}/``.

    Devolve ``{"saved": bool, "path": str|None, "species": str, "reason": ...}``.
    Falhas são registradas e devolvidas (nunca derrubam a requisição de
    reclassificação, que é a ação principal do usuário).
    """
    settings = settings or get_settings()
    result: dict[str, Any] = {
        "visit_id": visit_id,
        "species": species_name,
        "species_id": species_id,
        "saved": False,
        "path": None,
        "reason": None,
    }
    cleaned = (species_name or "").strip()
    if not cleaned:
        result["reason"] = "especie_vazia"
        return result

    repository = VisitRepository(settings.db_path)
    row = repository.get(visit_id)
    if row is None:
        result["reason"] = "visita_nao_encontrada"
        return result
    if (row.get("visitor_kind") or "bird") != "bird":
        result["reason"] = "visitante_especial"
        return result

    source_path = resolve_visit_image(row, settings)
    if source_path is None:
        result["reason"] = "imagem_indisponivel"
        return result

    try:
        settings.fine_tuning_dir.mkdir(parents=True, exist_ok=True)
        folder = settings.fine_tuning_dir / safe_species_folder(cleaned)
        folder.mkdir(parents=True, exist_ok=True)
        suffix = source_path.suffix.lower() if source_path.suffix else ".jpg"
        destination = folder / f"{visit_id}{suffix}"

        with _lock:
            entries = _read_index(settings)
            entries = _remove_previous_samples(
                entries, visit_id, destination, settings
            )
            if source_path.resolve() != destination.resolve():
                shutil.copy2(source_path, destination)
            entries.append(
                {
                    "visit_id": visit_id,
                    "species_name": cleaned,
                    "species_id": species_id or row.get("species_id"),
                    "source": source,
                    "image_path": _relative(destination, settings),
                    "confidence": row.get("confidence"),
                    "notes": (notes or "").strip() or None,
                    "created_at": _utc_now(),
                }
            )
            _write_index(settings, entries)

        result["saved"] = True
        result["path"] = _relative(destination, settings)
        result["reason"] = "amostra_salva"
        logger.info(
            "Correção salva para fine-tuning: %s → %s", visit_id, destination
        )
        return result
    except OSError:
        logger.exception(
            "Falha ao salvar a amostra de fine-tuning da visita %s", visit_id
        )
        result["reason"] = "falha_de_escrita"
        return result


def fine_tuning_stats(settings: Settings | None = None) -> dict[str, Any]:
    """Resumo das correções gravadas (contagem por espécie e total)."""
    settings = settings or get_settings()
    entries = _read_index(settings)
    counts: dict[str, int] = {}
    for entry in entries:
        species = str(entry.get("species_name") or "").strip()
        if species:
            counts[species] = counts.get(species, 0) + 1
    return {
        "total": len(entries),
        "by_species": dict(sorted(counts.items())),
        "directory": str(settings.fine_tuning_dir),
        "last_correction_at": (
            entries[-1].get("created_at") if entries else None
        ),
    }
