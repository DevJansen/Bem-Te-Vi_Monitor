"""Aprendizado ativo e fine-tuning incremental do Bem-Te-Vi Core.

O observador é o professor do sistema. Sempre que ele **corrige** a espécie de
uma visita ou **confirma** uma detecção, o recorte tratado da ave (o mesmo
close-up exibido na Galeria) é copiado para a fila de treinamento:

    app-data/training_queue/{espécie}/...

A partir dessa fila, o botão **“Otimizar Bem-Te-Vi Core com Novas Amostras”**
(Configurações) dispara um *fine-tuning* leve de um modelo de classificação
YOLOv8 (``yolov8n-cls.pt``). O treino roda em segundo plano, com poucas épocas,
e o ``best.pt`` resultante passa a ser consumido pelo classificador de espécies
do pipeline ao vivo — sem reiniciar o aplicativo.

Princípios de projeto:

* **Assíncrono e isolado** — o treino nunca bloqueia a API nem a captura.
* **Degradação graciosa** — sem ``ultralytics``/``torch`` a fila continua
  funcionando; apenas o botão de otimização informa que o treino não está
  disponível.
* **Vocabulário controlado** — rótulos genéricos (``bird``, ``Pássaro
  Desconhecido``) nunca entram na fila, pois não ensinam nada ao modelo.
* **Rastreável** — cada execução fica registrada em ``fine_tune_runs`` com
  status, métricas e o caminho do artefato gerado.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import math
import random
import re
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ai.visit_media import resolve_visit_image
from app.core.config import Settings, get_settings
from app.domain.species_labels import is_generic_species as _rotulo_generico
from app.infra.database.connection import db_session
from app.infra.database.repository import VisitRepository

logger = logging.getLogger(__name__)

# Caracteres proibidos pelo Windows (e separadores POSIX) em nomes de pasta.
_INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ActiveLearningError(RuntimeError):
    """Erro de negócio do aprendizado ativo (mensagem exibível ao usuário)."""


def utc_now() -> str:
    """Instante atual em UTC no formato ISO usado pelo SQLite."""
    return datetime.now(timezone.utc).isoformat()


def is_generic_species(name: str | None) -> bool:
    """Indica se o rótulo é genérico e não deve virar classe de treino.

    Reexporta o vocabulário compartilhado do domínio
    (:mod:`app.domain.species_labels`), evitando listas duplicadas.
    """
    return _rotulo_generico(name)


def safe_species_folder(name: str) -> str:
    """Converte o nome da espécie em um nome de pasta seguro.

    Mantém acentos (importantes para exibir ``Beija-flor`` corretamente), mas
    remove separadores de caminho e caracteres reservados do Windows. Espaços
    são normalizados para ``_`` para evitar problemas em scripts/CLI.
    """
    cleaned = _INVALID_NAME_CHARS.sub("_", (name or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    # Nomes reservados do Windows (CON, PRN, AUX, NUL, COM1.., LPT1..).
    if cleaned.casefold().split(".")[0] in {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }:
        cleaned = f"esp_{cleaned}"
    return cleaned[:120] or "especie_sem_nome"


def _json_safe(value: Any) -> Any:
    """Normaliza tipos do NumPy/Torch para JSON puro (métricas do treino)."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, str):
        return value
    try:
        # NumPy escalares e tensores simples.
        if hasattr(value, "item"):
            return _json_safe(value.item())
        return float(value)
    except Exception:
        return str(value)


def _row_to_run(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    """Converte uma linha de ``fine_tune_runs`` em dicionário de API."""
    if row is None:
        return None
    data = dict(row)
    try:
        metrics = json.loads(data.get("metrics_json") or "{}")
    except (TypeError, ValueError):
        metrics = {}
    return {
        "id": data["id"],
        "status": data.get("status") or "queued",
        "base_model": data.get("base_model"),
        "model_path": data.get("model_path"),
        "samples": int(data.get("samples") or 0),
        "classes": int(data.get("classes") or 0),
        "epochs": int(data.get("epochs") or 0),
        "batch": int(data.get("batch") or 0),
        "imgsz": int(data.get("imgsz") or 0),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "message": data.get("message") or "",
        "metrics": metrics if isinstance(metrics, dict) else {},
        "created_at": data.get("created_at") or "",
    }


class ActiveLearningService:
    """Gerencia a fila de amostras e o fine-tuning incremental do Core."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.db_path
        self._lock = threading.Lock()
        self._active_run_id: str | None = None
        self._thread: threading.Thread | None = None
        self._last_dataset_classes: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Fila de amostras
    # ------------------------------------------------------------------ #
    def _best_image_path(self, row: dict[str, Any]) -> Path | None:
        """Recorte tratado > thumbnail oficial > recorte canônico da visita.

        Delega ao resolvedor compartilhado (:mod:`app.ai.visit_media`), que
        valida os caminhos contra as pastas de mídia do ``app-data`` (proteção
        contra *path traversal*) e evita duplicar a regra nos módulos de IA.
        """
        return resolve_visit_image(row, self.settings)

    def _display_species(self, row: dict[str, Any]) -> tuple[str, str | None, str | None]:
        """Nome popular, id e nome científico da visita (catálogo > rótulo)."""
        common = (
            row.get("assigned_species_common_name")
            or row.get("species")
            or ""
        ).strip()
        species_id = row.get("species_id")
        scientific = row.get("assigned_species_scientific_name")
        return common, species_id, scientific

    def enqueue_visit(
        self,
        visit_id: str,
        *,
        species_name: str | None = None,
        species_id: str | None = None,
        source: str = "manual_assignment",
    ) -> dict[str, Any] | None:
        """Copia o recorte da visita para a fila da espécie.

        Devolve ``None`` quando não há imagem ou quando a visita é de um
        visitante não-ave. Rótulos genéricos disparam :class:`ActiveLearningError`
        porque não há o que ensinar ao modelo.

        A operação é idempotente por ``visit_id``: reatribuir a mesma visita
        atualiza a amostra (e move o arquivo para a pasta da nova espécie).
        """
        if not self.settings.active_learning_enabled:
            return None

        repository = VisitRepository(self.db_path)
        row = repository.get(visit_id)
        if row is None:
            raise ActiveLearningError("Visita não encontrada.")
        if (row.get("visitor_kind") or "bird") != "bird":
            return None

        common, catalog_id, scientific = self._display_species(row)
        final_name = (species_name or common).strip()
        if is_generic_species(final_name):
            raise ActiveLearningError(
                "Identifique a espécie desta visita antes de enviá-la ao "
                "treinamento do Bem-Te-Vi Core."
            )

        image_path = self._best_image_path(row)
        if image_path is None:
            logger.info(
                "Amostra ignorada: visita %s não possui imagem tratada", visit_id
            )
            return None

        folder = safe_species_folder(final_name)
        destination_dir = self.settings.training_queue_dir / folder
        destination_dir.mkdir(parents=True, exist_ok=True)
        suffix = image_path.suffix.lower() if image_path.suffix else ".jpg"
        destination = destination_dir / f"{visit_id}{suffix}"

        # Reatribuição: remove o arquivo antigo para não duplicar a amostra em
        # duas classes (o que ensinaria o modelo de forma contraditória).
        with db_session(self.db_path) as conn:
            existing = conn.execute(
                "SELECT image_path FROM training_samples WHERE visit_id = ?",
                (visit_id,),
            ).fetchone()

        if existing is not None:
            old_path = Path(str(existing["image_path"]))
            if old_path != destination and old_path.is_file():
                try:
                    old_path.unlink()
                except OSError:
                    logger.debug("Não foi possível remover amostra antiga %s", old_path)

        try:
            if image_path.resolve() != destination.resolve():
                shutil.copy2(image_path, destination)
        except OSError as exc:
            raise ActiveLearningError(
                "Não foi possível copiar o recorte para a fila de treinamento."
            ) from exc

        sample_id = uuid.uuid4().hex
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO training_samples (
                    id, visit_id, species_name, species_id, source,
                    image_path, confidence, used_in_run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(visit_id) DO UPDATE SET
                    species_name = excluded.species_name,
                    species_id = excluded.species_id,
                    source = excluded.source,
                    image_path = excluded.image_path,
                    confidence = excluded.confidence,
                    created_at = excluded.created_at
                """,
                (
                    sample_id,
                    visit_id,
                    final_name,
                    species_id or catalog_id,
                    source,
                    str(destination),
                    float(row.get("confidence") or 0.0),
                    utc_now(),
                ),
            )
            saved = conn.execute(
                "SELECT * FROM training_samples WHERE visit_id = ?", (visit_id,)
            ).fetchone()

        logger.info(
            "Amostra de aprendizado ativo salva: %s → %s (%s)",
            visit_id,
            final_name,
            source,
        )
        return dict(saved) if saved is not None else None

    def queue_stats(self) -> list[dict[str, Any]]:
        """Amostras por espécie, com elegibilidade para o treino."""
        minimum = int(self.settings.active_learning_min_samples)
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT species_name,
                       COUNT(*) AS samples,
                       MAX(created_at) AS last_sample_at
                FROM training_samples
                GROUP BY species_name
                ORDER BY samples DESC, species_name COLLATE NOCASE ASC
                """
            ).fetchall()
            missing_rows = conn.execute(
                "SELECT species_name, image_path FROM training_samples"
            ).fetchall()

        missing_by_species: dict[str, int] = {}
        for row in missing_rows:
            try:
                if not Path(str(row["image_path"])).is_file():
                    name = str(row["species_name"])
                    missing_by_species[name] = missing_by_species.get(name, 0) + 1
            except OSError:
                name = str(row["species_name"])
                missing_by_species[name] = missing_by_species.get(name, 0) + 1

        stats: list[dict[str, Any]] = []
        for row in rows:
            samples = int(row["samples"] or 0)
            name = str(row["species_name"])
            stats.append(
                {
                    "species_name": name,
                    "samples": samples,
                    "eligible": samples >= minimum,
                    "missing_files": missing_by_species.get(name, 0),
                    "last_sample_at": row["last_sample_at"],
                }
            )
        return stats

    def total_samples(self) -> int:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM training_samples"
            ).fetchone()
            return int(row["total"]) if row else 0

    def repair_sample_paths(self) -> int:
        """Reaponta amostras cujo arquivo ficou na pasta antiga do projeto.

        ``training_samples.image_path`` guarda caminhos **absolutos**. Se o
        projeto for movido/copiado (ex.: ``Documentos`` → ``C:\\DevJansen``),
        todas as amostras antigas passam a apontar para um caminho inexistente
        e a fila de aprendizado ativo fica "vazia" no painel.

        O reparo é conservador e idempotente: só altera linhas cujo arquivo
        atual não existe **e** cujo nome é encontrado em
        ``app-data/training_queue``. Nenhuma amostra é apagada.

        Devolve a quantidade de linhas corrigidas.
        """
        queue_dir = self.settings.training_queue_dir
        if not queue_dir.is_dir():
            return 0

        # Índice nome do arquivo → caminho atual (a fila é pequena e plana por
        # espécie, então o custo é desprezível no startup).
        por_nome: dict[str, Path] = {}
        for candidate in queue_dir.rglob("*"):
            try:
                if candidate.is_file():
                    por_nome.setdefault(candidate.name, candidate)
            except OSError:
                continue

        repaired = 0
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, image_path FROM training_samples"
            ).fetchall()
            for row in rows:
                try:
                    current = Path(str(row["image_path"]))
                    if current.is_file():
                        continue
                    match = por_nome.get(current.name)
                    if match is None:
                        continue
                    conn.execute(
                        "UPDATE training_samples SET image_path = ? WHERE id = ?",
                        (str(match), row["id"]),
                    )
                    repaired += 1
                except OSError:
                    continue

        if repaired:
            logger.info(
                "Aprendizado ativo: %s caminho(s) de amostra reparado(s) após "
                "mudança de pasta do projeto.",
                repaired,
            )
        return repaired

    # ------------------------------------------------------------------ #
    # Métricas e status
    # ------------------------------------------------------------------ #
    def last_run(self) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM fine_tune_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return _row_to_run(row)

    def running(self) -> bool:
        with self._lock:
            return self._active_run_id is not None

    def status(self) -> dict[str, Any]:
        """Retrato pronto para o painel de Configurações."""
        queue = self.queue_stats()
        total = sum(item["samples"] for item in queue)
        eligible = sum(1 for item in queue if item["eligible"])
        last = self.last_run()
        model_path = self.settings.fine_tuned_model_path
        model_available = model_path.is_file()
        model_size = model_path.stat().st_size if model_available else 0
        model_trained_at = None
        if model_available:
            try:
                model_trained_at = datetime.fromtimestamp(
                    model_path.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            except OSError:
                model_trained_at = None

        notes: list[str] = []
        if not self.settings.active_learning_enabled:
            notes.append("Aprendizado ativo desligado em ACTIVE_LEARNING_ENABLED.")
        if importlib.util.find_spec("ultralytics") is None:
            notes.append(
                "Ultralytics não instalado: a fila funciona, mas o treino está "
                "indisponível."
            )
        elif importlib.util.find_spec("torch") is None:
            notes.append("PyTorch não instalado: o treino está indisponível.")
        if eligible < 2:
            notes.append(
                "São necessárias pelo menos duas espécies com "
                f"{self.settings.active_learning_min_samples}+ amostras cada "
                "para o fine-tuning."
            )
        if model_available:
            notes.append(
                "Modelo treinado disponível: o pipeline já classifica espécies "
                "com o Bem-Te-Vi Core."
            )

        return {
            "enabled": bool(self.settings.active_learning_enabled),
            "running": self.running(),
            "total_samples": total,
            "eligible_classes": eligible,
            "min_samples": int(self.settings.active_learning_min_samples),
            "queue": queue,
            "last_run": last,
            "model_available": model_available,
            "model_path": str(model_path) if model_available else None,
            "model_size_bytes": model_size,
            "model_trained_at": model_trained_at,
            "notes": notes,
        }

    # ------------------------------------------------------------------ #
    # Fine-tuning
    # ------------------------------------------------------------------ #
    def _prepare_dataset(self) -> tuple[Path, dict[str, str], int, int]:
        """Monta ``train/`` e ``val/`` a partir da fila de amostras.

        Devolve ``(diretório, mapa pasta→espécie original, amostras, classes)``.
        A divisão treino/validação é determinística (hash do nome do arquivo),
        para que execuções repetidas comparem os mesmos dados.
        """
        minimum = int(self.settings.active_learning_min_samples)
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT species_name, image_path
                FROM training_samples
                ORDER BY species_name COLLATE NOCASE ASC, created_at ASC
                """
            ).fetchall()

        grouped: dict[str, list[Path]] = {}
        original_names: dict[str, str] = {}
        for row in rows:
            name = str(row["species_name"] or "").strip()
            if is_generic_species(name):
                continue
            path = Path(str(row["image_path"]))
            if not path.is_file():
                continue
            folder = safe_species_folder(name)
            original_names.setdefault(folder, name)
            grouped.setdefault(folder, []).append(path)

        selected = {
            folder: paths
            for folder, paths in grouped.items()
            if len(paths) >= minimum
        }
        if len(selected) < 2:
            raise ActiveLearningError(
                "São necessárias pelo menos duas espécies com "
                f"{minimum} amostras válidas cada para iniciar o fine-tuning."
            )

        dataset_dir = self.settings.fine_tune_dataset_dir
        shutil.rmtree(dataset_dir, ignore_errors=True)
        (dataset_dir / "train").mkdir(parents=True, exist_ok=True)
        (dataset_dir / "val").mkdir(parents=True, exist_ok=True)

        total = 0
        for folder, paths in selected.items():
            ordered = sorted(
                paths,
                key=lambda item: hashlib.sha1(
                    f"{folder}:{item.name}".encode("utf-8", "ignore")
                ).hexdigest(),
            )
            val_count = max(1, int(round(len(ordered) * 0.2)))
            val_count = min(val_count, max(1, len(ordered) - 1))
            train_paths = ordered[:-val_count]
            val_paths = ordered[-val_count:]

            for split, split_paths in (("train", train_paths), ("val", val_paths)):
                class_dir = dataset_dir / split / folder
                class_dir.mkdir(parents=True, exist_ok=True)
                for index, source in enumerate(split_paths):
                    suffix = source.suffix.lower() if source.suffix else ".jpg"
                    destination = class_dir / f"{index:05d}_{source.stem}{suffix}"
                    try:
                        shutil.copy2(source, destination)
                    except OSError:
                        logger.warning(
                            "Amostra ilegível ignorada no dataset: %s", source,
                            exc_info=True,
                        )
                        continue
                    total += 1

        # O Ultralytics exige que o diretório de dados contenha as pastas
        # train/ e val/; o mapa abaixo preserva o nome acentuado original.
        (dataset_dir / "labels.json").write_text(
            json.dumps(original_names, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._last_dataset_classes = original_names
        return dataset_dir, original_names, total, len(selected)

    def _set_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        message: str | None = None,
        model_path: str | None = None,
        metrics: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> None:
        """Atualiza o registro da execução de treino (thread-safe via SQLite)."""
        fields: list[str] = []
        params: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if message is not None:
            fields.append("message = ?")
            params.append(message)
        if model_path is not None:
            fields.append("model_path = ?")
            params.append(model_path)
        if metrics is not None:
            fields.append("metrics_json = ?")
            params.append(json.dumps(_json_safe(metrics), ensure_ascii=False))
        if finished:
            fields.append("finished_at = ?")
            params.append(utc_now())
        if not fields:
            return
        params.append(run_id)
        with db_session(self.db_path) as conn:
            conn.execute(
                f"UPDATE fine_tune_runs SET {', '.join(fields)} WHERE id = ?",
                params,
            )

    def _resolve_device(self) -> Any:
        device = (self.settings.yolo_device or "auto").strip()
        if device.lower() in {"", "auto"}:
            return None
        return device

    def _train_worker(self, run_id: str) -> None:
        """Corpo do treino (executado em thread dedicada)."""
        settings = self.settings
        try:
            self._set_run(
                run_id,
                status="running",
                message="Preparando o dataset a partir da fila de amostras…",
            )
            dataset_dir, original_names, samples, classes = self._prepare_dataset()
            if samples <= 0:
                raise ActiveLearningError(
                    "Nenhuma amostra válida foi encontrada na fila."
                )

            from ultralytics import YOLO  # import tardio: opcional e pesado

            # Fine-tuning **incremental**: se já existe um modelo do Core, ele é
            # o ponto de partida; senão, usa-se o backbone leve pré-treinado.
            base_path = (
                settings.fine_tuned_model_path
                if settings.fine_tuned_model_path.is_file()
                else settings.fine_tune_base_model
            )
            self._set_run(
                run_id,
                message=(
                    f"Carregando {Path(str(base_path)).name} e treinando "
                    f"{classes} classes por {settings.fine_tune_epochs} épocas…"
                ),
            )
            model = YOLO(str(base_path))
            train_kwargs: dict[str, Any] = {
                "data": str(dataset_dir),
                "epochs": int(settings.fine_tune_epochs),
                "batch": int(settings.fine_tune_batch),
                "imgsz": int(settings.fine_tune_imgsz),
                "project": str(settings.ai_models_dir),
                "name": "runs",
                "exist_ok": True,
                "pretrained": True,
                "plots": False,
                "verbose": False,
                "workers": 0,
                "seed": 42,
            }
            device = self._resolve_device()
            if device is not None:
                train_kwargs["device"] = device

            results = model.train(**train_kwargs)

            # Localiza o melhor checkpoint gerado pelo Ultralytics.
            weights_candidates: list[Path] = []
            save_dir = getattr(results, "save_dir", None)
            if save_dir:
                weights_candidates.append(Path(str(save_dir)) / "weights" / "best.pt")
            trainer = getattr(model, "trainer", None)
            best = getattr(trainer, "best", None)
            if best:
                weights_candidates.append(Path(str(best)))
            # Varredura de segurança (versões diferentes do Ultralytics).
            weights_candidates.extend(
                sorted(settings.ai_models_dir.glob("runs/**/weights/best.pt"))
            )
            best_path = next(
                (candidate for candidate in weights_candidates if candidate.is_file()),
                None,
            )
            if best_path is None:
                raise ActiveLearningError(
                    "O treino terminou, mas o checkpoint best.pt não foi "
                    "encontrado."
                )

            settings.ai_models_dir.mkdir(parents=True, exist_ok=True)
            temporary = settings.fine_tuned_model_path.with_suffix(".tmp.pt")
            shutil.copy2(best_path, temporary)
            temporary.replace(settings.fine_tuned_model_path)

            # Mapa de rótulos: o YOLO usa os nomes das pastas (sem acento
            # quando necessário); aqui recuperamos o nome original da espécie.
            names = getattr(model, "names", {}) or {}
            labels_payload = {
                "classes": original_names,
                "names": {str(key): str(value) for key, value in dict(names).items()},
                "trained_at": utc_now(),
                "samples": samples,
            }
            settings.fine_tuned_labels_path.write_text(
                json.dumps(labels_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            metrics: dict[str, Any] = {}
            results_dict = getattr(results, "results_dict", None)
            if isinstance(results_dict, dict):
                metrics = _json_safe(results_dict)
            elif hasattr(results, "metrics"):
                metrics = _json_safe(getattr(results, "metrics"))

            self._set_run(
                run_id,
                status="completed",
                message=(
                    f"Modelo otimizado com {samples} amostras e {classes} "
                    "espécies. Pipeline atualizado automaticamente."
                ),
                model_path=str(settings.fine_tuned_model_path),
                metrics=metrics if isinstance(metrics, dict) else {},
                finished=True,
            )

            # Recarrega o classificador compartilhado do pipeline ao vivo.
            try:
                from app.infra.ai.species_classifier import (
                    reload_default_species_classifier,
                )

                reload_default_species_classifier()
            except Exception:
                logger.exception("Falha ao recarregar o classificador fine-tunado")

            logger.info(
                "Fine-tuning concluído: %s (%s amostras, %s classes)",
                settings.fine_tuned_model_path,
                samples,
                classes,
            )
        except Exception as exc:
            logger.exception("Fine-tuning do Bem-Te-Vi Core falhou")
            self._set_run(
                run_id,
                status="failed",
                message=str(exc) or "Falha inesperada durante o fine-tuning.",
                finished=True,
            )
        finally:
            with self._lock:
                self._active_run_id = None

    def start_fine_tuning(self) -> dict[str, Any]:
        """Valida a fila e dispara o treino em segundo plano.

        Levanta :class:`ActiveLearningError` quando já há um treino em
        andamento ou quando a fila não tem espécies suficientes.
        """
        if not self.settings.active_learning_enabled:
            raise ActiveLearningError(
                "O aprendizado ativo está desligado (ACTIVE_LEARNING_ENABLED)."
            )
        if importlib.util.find_spec("ultralytics") is None:
            raise ActiveLearningError(
                "Instale o pacote 'ultralytics' para habilitar o fine-tuning."
            )
        with self._lock:
            if self._active_run_id is not None:
                raise ActiveLearningError(
                    "Já existe uma otimização do Bem-Te-Vi Core em andamento."
                )
            # Reserva a vaga antes de tocar no banco (evita corrida entre cliques).
            self._active_run_id = "starting"

        run_id = uuid.uuid4().hex
        try:
            queue = self.queue_stats()
            eligible = [item for item in queue if item["eligible"]]
            if len(eligible) < 2:
                raise ActiveLearningError(
                    "São necessárias pelo menos duas espécies com "
                    f"{self.settings.active_learning_min_samples} amostras "
                    "válidas cada para iniciar o fine-tuning."
                )
            samples = sum(int(item["samples"]) for item in eligible)
            now = utc_now()
            with db_session(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO fine_tune_runs (
                        id, status, base_model, model_path, samples, classes,
                        epochs, batch, imgsz, started_at, finished_at, message,
                        metrics_json, created_at
                    ) VALUES (?, 'queued', ?, NULL, ?, ?, ?, ?, ?, ?, NULL, ?, '{}', ?)
                    """,
                    (
                        run_id,
                        str(self.settings.fine_tuned_model_path)
                        if self.settings.fine_tuned_model_path.is_file()
                        else self.settings.fine_tune_base_model,
                        samples,
                        len(eligible),
                        int(self.settings.fine_tune_epochs),
                        int(self.settings.fine_tune_batch),
                        int(self.settings.fine_tune_imgsz),
                        now,
                        "Otimização agendada: aguardando o início do treino.",
                        now,
                    ),
                )
            with self._lock:
                self._active_run_id = run_id
            thread = threading.Thread(
                target=self._train_worker,
                args=(run_id,),
                name="bem-te-vi-core-fine-tune",
                daemon=True,
            )
            self._thread = thread
            thread.start()
        except Exception:
            with self._lock:
                self._active_run_id = None
            raise

        return self.status()


_service: ActiveLearningService | None = None
_service_lock = threading.Lock()


def get_active_learning_service() -> ActiveLearningService:
    """Instância única (singleton) do serviço de aprendizado ativo."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = ActiveLearningService()
    return _service


__all__ = [
    "ActiveLearningError",
    "ActiveLearningService",
    "get_active_learning_service",
    "is_generic_species",
    "safe_species_folder",
]
