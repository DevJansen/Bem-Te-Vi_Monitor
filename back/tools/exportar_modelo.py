"""Utilitário de linha de comando para exportar o YOLOv8 otimizado (Edge AI).

Gera o artefato de inferência mais rápido para o hardware do usuário:

- ``onnx``      → portável; acelera em CPU (OpenVINO/ONNX Runtime) e GPU.
- ``engine``    → TensorRT; máxima velocidade em GPUs NVIDIA (FP16/INT8).
- ``openvino``  → Intel CPU/iGPU.
- ``torchscript`` → empacotamento portátil do PyTorch.

Após exportar, o Bem-Te-Vi passa a usar o artefato automaticamente (com
``YOLO_ACCELERATION=auto``), desde que o arquivo fique ao lado do ``.pt``.

Uso (a partir da pasta ``back``, com o ambiente virtual ativo)::

    python -m tools.exportar_modelo --formato onnx
    python -m tools.exportar_modelo --formato engine --half
    python -m tools.exportar_modelo --formato engine --int8   # requer GPU NVIDIA

O modelo de origem é lido de ``YOLO_MODEL`` (padrão ``yolov8n.pt``).
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.core.config import get_settings
from app.infra.ai.model_loader import exportar_modelo


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exporta o modelo YOLOv8 para um formato otimizado (Edge AI)."
    )
    parser.add_argument(
        "--modelo",
        default=None,
        help="Modelo de origem (padrão: YOLO_MODEL do .env ou yolov8n.pt).",
    )
    parser.add_argument(
        "--formato",
        default="onnx",
        choices=["onnx", "engine", "openvino", "torchscript"],
        help="Formato de destino (padrão: onnx).",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=None,
        help="Tamanho de entrada em px (padrão: YOLO_IMGSZ do .env ou 640).",
    )
    parser.add_argument(
        "--half",
        action="store_true",
        help="Exporta em FP16 (recomendado em GPU NVIDIA).",
    )
    parser.add_argument(
        "--int8",
        action="store_true",
        help="Quantiza em INT8 (requer GPU NVIDIA e dados de calibração).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args(argv)
    settings = get_settings()
    modelo = args.modelo or settings.yolo_model
    imgsz = args.imgsz or settings.yolo_imgsz

    try:
        caminho = exportar_modelo(
            modelo,
            formato=args.formato,
            imgsz=imgsz,
            half=args.half,
            int8=args.int8,
        )
    except Exception as exc:  # noqa: BLE001 — mensagem amigável ao usuário
        print(f"Falha ao exportar o modelo: {exc}", file=sys.stderr)
        return 1

    print(f"Artefato gerado: {caminho}")
    print(
        "Pronto! O Bem-Te-Vi usará este arquivo automaticamente "
        "(YOLO_ACCELERATION=auto)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
