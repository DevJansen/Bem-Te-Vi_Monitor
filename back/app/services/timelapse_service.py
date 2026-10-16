"""Serviço de resumos do dia (time-lapse): orquestração e agendamento.

Responsabilidades:

* **Consultar** o banco para descobrir os clipes de vídeo gravados em um dia;
* **Gerar** o ``timelapse_YYYY-MM-DD.mp4`` (delegando a montagem ao FFmpeg em
  ``app.infra.media.timelapse``);
* **Listar** e **remover** os resumos existentes;
* Rodar um **agendador** em segundo plano que monta o resumo no fim do dia e
  recupera dias que ficaram pendentes enquanto o app estava desligado.

O "dia" é interpretado no **fuso local** do computador (o que o observador
espera ao ver "resumo de 15/10"), mas as consultas ao banco convertem esse dia
para o intervalo UTC correspondente, já que as visitas são gravadas em UTC.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from app.core.config import Settings, get_settings
from app.infra.media import timelapse as media

logger = logging.getLogger(__name__)

# Formato de data/hora usado nas colunas do banco (`detected_at`).
_DB_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _visit_repo():
    """Cria o repositório de visitas sob demanda.

    Import tardio para evitar o ciclo ``services ↔ database`` (o repositório
    importa serviços de clima, que por sua vez podem depender de outros
    serviços).
    """
    from app.infra.database.repository import VisitRepository

    return VisitRepository(get_settings().db_path)


def _local_day_bounds_utc(day: date) -> tuple[str, str]:
    """Converte um dia local para o intervalo ``[início, fim)`` em UTC.

    Devolve duas strings no formato gravado pelo pipeline
    (``YYYY-MM-DDTHH:MM:SSZ``) para permitir a comparação direta no SQLite.
    """
    local_tz = datetime.now().astimezone().tzinfo
    start_local = datetime.combine(day, time.min, tzinfo=local_tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return (
        start_utc.strftime(_DB_DATETIME_FORMAT),
        end_utc.strftime(_DB_DATETIME_FORMAT),
    )


class TimelapseService:
    """Gera, lista e remove os resumos do dia (sob demanda ou agendados)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        # O FFmpeg é pesado; serializa as gerações para não competir por CPU.
        self._lock = threading.Lock()

    # ——— Consultas ———

    def list(self) -> list[dict]:
        """Lista os resumos existentes (mais recentes primeiro), com a URL."""
        return [self._describe(video) for video in media.list_timelapse_files()]

    def get(self, day: date) -> dict | None:
        """Metadados do resumo de um dia específico (ou ``None`` se não existir)."""
        video = media.timelapse_path(day)
        if not video.is_file():
            return None
        return self._describe(video)

    # ——— Geração ———

    def generate(self, day: date | None = None, *, force: bool = False) -> dict:
        """Gera o resumo de um dia (padrão: hoje, no fuso local).

        Devolve um dicionário com ``status`` em
        ``generated``/``exists``/``empty``/``unavailable`` e, quando aplicável,
        os metadados em ``timelapse``.
        """
        target = day or datetime.now().date()
        video = media.timelapse_path(target)

        with self._lock:
            if video.is_file() and not force:
                return {
                    "status": "exists",
                    "message": f"O resumo de {target.isoformat()} já existe.",
                    "timelapse": self._describe(video),
                }

            clips = self._collect_clips(target)
            if not clips:
                return {
                    "status": "empty",
                    "message": (
                        f"Não há clipes gravados em {target.isoformat()} "
                        "para montar o resumo."
                    ),
                    "timelapse": None,
                }

            metadata = media.build_timelapse(
                clips, target, self.settings.timelapse_speed
            )
            if metadata is None:
                return {
                    "status": "unavailable",
                    "message": (
                        "Não foi possível gerar o resumo do dia. Confirme se o "
                        "FFmpeg está instalado e se os clipes são válidos."
                    ),
                    "timelapse": None,
                }
            metadata["url"] = media.timelapse_url(metadata["filename"])
            return {
                "status": "generated",
                "message": f"Resumo de {target.isoformat()} gerado com sucesso.",
                "timelapse": metadata,
            }

    def delete(self, filename: str) -> bool:
        """Remove um resumo pelo nome do arquivo (valida o padrão do nome)."""
        if not media.is_timelapse_filename(filename):
            return False
        return media.delete_timelapse(self.settings.timelapses_dir / filename)

    # ——— Auxiliares ———

    def missing_days(
        self, days: int, *, include_today: bool = False
    ) -> list[date]:
        """Dias recentes com clipes, mas ainda sem resumo.

        Percorre do mais antigo para o mais recente, para que a recuperação
        gere os resumos em ordem cronológica. Quando ``include_today`` é
        verdadeiro, o dia corrente também é considerado (usado quando o app
        inicia depois do horário agendado, no fim do dia).
        """
        today = datetime.now().date()
        offsets = list(range(days, 0, -1))
        if include_today:
            offsets.append(0)
        missing: list[date] = []
        for offset in offsets:
            day = today - timedelta(days=offset)
            if media.timelapse_path(day).is_file():
                continue
            if self._collect_clips(day):
                missing.append(day)
        return missing

    def _describe(self, video: Path) -> dict:
        """Metadados do arquivo + URL de streaming pronta para o player."""
        metadata = media.load_metadata(video)
        metadata["url"] = media.timelapse_url(video.name)
        return metadata

    def _collect_clips(self, day: date) -> list[Path]:
        """Resolve os clipes das visitas do dia para arquivos existentes."""
        start_utc, end_utc = _local_day_bounds_utc(day)
        clip_paths = _visit_repo().list_clip_paths_between(start_utc, end_utc)
        clips: list[Path] = []
        for raw in clip_paths:
            resolved = media.resolve_clip_path(raw)
            if resolved is not None and resolved.is_file():
                clips.append(resolved)
        return clips


class TimelapseScheduler:
    """Monta o resumo no fim do dia e recupera dias pendentes ao iniciar."""

    def __init__(self, service: TimelapseService | None = None) -> None:
        self.settings = get_settings()
        self.service = service or get_timelapse_service()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="timelapse-scheduler",
            daemon=True,
        )

    def start(self) -> None:
        """Inicia a thread (não faz nada se a geração automática estiver off)."""
        if not self.settings.timelapse_enabled:
            logger.info("Geração automática de time-lapse desativada.")
            return
        self._thread.start()

    def stop(self) -> None:
        """Sinaliza a parada e aguarda a thread encerrar."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        # Primeiro recupera o atraso (dias sem resumo) e só então agenda o dia.
        self._backfill()
        while not self._stop.is_set():
            if self._stop.wait(self._seconds_until_next_run()):
                return
            self._generate_today()

    def _backfill(self) -> None:
        """Gera os resumos de dias anteriores que ficaram pendentes."""
        days = self.settings.timelapse_backfill_days
        if days <= 0:
            return
        # Depois do horário agendado, o dia corrente também entra na recuperação
        # (o resumo seria montado hoje à noite de qualquer forma).
        include_today = datetime.now() >= self._scheduled_datetime()
        try:
            pending = self.service.missing_days(days, include_today=include_today)
        except Exception:
            logger.exception("Falha ao verificar resumos pendentes")
            return
        for day in pending:
            if self._stop.is_set():
                return
            try:
                self.service.generate(day)
            except Exception:
                logger.exception("Falha ao gerar o resumo atrasado de %s", day)

    def _generate_today(self) -> None:
        """Regenera o resumo do dia corrente (inclui o que foi gravado hoje)."""
        try:
            self.service.generate(force=True)
        except Exception:
            logger.exception("Falha ao gerar o resumo do dia")

    def _scheduled_datetime(self, now: datetime | None = None) -> datetime:
        """Data/hora local do horário agendado para hoje."""
        reference = now or datetime.now()
        return datetime.combine(
            reference.date(),
            time(
                hour=self.settings.timelapse_hour,
                minute=self.settings.timelapse_minute,
            ),
        )

    def _seconds_until_next_run(self) -> float:
        """Segundos até o próximo horário agendado (hora/minuto configurados)."""
        now = datetime.now()
        target = self._scheduled_datetime(now)
        if target <= now:
            target += timedelta(days=1)
        return max(1.0, (target - now).total_seconds())


_service: TimelapseService | None = None


def get_timelapse_service() -> TimelapseService:
    """Instância única (singleton) do serviço de time-lapse."""
    global _service
    if _service is None:
        _service = TimelapseService()
    return _service
