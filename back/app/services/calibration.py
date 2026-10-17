"""Serviço de calibração de sensibilidade, persistido em JSON local.

Responsabilidades:
- Guardar os parâmetros de calibração em `app-data/calibration.json` de forma
  atômica e segura (nunca deixa o arquivo corrompido).
- Oferecer perfis prontos ("Passarinhos Parados" e "Alta Movimentação") para o
  usuário não técnico, além de ajustes manuais (modo "custom").
- Aplicar o limiar de confiança no detector YOLO em tempo de execução, sem
  reiniciar o backend. Os demais parâmetros (permanência e movimento) são lidos
  pelos pipelines a cada ciclo.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from app.core.config import get_settings
from app.domain.models import (
    CalibrationOut,
    CalibrationProfile,
    CalibrationUpdate,
    NightVisionMode,
)

logger = logging.getLogger(__name__)

# Faixa aceita para o limiar de confiança (mantida em sincronia com o detector).
_CONFIDENCE_MIN = 0.05
_CONFIDENCE_MAX = 1.0


def _clamp_confidence(value: float) -> float:
    """Limita o limiar de confiança à faixa suportada pelo detector."""
    return min(_CONFIDENCE_MAX, max(_CONFIDENCE_MIN, float(value)))

# Campos numéricos calibráveis (usados para detectar ajustes manuais).
_NUMERIC_FIELDS = (
    "yolo_confidence",
    "object_persistence_time",
    "motion_sensitivity",
)

# Valores pré-definidos de cada perfil, explicados no painel web.
PROFILE_PRESETS: dict[CalibrationProfile, dict[str, float]] = {
    # Passarinhos Parados / Alimentador (recomendado): confiança menor para
    # pegar aves distantes e permanência longa para aves imóveis comendo.
    CalibrationProfile.STATIONARY: {
        "yolo_confidence": 0.22,
        "object_persistence_time": 10.0,
        "motion_sensitivity": 0.80,
    },
    # Alta Movimentação / Voo Rápido: confiança maior (menos ruído) e
    # permanência curta, priorizando capturas rápidas.
    CalibrationProfile.FAST_MOTION: {
        "yolo_confidence": 0.45,
        "object_persistence_time": 3.0,
        "motion_sensitivity": 0.55,
    },
}

RECOMMENDED_PROFILE = CalibrationProfile.STATIONARY


class CalibrationService:
    """Fonte única de verdade da calibração (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings = get_settings()
        self._path: Path = self._settings.app_data_dir / "calibration.json"
        self._current = self._load()
        self._apply_runtime()

    # ------------------------------------------------------------------ #
    # Leitura
    # ------------------------------------------------------------------ #
    def current(self) -> CalibrationOut:
        """Retorna uma cópia dos parâmetros ativos (rápido, em memória)."""
        with self._lock:
            return self._current.model_copy()

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------ #
    # Atualização
    # ------------------------------------------------------------------ #
    def update(self, payload: CalibrationUpdate) -> CalibrationOut:
        """Aplica um perfil e/ou ajustes manuais, salva e aplica em runtime."""
        with self._lock:
            values = self._current.model_dump()
            profile = payload.profile

            # 1) Perfil pronto define a base dos valores.
            if profile in PROFILE_PRESETS:
                values.update(PROFILE_PRESETS[profile])

            # 2) Ajustes manuais têm precedência sobre o perfil.
            for field in _NUMERIC_FIELDS:
                override = getattr(payload, field)
                if override is not None:
                    values[field] = float(override)

            # 2b) Visão noturna e fauna noturna (independentes do perfil numérico).
            if payload.night_vision_mode is not None:
                values["night_vision_mode"] = payload.night_vision_mode
            if payload.night_vision_threshold is not None:
                values["night_vision_threshold"] = float(
                    payload.night_vision_threshold
                )
            if payload.night_fauna_enabled is not None:
                values["night_fauna_enabled"] = bool(payload.night_fauna_enabled)

            # 3) Define o rótulo final do perfil.
            values["profile"] = self._resolve_profile(profile, values, payload)

            # 4) Normaliza os limites aceitos.
            values["yolo_confidence"] = _clamp_confidence(values["yolo_confidence"])
            values["object_persistence_time"] = min(
                30.0, max(0.0, float(values["object_persistence_time"]))
            )
            values["motion_sensitivity"] = min(
                1.0, max(0.0, float(values["motion_sensitivity"]))
            )
            values["night_vision_threshold"] = min(
                255.0, max(0.0, float(values.get("night_vision_threshold", 60.0)))
            )

            updated = CalibrationOut(**values)
            self._write(updated)
            self._current = updated
            self._apply_runtime()
            logger.info(
                "Calibração atualizada: perfil=%s conf=%.2f persistência=%.1fs movimento=%.2f noite=%s fauna=%s",
                updated.profile.value,
                updated.yolo_confidence,
                updated.object_persistence_time,
                updated.motion_sensitivity,
                updated.night_vision_mode.value,
                updated.night_fauna_enabled,
            )
            return updated.model_copy()

    def _resolve_profile(
        self,
        requested: CalibrationProfile | None,
        values: dict,
        payload: CalibrationUpdate,
    ) -> CalibrationProfile:
        """Marca como 'custom' quando o usuário ajusta sliders além do perfil.

        Alterações apenas de visão noturna (sem tocar nos controles numéricos)
        preservam o perfil atual, para não sinalizar um ajuste que não ocorreu.
        """
        numeric_overrides = {
            field: getattr(payload, field)
            for field in _NUMERIC_FIELDS
            if getattr(payload, field) is not None
        }
        if requested == CalibrationProfile.CUSTOM:
            return CalibrationProfile.CUSTOM
        if requested is None:
            # Sem perfil informado: preserva o atual se não houve ajuste numérico.
            return self._current.profile if not numeric_overrides else CalibrationProfile.CUSTOM
        preset = PROFILE_PRESETS.get(requested)
        if preset is None:
            return CalibrationProfile.CUSTOM
        for field, override in numeric_overrides.items():
            if abs(float(override) - preset[field]) > 1e-9:
                return CalibrationProfile.CUSTOM
        return requested

    # ------------------------------------------------------------------ #
    # Persistência e runtime
    # ------------------------------------------------------------------ #
    def _defaults(self) -> CalibrationOut:
        """Valores iniciais vindos do .env (alta sensibilidade por padrão).

        Quando os padrões coincidem com o perfil recomendado, o rótulo já vem
        apontando para ele — assim o painel mostra a configuração sensível como
        ativa sem o usuário precisar mexer em nada.
        """
        confianca = _clamp_confidence(self._settings.yolo_confidence)
        persistencia = min(30.0, max(0.0, self._settings.object_persistence_time))
        movimento = min(1.0, max(0.0, self._settings.motion_sensitivity))
        preset = PROFILE_PRESETS[RECOMMENDED_PROFILE]
        coincide = (
            abs(confianca - preset["yolo_confidence"]) < 1e-9
            and abs(persistencia - preset["object_persistence_time"]) < 1e-9
            and abs(movimento - preset["motion_sensitivity"]) < 1e-9
        )
        return CalibrationOut(
            yolo_confidence=confianca,
            object_persistence_time=persistencia,
            motion_sensitivity=movimento,
            night_vision_mode=NightVisionMode.normalize(self._settings.night_vision_mode),
            night_vision_threshold=min(
                255.0, max(0.0, float(self._settings.night_vision_threshold))
            ),
            night_fauna_enabled=bool(self._settings.night_fauna_enabled),
            profile=RECOMMENDED_PROFILE if coincide else CalibrationProfile.CUSTOM,
            recommended_profile=RECOMMENDED_PROFILE,
        )

    def _load(self) -> CalibrationOut:
        defaults = self._defaults()
        try:
            if self._path.is_file():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                merged = {**defaults.model_dump(), **data}
                return CalibrationOut.model_validate(merged)
        except Exception:
            logger.exception("Falha ao ler calibration.json; usando padrões do .env")
        return defaults

    def _write(self, settings: CalibrationOut) -> None:
        """Grava o JSON de forma atômica (escreve em temporário e substitui)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=".calibration-",
                suffix=".tmp",
                dir=self._path.parent,
                text=True,
            )
            os.close(descriptor)
            temporary = Path(name)
            temporary.write_text(
                json.dumps(settings.model_dump(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
            temporary = None
        except Exception:
            logger.exception("Falha ao salvar calibration.json")
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _apply_runtime(self) -> None:
        """Empurra o limiar de confiança para o detector YOLO já carregado."""
        try:
            from app.infra.ai.detector import get_bird_detector

            get_bird_detector().set_confidence(self._current.yolo_confidence)
        except Exception:
            logger.exception("Falha ao aplicar a calibração no detector")


_service: CalibrationService | None = None
_service_lock = threading.Lock()


def get_calibration_service() -> CalibrationService:
    global _service
    with _service_lock:
        if _service is None:
            _service = CalibrationService()
        return _service
