"""Log de anomalias acústico-visuais.

Detecta eventos relevantes para conservação — em especial o **retorno de uma
espécie ausente**: se uma ave volta a ser registrada (visual ou sonoramente)
após um longo intervalo (padrão: mais de 6 meses), geramos uma anomalia no
painel. Isso ajuda biólogos a notar reaparecimentos, sazonalidade incomum e
possíveis mudanças de rota.

O serviço é tolerante a falhas: qualquer erro é registrado e nunca derruba a
captura/identificação.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.infra.database.connection import db_session
from app.infra.database.repository import AnomalyRepository

logger = logging.getLogger(__name__)

KIND_SPECIES_RETURN = "species_return"


def _parse_iso(valor: str | None) -> datetime | None:
    """Converte um timestamp ISO (com ``Z`` ou offset) em datetime UTC."""
    if not valor:
        return None
    texto = str(valor).strip()
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def _ultima_deteccao(
    species: str,
    scientific_name: str | None,
    exclude_visit_id: str | None = None,
) -> str | None:
    """Data (ISO) do último registro conhecido da espécie, ou ``None``.

    ``exclude_visit_id`` ignora a visita recém-criada, para que o cálculo da
    ausência reflita o histórico **anterior** a ela.
    """
    with db_session(get_settings().db_path) as conn:
        row = conn.execute(
            """
            SELECT MAX(detected_at) AS ultima FROM (
                SELECT detected_at FROM visits
                WHERE species = ? COLLATE NOCASE
                    AND (? IS NULL OR id != ?)
                UNION ALL
                SELECT detected_at FROM audio_detections
                WHERE species = ? COLLATE NOCASE
                    OR (? IS NOT NULL AND scientific_name = ? COLLATE NOCASE)
            )
            """,
            (species, exclude_visit_id, exclude_visit_id, species, scientific_name, scientific_name),
        ).fetchone()
    return str(row["ultima"]) if row and row["ultima"] else None


def registrar_retorno_especie(
    *,
    species: str,
    scientific_name: str | None = None,
    visit_id: str | None = None,
    exclude_visit_id: str | None = None,
) -> dict[str, Any] | None:
    """Registra uma anomalia se a espécie reaparecer após longo intervalo.

    Devolve o registro criado (dict) ou ``None`` quando não é anomalia (primeira
    observação, intervalo curto, log desligado ou anomalia recente já existente).
    ``exclude_visit_id`` ignora a visita atual no cálculo da ausência.
    """
    settings = get_settings()
    if not bool(settings.anomaly_log_enabled):
        return None
    nome = str(species or "").strip()
    if not nome or nome.lower() in {"bird", "passaro", "passaro desconhecido"}:
        # Sem espécie confiável (ainda genérica), não há como avaliar.
        return None

    try:
        ultima = _ultima_deteccao(nome, scientific_name, exclude_visit_id)
        if ultima is None:
            return None  # primeira vez: não é um "retorno"

        momento = _parse_iso(ultima)
        if momento is None:
            return None
        agora = datetime.now(timezone.utc)
        dias = int((agora - momento).total_seconds() // 86400)
        if dias < int(settings.anomaly_species_gap_days):
            return None

        repo = AnomalyRepository(settings.db_path)
        desde = (agora - timedelta(days=int(settings.anomaly_cooldown_days))).isoformat()
        if repo.has_recent_for_species(nome, desde):
            return None

        meses = round(dias / 30.0, 1)
        mensagem = (
            f"⭐ {nome} não era registrada há {dias} dias "
            f"(~{meses} meses)! Reaparecimento detectado."
        )
        registro = repo.create(
            kind=KIND_SPECIES_RETURN,
            species=nome,
            scientific_name=scientific_name,
            days_absent=dias,
            message=mensagem,
            visit_id=visit_id,
            details={"last_seen_at": ultima, "gap_days": dias},
        )
        logger.info("Anomalia registrada: %s (ausente %s dias)", nome, dias)
        return registro
    except Exception:
        logger.exception("Falha ao avaliar anomalia de retorno para %s", nome)
        return None
