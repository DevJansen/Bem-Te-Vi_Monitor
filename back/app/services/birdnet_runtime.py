"""Runtime TFLite usado pelo BirdNET.

O ``birdnetlib`` importa ``tflite_runtime.interpreter`` e, caso não o encontre,
recorre a ``tensorflow.lite``. Em algumas plataformas (por exemplo, Windows com
Python 3.14) nenhum dos dois possui wheels publicados, mas o ``ai-edge-litert``
— runtime TFLite oficial e atual do Google — está disponível.

Este módulo garante que ``tflite_runtime.interpreter`` seja importável, aliasando
o interpretador do ``ai_edge_litert`` quando necessário. Ele deve ser chamado
**antes** de qualquer ``import birdnetlib``.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types

logger = logging.getLogger(__name__)

# Runtime alternativo usado quando ``tflite_runtime``/``tensorflow`` não existem.
_FALLBACK_RUNTIME = "ai_edge_litert"

_shim_installed = False


def _module_available(name: str) -> bool:
    """Indica se um módulo pode ser importado, sem importá-lo de fato."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def available_runtime() -> str | None:
    """Nome do runtime TFLite disponível no ambiente, ou ``None``.

    A ordem reflete a preferência do próprio ``birdnetlib``: primeiro o
    ``tflite_runtime``, depois o ``tensorflow`` e, por fim, o ``ai-edge-litert``.
    """
    for name in ("tflite_runtime", "tensorflow", _FALLBACK_RUNTIME):
        if _module_available(name):
            return name
    return None


def ensure_tflite_runtime() -> str | None:
    """Garante que ``tflite_runtime.interpreter`` seja importável.

    Quando nem ``tflite_runtime`` nem ``tensorflow`` existem, mas o
    ``ai-edge-litert`` está instalado, registra um módulo ``tflite_runtime``
    apontando para o interpretador do ``ai_edge_litert``.

    Retorna o nome do runtime efetivamente disponível, ou ``None`` quando nenhum
    runtime TFLite estiver instalado.
    """
    global _shim_installed

    # Já existe um runtime "nativo" — nada a fazer.
    if _module_available("tflite_runtime") or _module_available("tensorflow"):
        return available_runtime()

    if not _module_available(_FALLBACK_RUNTIME):
        return None

    if not _shim_installed:
        try:
            from ai_edge_litert import interpreter as litert_interpreter
        except Exception:  # pragma: no cover - depende do ambiente de instalação
            logger.exception("Falha ao importar o 'ai_edge_litert'")
            return None

        module = types.ModuleType("tflite_runtime")
        module.interpreter = litert_interpreter  # type: ignore[attr-defined]
        sys.modules.setdefault("tflite_runtime", module)
        sys.modules.setdefault("tflite_runtime.interpreter", litert_interpreter)
        _shim_installed = True
        logger.info(
            "BirdNET: usando 'ai-edge-litert' como runtime TFLite "
            "(shim de 'tflite_runtime' aplicado)."
        )

    return _FALLBACK_RUNTIME
