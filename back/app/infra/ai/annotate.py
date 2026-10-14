"""Desenho de bounding boxes de aves sobre frames OpenCV."""

from __future__ import annotations

import cv2
import numpy as np

from app.infra.ai.detector import Detection

# Verde esmeralda em BGR (conforme especificação)
EMERALD_BGR = (16, 200, 80)
BOX_THICKNESS = 2
LABEL_PT = "Pássaro"


def draw_bird_detections(
    frame: np.ndarray,
    detections: list[Detection],
    *,
    min_confidence: float | None = None,
) -> np.ndarray:
    """
    Retorna cópia do frame com retângulos e rótulos desenhados.

    Rótulo: \"Pássaro: 87%\" com fundo preenchido acima da caixa.
    """
    if frame is None or frame.size == 0:
        return frame

    annotated = frame.copy()
    height, width = annotated.shape[:2]

    for det in detections:
        if min_confidence is not None and det.confidence < min_confidence:
            continue

        x1, y1, x2, y2 = det.bbox
        x1_i = max(0, min(width - 1, int(round(x1))))
        y1_i = max(0, min(height - 1, int(round(y1))))
        x2_i = max(0, min(width - 1, int(round(x2))))
        y2_i = max(0, min(height - 1, int(round(y2))))
        if x2_i <= x1_i or y2_i <= y1_i:
            continue

        cv2.rectangle(
            annotated,
            (x1_i, y1_i),
            (x2_i, y2_i),
            EMERALD_BGR,
            BOX_THICKNESS,
            lineType=cv2.LINE_AA,
        )

        pct = int(round(det.confidence * 100))
        label = f"{LABEL_PT}: {pct}%"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        font_thickness = 1
        (tw, th), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)

        # Fundo do rótulo no topo da caixa
        pad = 4
        label_top = max(0, y1_i - th - baseline - pad * 2)
        label_bottom = max(th + baseline + pad * 2, y1_i)
        label_left = x1_i
        label_right = min(width - 1, x1_i + tw + pad * 2)

        cv2.rectangle(
            annotated,
            (label_left, label_top),
            (label_right, label_bottom),
            EMERALD_BGR,
            thickness=-1,
        )
        text_y = label_bottom - pad - baseline
        cv2.putText(
            annotated,
            label,
            (label_left + pad, text_y),
            font,
            font_scale,
            (10, 20, 14),  # texto escuro sobre fundo esmeralda
            font_thickness,
            lineType=cv2.LINE_AA,
        )

    return annotated
