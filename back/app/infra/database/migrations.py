"""Versioned SQLite migrations for Bem-Te-Vi."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cameras (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK (source_type IN ('usb', 'rtsp', 'onvif')),
            source_uri TEXT NOT NULL,
            username_enc TEXT,
            password_enc TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            zones_json TEXT NOT NULL DEFAULT '{"zones":[]}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS visits (
            id TEXT PRIMARY KEY,
            camera_id TEXT NOT NULL,
            species TEXT NOT NULL DEFAULT 'bird',
            confidence REAL NOT NULL DEFAULT 0,
            detected_at TEXT NOT NULL,
            dwell_seconds REAL NOT NULL DEFAULT 0,
            clip_path TEXT,
            thumbnail_path TEXT,
            bbox_json TEXT,
            zone_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_visits_detected_at ON visits(detected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_visits_camera_id ON visits(camera_id);
        CREATE INDEX IF NOT EXISTS idx_visits_species ON visits(species);

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS bird_species (
            id TEXT PRIMARY KEY,
            common_name TEXT NOT NULL,
            scientific_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            reference_image_path TEXT,
            created_at TEXT NOT NULL
        );

        ALTER TABLE visits
        ADD COLUMN species_id TEXT REFERENCES bird_species(id) ON DELETE SET NULL;

        CREATE INDEX IF NOT EXISTS idx_visits_species_id ON visits(species_id);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS audio_detections (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL DEFAULT 'AUDIO_DETECTION'
                CHECK (event_type = 'AUDIO_DETECTION'),
            camera_id TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            species TEXT NOT NULL,
            scientific_name TEXT NOT NULL,
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            linked_visit_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
            FOREIGN KEY (linked_visit_id) REFERENCES visits(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audio_detections_detected_at
            ON audio_detections(detected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audio_detections_camera_time
            ON audio_detections(camera_id, detected_at DESC);
        """,
    ),
    (
        4,
        """
        ALTER TABLE visits ADD COLUMN temperature REAL;
        ALTER TABLE visits ADD COLUMN humidity REAL;
        ALTER TABLE visits ADD COLUMN weather_code TEXT;
        ALTER TABLE visits ADD COLUMN wind_speed REAL;

        ALTER TABLE audio_detections ADD COLUMN temperature REAL;
        ALTER TABLE audio_detections ADD COLUMN humidity REAL;
        ALTER TABLE audio_detections ADD COLUMN weather_code TEXT;
        ALTER TABLE audio_detections ADD COLUMN wind_speed REAL;

        CREATE INDEX IF NOT EXISTS idx_visits_weather_code
            ON visits(weather_code);
        """,
    ),
    (
        5,
        """
        -- Status ecológico regional (avifauna do Sul do Brasil / SC) por espécie.
        ALTER TABLE bird_species ADD COLUMN ecological_status TEXT;

        -- Log de anomalias acústico-visuais (ex.: espécie ausente há meses).
        CREATE TABLE IF NOT EXISTS anomaly_events (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL DEFAULT 'species_return',
            created_at TEXT NOT NULL,
            species TEXT NOT NULL,
            scientific_name TEXT,
            days_absent INTEGER,
            message TEXT NOT NULL DEFAULT '',
            visit_id TEXT,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            details_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_anomaly_events_created_at
            ON anomaly_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_anomaly_events_species
            ON anomaly_events(species);
        """,
    ),
    (
        6,
        """
        -- Central de Câmeras: rebuild da tabela para novos campos e tipos de fonte.
        -- Renomeia colunas (source_uri→stream_url, password_enc→password_encrypted,
        -- enabled→is_active), adiciona location_label e amplia o CHECK de
        -- source_type para HLS/HTTP/WebRTC. FKs ficam OFF durante a transação.
        PRAGMA foreign_keys=OFF;
        BEGIN TRANSACTION;
        CREATE TABLE cameras_new (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK (source_type IN
                ('usb','rtsp','onvif','hls','http','webrtc')),
            stream_url TEXT NOT NULL,
            location_label TEXT,
            username TEXT,
            password_encrypted TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            zones_json TEXT NOT NULL DEFAULT '{"zones":[]}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO cameras_new
            (id, name, source_type, stream_url, location_label,
             username, password_encrypted, is_active, zones_json,
             created_at, updated_at)
        SELECT
            id, name, source_type, source_uri, NULL,
            username_enc, password_enc, enabled, zones_json,
            created_at, updated_at
        FROM cameras;
        DROP TABLE cameras;
        ALTER TABLE cameras_new RENAME TO cameras;
        COMMIT;
        PRAGMA foreign_keys=ON;
        """,
    ),
    (
        7,
        """
        -- Ficha ornitológica da IA externa por espécie (cache da consulta
        -- profunda acionada a partir de "Minhas Aves" / Álbum de Conquistas).
        ALTER TABLE bird_species ADD COLUMN ai_consult_json TEXT;
        """,
    ),
    (
        8,
        """
        -- Câmeras globais/remotas: localização geográfica opcional para exibir
        -- o clima e o horário locais do jardim (Open-Meteo) e para corrigir os
        -- gráficos de horário de pico pelo fuso da câmera.
        --   latitude/longitude: coordenadas do jardim (WGS84).
        --   timezone: identificador IANA (ex.: "America/Costa_Rica").
        --   country: país resolvido pelo geocodificador (ex.: "Costa Rica").
        ALTER TABLE cameras ADD COLUMN latitude REAL;
        ALTER TABLE cameras ADD COLUMN longitude REAL;
        ALTER TABLE cameras ADD COLUMN timezone TEXT;
        ALTER TABLE cameras ADD COLUMN country TEXT;

        -- Horário local da câmera no instante da visita: garante que os
        -- histogramas/relatórios do Alaris Core reflitam o fuso do jardim, e
        -- não o UTC. Nulos (câmeras sem fuso) caem para o UTC original.
        ALTER TABLE visits ADD COLUMN local_hour INTEGER;
        ALTER TABLE visits ADD COLUMN local_date TEXT;
        """,
    ),
    (
        9,
        """
        -- Visitantes Silvestres / Convidados Especiais ("Modo Esquilo").
        -- O Alaris Core classifica o animal que aparece no comedouro: aves
        -- seguem o fluxo ornitológico normal; mamíferos e outros viram
        -- "Visitantes Especiais" (card próprio, galeria temática) e ficam
        -- FORA da Life List e das estatísticas de aves.
        --   visitor_kind: 'bird' | 'mammal' | 'other' (padrão 'bird').
        --   visitor_group: grupo divertido (ex.: 'esquilo', 'felino').
        ALTER TABLE visits ADD COLUMN visitor_kind TEXT NOT NULL DEFAULT 'bird';
        ALTER TABLE visits ADD COLUMN visitor_group TEXT;

        CREATE INDEX IF NOT EXISTS idx_visits_visitor_kind
            ON visits(visitor_kind);
        """,
    ),
    (
        10,
        """
        -- Segmentação por Jardim (Câmaras Remotas/Locais): cada visita registra
        -- o rótulo amigável do jardim (location_label da câmera) no momento da
        -- captura, para que os painéis e gráficos possam agregar/filtrar por
        -- jardim sem depender de joins posteriores (e sobrevivendo a renomeações
        -- da câmera). Câmaras sem rótulo recebem NULL (exibido como
        -- "Jardim sem nome").
        ALTER TABLE visits ADD COLUMN location_label TEXT;

        CREATE INDEX IF NOT EXISTS idx_visits_location_label
            ON visits(location_label);
        CREATE INDEX IF NOT EXISTS idx_visits_camera_id
            ON visits(camera_id);
        """,
    ),
    (
        11,
        """
        -- Controles Operacionais em Tempo Real por Câmera (Alaris Core & Bioacústica BirdNET).
        -- ai_enabled: liga/desliga o processamento de IA (YOLOv8) e gravação de visitas.
        -- audio_enabled: liga/desliga a captura e monitoramento contínuo de áudio com BirdNET.
        ALTER TABLE cameras ADD COLUMN ai_enabled INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE cameras ADD COLUMN audio_enabled INTEGER NOT NULL DEFAULT 0;
        """,
    ),
    (
        12,
        """
        -- Preservação permanente do histórico do jardim.
        -- Excluir uma câmera NÃO apaga mais as visitas, os clipes de vídeo, as
        -- fotos nem os áudios associados. A câmera passa a ser "arquivada"
        -- (is_archived = 1) e sai das listagens e do processamento, mas as
        -- visitas continuam apontando para ela (o LEFT JOIN preserva o nome do
        -- jardim no histórico). O ON DELETE CASCADE das visitas permanece apenas
        -- como salvaguarda e nunca é acionado pelo fluxo normal.
        ALTER TABLE cameras ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0;

        CREATE INDEX IF NOT EXISTS idx_cameras_is_archived ON cameras(is_archived);
        """,
    ),
    (
        13,
        """
        -- Detecção Sonora (Bioacústica): cada canto identificado pelo BirdNET
        -- passa a guardar o clipe de áudio gravado, o vínculo com a espécie da
        -- Life List e a ficha ornitológica da IA externa em cache.
        --   audio_path: caminho relativo do WAV em captures/audio/.
        --   species_id: card da espécie (bird_species) associado, quando houver.
        --   identification_status: rótulo do estado (ex.: "Identificado por IA Externa").
        --   ai_consult_json: ficha ornitológica da IA externa em cache (JSON).
        ALTER TABLE audio_detections ADD COLUMN audio_path TEXT;
        ALTER TABLE audio_detections ADD COLUMN species_id TEXT;
        ALTER TABLE audio_detections ADD COLUMN identification_status TEXT;
        ALTER TABLE audio_detections ADD COLUMN ai_consult_json TEXT;

        CREATE INDEX IF NOT EXISTS idx_audio_detections_species
            ON audio_detections(species_id);
        """,
    ),
]


def get_current_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT MAX(version) AS version FROM schema_migrations"
        ).fetchone()
        if row is None or row["version"] is None:
            return 0
        return int(row["version"])
    except sqlite3.OperationalError:
        return 0


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending migrations. Returns the final schema version."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    current = get_current_version(conn)
    applied = 0

    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        logger.info("Applying database migration v%s", version)
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _utc_now()),
            )
            conn.commit()
            applied += 1
            current = version
        except Exception:
            conn.rollback()
            logger.exception("Failed to apply migration v%s", version)
            raise

    if applied:
        logger.info("Database migrated to version %s (%s new)", current, applied)
    else:
        logger.debug("Database already at version %s", current)
    return current
