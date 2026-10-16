"""Carregamento otimizado do YOLOv8 para Edge AI (TensorRT / ONNX / FP16).

Estratégia de aceleração (em ordem de preferência, conforme disponibilidade):

1. **TensorRT** (``.engine``) — máxima velocidade em GPUs NVIDIA (FP16/INT8).
2. **ONNX** (``.onnx``) — portável; acelera em CPU (OpenVINO/ONNX Runtime) e GPU.
3. **PyTorch** (``.pt``) — padrão; usa **FP16** automaticamente em GPU CUDA.

O módulo apenas *carrega* o artefato certo e resolve os parâmetros de inferência
(dispositivo, half, tamanho de imagem). A geração dos artefatos otimizados é
feita pelo utilitário ``back/tools/exportar_modelo.py`` (ver README).

Nada aqui quebra a instalação padrão: sem GPU e sem artefatos exportados, o
sistema cai no ``.pt`` em CPU, exatamente como antes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Backends suportados.
BACKEND_TENSORRT = "tensorrt"
BACKEND_ONNX = "onnx"
BACKEND_PYTORCH = "pytorch"

# Valores aceitos em YOLO_ACCELERATION.
_MODOS_AUTO = {"", "auto", "automatico", "automático"}


@dataclass
class ModeloOtimizado:
    """Modelo carregado + parâmetros de inferência resolvidos."""

    modelo: object
    fonte: str
    backend: str
    device: str
    half: bool
    imgsz: int
    # Avisos/observações de aceleração (exibidos na telemetria/diagnóstico).
    observacoes: list[str] = field(default_factory=list)

    def predict_kwargs(self) -> dict[str, object]:
        """Argumentos comuns de ``model.predict`` para inferência rápida."""
        kwargs: dict[str, object] = {
            "device": self.device,
            "imgsz": self.imgsz,
        }
        # ``half`` só é válido no backend PyTorch em CUDA; TRT/ONNX já embutem
        # a precisão na exportação.
        if self.backend == BACKEND_PYTORCH and self.half:
            kwargs["half"] = True
        return kwargs


def cuda_disponivel() -> bool:
    """Indica se existe uma GPU CUDA utilizável pelo PyTorch."""
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def dispositivo_efetivo(configurado: str | None) -> str:
    """Resolve ``auto`` para a melhor opção disponível (GPU ``0`` ou ``cpu``)."""
    valor = str(configurado or "auto").strip().lower()
    if valor in _MODOS_AUTO:
        return "0" if cuda_disponivel() else "cpu"
    return valor or "cpu"


def resolver_artefato(model_name: str, aceleracao: str | None = "auto") -> tuple[str, str]:
    """Escolhe o melhor artefato disponível para ``model_name``.

    Devolve ``(caminho, backend)``. Se o próprio ``model_name`` já apontar para
    um ``.engine``/``.onnx``, respeita a escolha. Caso contrário, procura um
    artefato otimizado ao lado do ``.pt`` conforme ``aceleracao``.
    """
    caminho = Path(model_name)
    sufixo = caminho.suffix.lower()

    if sufixo == ".engine":
        return model_name, BACKEND_TENSORRT
    if sufixo == ".onnx":
        return model_name, BACKEND_ONNX

    modo = str(aceleracao or "auto").strip().lower()
    base = caminho.with_suffix("")
    engine = Path(f"{base}.engine")
    onnx = Path(f"{base}.onnx")

    quer_engine = modo in _MODOS_AUTO or modo in {"engine", "tensorrt", "trt"}
    quer_onnx = modo in _MODOS_AUTO or modo in {"onnx"}

    if quer_engine and engine.is_file():
        return str(engine), BACKEND_TENSORRT
    if quer_onnx and onnx.is_file():
        return str(onnx), BACKEND_ONNX
    return model_name, BACKEND_PYTORCH


def carregar_modelo(
    model_name: str,
    *,
    aceleracao: str | None = "auto",
    device: str | None = "auto",
    half: bool = False,
    imgsz: int = 640,
) -> ModeloOtimizado:
    """Carrega o modelo YOLO pelo melhor backend disponível.

    Levanta a exceção original do Ultralytics se o carregamento falhar (o
    detector trata e registra o erro).
    """
    from ultralytics import YOLO

    fonte, backend = resolver_artefato(model_name, aceleracao)
    dispositivo = dispositivo_efetivo(device)
    observacoes: list[str] = []

    usar_half = bool(half) and backend == BACKEND_PYTORCH and dispositivo != "cpu"
    if bool(half) and backend == BACKEND_PYTORCH and dispositivo == "cpu":
        observacoes.append("FP16 ignorado em CPU (sem ganho e sem suporte estável).")

    if backend == BACKEND_TENSORRT:
        observacoes.append("TensorRT ativo (máxima velocidade em GPU NVIDIA).")
    elif backend == BACKEND_ONNX:
        observacoes.append("ONNX ativo (inferência acelerada e portável).")
    elif usar_half:
        observacoes.append("PyTorch FP16 ativo (GPU CUDA).")
    else:
        observacoes.append("PyTorch FP32 (CPU).")

    logger.info(
        "Carregando YOLO %s (backend=%s device=%s half=%s imgsz=%s)",
        fonte,
        backend,
        dispositivo,
        usar_half,
        imgsz,
    )
    modelo = YOLO(fonte)
    return ModeloOtimizado(
        modelo=modelo,
        fonte=fonte,
        backend=backend,
        device=dispositivo,
        half=usar_half,
        imgsz=int(imgsz),
        observacoes=observacoes,
    )


def exportar_modelo(
    model_name: str,
    *,
    formato: str = "onnx",
    imgsz: int = 640,
    half: bool = False,
    int8: bool = False,
) -> str:
    """Exporta o modelo para um artefato otimizado e devolve o caminho.

    Usado pelo utilitário de linha de comando. ``formato`` aceita ``onnx``,
    ``engine`` (TensorRT), ``openvino`` ou ``torchscript``. Para TensorRT INT8,
    informe ``int8=True`` (requer GPU NVIDIA e dados de calibração).
    """
    from ultralytics import YOLO

    logger.info(
        "Exportando %s para %s (imgsz=%s half=%s int8=%s)",
        model_name,
        formato,
        imgsz,
        half,
        int8,
    )
    modelo = YOLO(model_name)
    caminho = modelo.export(
        format=formato,
        imgsz=int(imgsz),
        half=bool(half),
        int8=bool(int8),
    )
    return str(caminho)
