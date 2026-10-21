"""Rede Global Bem-Te-Vi Monitor: destaques de avistamentos entre jardins.

Cada instância pode compartilhar (e receber) avisos de **avistamentos raros ou
incomuns**. O módulo é deliberadamente conservador:

* o feed local funciona sozinho, reunindo os destaques das câmeras deste jardim;
* o **webhook** de entrada só responde quando um token compartilhado está
  configurado (comparação em tempo constante);
* a publicação para parceiros roda em thread separada, com timeout curto, e
  nunca atrasa a captura ou a gravação da visita;
* o payload é sanitizado e limitado, e URLs de mídia não são aceitas — o feed
  exibe texto, sem baixar arquivos de terceiros.

Nenhum dado sensível (token, credenciais ou URLs privadas) aparece no feed.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.core.config import get_settings
from app.infra.database.connection import db_session

logger = logging.getLogger(__name__)

_RARE_TOKENS = ("rara", "raro", "amea", "vulner", "endanger", "critic")
_INCOMMON_TOKENS = ("endem", "migrat", "quase", "near")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_timestamp(value: str | None) -> str:
    """Aceita ISO-8601 com ou sem fuso; devolve sempre UTC ISO."""
    if not value:
        return _now_iso()
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return _now_iso()


def classify_rarity(
    ecological_status: str | None,
    *,
    anomaly: bool = False,
    local_sightings: int | None = None,
) -> str:
    """Converte o status ecológico e a frequência local em um destaque.

    Prioridade: anomalia/reaparecimento > status regional > frequência local.
    Uma espécie comum, mas vista poucas vezes neste jardim, ainda merece o
    feed; uma espécie nativa com dezenas de registros não vira ruído.
    """
    if anomaly:
        return "Rara"
    status = (ecological_status or "").strip().casefold()
    if any(token in status for token in _RARE_TOKENS):
        return "Rara"
    if any(token in status for token in _INCOMMON_TOKENS):
        return "Incomum"
    if local_sightings is not None and local_sightings > 0:
        if local_sightings <= 2:
            return "Rara"
        if local_sightings <= 5:
            return "Incomum"
    return "Comum"


def token_matches(received: str | None, expected: str) -> bool:
    """Comparação em tempo constante do token do webhook."""
    if not expected or not received:
        return False
    return hmac.compare_digest(str(received), str(expected))


def _peer_urls() -> list[str]:
    """URLs de webhook dos parceiros, normalizadas e sem duplicatas."""
    raw = str(get_settings().global_network_peers or "")
    urls: list[str] = []
    for part in raw.replace("\n", ",").split(","):
        candidate = part.strip()
        if not candidate:
            continue
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.warning("Parceiro da rede global inválido ignorado: %s", candidate)
            continue
        candidate = candidate.rstrip("/")
        if not candidate.endswith("/api/network/webhook"):
            candidate = f"{candidate}/api/network/webhook"
        if candidate not in urls:
            urls.append(candidate)
    return urls


class GlobalNetworkService:
    """Persistência e distribuição do Feed Global Bem-Te-Vi Monitor."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.settings = get_settings()
        self.db_path = db_path or self.settings.db_path

    # ------------------------------------------------------------------
    # Registro local
    # ------------------------------------------------------------------
    def _local_sighting_count(
        self,
        species: str,
        scientific_name: str | None,
        occurred_at: str,
    ) -> int | None:
        """Quantas vezes esta espécie já foi registrada até o momento.

        Usa a coluna indexada ``visits.species`` para manter o custo baixo no
        caminho quente do pipeline. Se não houver correspondência exata, tenta o
        nome científico (visitas antigas podem ter sido renomeadas no catálogo).
        """
        cleaned = (species or "").strip()
        if not cleaned:
            return None
        try:
            with db_session(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM visits
                    WHERE species = ?
                      AND COALESCE(NULLIF(visitor_kind, ''), 'bird') = 'bird'
                      AND julianday(detected_at) <= julianday(?)
                    """,
                    (cleaned, occurred_at),
                ).fetchone()
                total = int(row["total"]) if row is not None else 0
                if total > 0 or not scientific_name:
                    return total
                fallback = conn.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM visits v
                    JOIN bird_species bs ON bs.id = v.species_id
                    WHERE bs.scientific_name = ?
                      AND COALESCE(NULLIF(v.visitor_kind, ''), 'bird') = 'bird'
                      AND julianday(v.detected_at) <= julianday(?)
                    """,
                    (scientific_name, occurred_at),
                ).fetchone()
                return int(fallback["total"]) if fallback is not None else total
        except Exception:
            logger.debug(
                "Não foi possível contar os avistamentos locais de %s",
                cleaned,
                exc_info=True,
            )
            return None

    def record_local_sighting(
        self,
        *,
        visit_id: str,
        species: str,
        scientific_name: str | None = None,
        camera_id: str | None = None,
        camera_name: str | None = None,
        garden_name: str | None = None,
        ecological_status: str | None = None,
        confidence: float | None = None,
        occurred_at: str | None = None,
        anomaly: bool = False,
    ) -> dict[str, Any] | None:
        """Registra um destaque local e publica nos parceiros (em background).

        Espécies comuns são ignoradas, a menos que ``GLOBAL_NETWORK_SHARE_ALL``
        esteja ligado. Devolve o evento criado ou ``None`` quando não é um
        destaque (ou quando o mesmo ``visit_id`` já foi compartilhado).
        """
        if not self.settings.global_network_enabled:
            return None

        occurred = _normalize_timestamp(occurred_at)
        rarity = classify_rarity(ecological_status, anomaly=anomaly)
        if rarity == "Comum":
            local_sightings = self._local_sighting_count(
                species, scientific_name, occurred
            )
            rarity = classify_rarity(
                ecological_status,
                anomaly=anomaly,
                local_sightings=local_sightings,
            )
        if rarity == "Comum" and not self.settings.global_network_share_all:
            return None

        instance = self.settings.global_network_instance_name or "Meu Jardim"
        event_id = str(uuid.uuid4())
        external_id = f"local:{instance.casefold()}:{visit_id}"
        received_at = _now_iso()
        payload = {
            "event_id": visit_id,
            "instance": instance,
            "species": species,
            "scientific_name": scientific_name,
            "rarity": rarity,
            "garden": garden_name,
            "camera": camera_name,
            "confidence": confidence,
            "occurred_at": occurred,
        }

        try:
            with db_session(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO network_feed_events (
                        id, external_id, source_kind, source_instance,
                        garden_name, camera_name, species, scientific_name,
                        rarity, confidence, occurred_at, received_at,
                        payload_json
                    ) VALUES (?, ?, 'local', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        external_id,
                        instance,
                        garden_name,
                        camera_name,
                        species,
                        scientific_name,
                        rarity,
                        confidence,
                        occurred,
                        received_at,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                if cursor.rowcount == 0:
                    return None
        except Exception:
            logger.exception("Falha ao registrar destaque local da rede global")
            return None

        event = {
            "id": event_id,
            "source_kind": "local",
            "source_instance": instance,
            "garden_name": garden_name,
            "camera_name": camera_name,
            "species": species,
            "scientific_name": scientific_name,
            "rarity": rarity,
            "confidence": confidence,
            "occurred_at": occurred,
            "received_at": received_at,
        }
        self._publish_to_peers(payload)
        return event

    # ------------------------------------------------------------------
    # Recebimento de parceiros
    # ------------------------------------------------------------------
    def ingest_peer_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persiste um destaque recebido de outra instância (idempotente)."""
        instance = str(payload.get("instance") or "").strip() or "Jardim remoto"
        species = str(payload.get("species") or "").strip()
        if not species:
            raise ValueError("O evento não informa a espécie avistada.")
        scientific_name = (
            str(payload.get("scientific_name") or "").strip() or None
        )
        rarity = str(payload.get("rarity") or "Incomum").strip()
        if rarity not in {"Rara", "Incomum", "Comum"}:
            rarity = "Incomum"
        remote_event = str(payload.get("event_id") or "").strip() or None
        occurred = _normalize_timestamp(payload.get("occurred_at"))
        external_id = (
            f"peer:{instance.casefold()}:{remote_event}"
            if remote_event
            else f"peer:{instance.casefold()}:{species.casefold()}:{occurred}"
        )
        event_id = str(uuid.uuid4())
        received_at = _now_iso()
        garden = str(payload.get("garden") or "").strip() or None
        camera = str(payload.get("camera") or "").strip() or None
        confidence = payload.get("confidence")
        if not isinstance(confidence, (int, float)):
            confidence = None
        else:
            confidence = min(1.0, max(0.0, float(confidence)))

        try:
            with db_session(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO network_feed_events (
                        id, external_id, source_kind, source_instance,
                        garden_name, camera_name, species, scientific_name,
                        rarity, confidence, occurred_at, received_at,
                        payload_json
                    ) VALUES (?, ?, 'peer', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        external_id,
                        instance,
                        garden,
                        camera,
                        species,
                        scientific_name,
                        rarity,
                        confidence,
                        occurred,
                        received_at,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                duplicate = cursor.rowcount == 0
                row = conn.execute(
                    "SELECT id FROM network_feed_events WHERE external_id = ?",
                    (external_id,),
                ).fetchone()
                if row is not None:
                    event_id = str(row["id"])
        except Exception:
            logger.exception("Falha ao gravar evento recebido da rede global")
            raise

        return {
            "accepted": True,
            "duplicate": duplicate,
            "event_id": event_id,
        }

    # ------------------------------------------------------------------
    # Feed e estado
    # ------------------------------------------------------------------
    def feed(
        self,
        *,
        days: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Lista os destaques recentes (locais e de parceiros)."""
        settings = self.settings
        window_days = min(
            90,
            max(1, int(days or settings.global_network_feed_days)),
        )
        max_items = min(
            100,
            max(1, int(limit or settings.global_network_feed_limit)),
        )
        start = (
            datetime.now(timezone.utc) - timedelta(days=window_days)
        ).isoformat()
        with db_session(self.db_path) as conn:
            total_row = conn.execute(
                "SELECT COUNT(*) AS total FROM network_feed_events "
                "WHERE occurred_at >= ?",
                (start,),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT id, source_kind, source_instance, garden_name,
                       camera_name, species, scientific_name, rarity,
                       confidence, occurred_at, received_at
                FROM network_feed_events
                WHERE occurred_at >= ?
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (start, max_items),
            ).fetchall()
        events = [
            {
                "id": str(row["id"]),
                "source_kind": str(row["source_kind"]),
                "source_instance": str(row["source_instance"]),
                "garden_name": row["garden_name"],
                "camera_name": row["camera_name"],
                "species": str(row["species"]),
                "scientific_name": row["scientific_name"],
                "rarity": str(row["rarity"]),
                "confidence": (
                    float(row["confidence"])
                    if row["confidence"] is not None
                    else None
                ),
                "occurred_at": str(row["occurred_at"]),
                "received_at": str(row["received_at"]),
            }
            for row in rows
        ]
        return {
            "generated_at": _now_iso(),
            "enabled": bool(settings.global_network_enabled),
            "instance_name": settings.global_network_instance_name or "Meu Jardim",
            "days": window_days,
            "total": int(total_row["total"]) if total_row else 0,
            "events": events,
        }

    def status(self) -> dict[str, Any]:
        """Estado da integração, sem expor o token ou as URLs dos parceiros."""
        settings = self.settings
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT source_kind, COUNT(*) AS total
                FROM network_feed_events
                GROUP BY source_kind
                """
            ).fetchall()
        counts = {str(row["source_kind"]): int(row["total"]) for row in rows}
        return {
            "enabled": bool(settings.global_network_enabled),
            "instance_name": settings.global_network_instance_name or "Meu Jardim",
            "webhook_ready": bool(settings.global_network_token),
            "peers_configured": len(_peer_urls()),
            "local_events": counts.get("local", 0),
            "peer_events": counts.get("peer", 0),
            "feed_days": int(settings.global_network_feed_days),
        }

    # ------------------------------------------------------------------
    # Publicação assíncrona
    # ------------------------------------------------------------------
    def _publish_to_peers(self, payload: dict[str, Any]) -> None:
        """Dispara o envio para os parceiros em uma thread daemon."""
        settings = self.settings
        if not settings.global_network_enabled:
            return
        if not settings.global_network_token:
            # Sem token, os parceiros recusariam o evento; não há o que fazer.
            return
        peers = _peer_urls()
        if not peers:
            return

        def _send() -> None:
            headers = {
                "Content-Type": "application/json",
                "X-Bem-Te-Vi-Token": settings.global_network_token,
                "User-Agent": "Bem-Te-Vi-Monitor-Global-Network/1.0",
            }
            for url in peers:
                try:
                    response = requests.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=(3.0, settings.global_network_timeout_seconds),
                    )
                    if response.status_code >= 400:
                        logger.warning(
                            "Parceiro recusou o destaque global (%s): HTTP %s",
                            urlparse(url).netloc,
                            response.status_code,
                        )
                except Exception:
                    logger.warning(
                        "Falha ao publicar no parceiro %s",
                        urlparse(url).netloc,
                        exc_info=True,
                    )

        threading.Thread(target=_send, name="bem-te-vi-monitor-network", daemon=True).start()


def get_global_network_service() -> GlobalNetworkService:
    """Instância leve (o estado vive no SQLite compartilhado)."""
    return GlobalNetworkService()
