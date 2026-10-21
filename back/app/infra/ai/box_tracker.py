"""Rastreamento leve com fluxo óptico e persistência para aves imóveis.

Como funciona:
- Nos quadros de inferência o YOLO entrega as detecções ("âncoras").
- Nos quadros intermediários o deslocamento das caixas é estimado por fluxo
  óptico esparso (Lucas-Kanade), evitando rodar o YOLO em todos os quadros.
- Persistência para aves imóveis: quando o YOLO deixa de detectar uma ave que
  já estava rastreada (o que é comum quando ela para de se mover para se
  alimentar), a caixa NÃO é descartada na hora. Ela é mantida "em espera" pela
  janela de retenção (`retention_seconds`). Assim a presença permanece contínua
  para o validador de zonas e o contador de permanência (dwell) não reinicia a
  cada quadro. A faixa só é removida após a janela de retenção expirar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from app.infra.ai.detector import Detection

# Limiar mínimo de sobreposição (IoU) para considerar que duas caixas são a
# mesma ave entre dois quadros de inferência.
DEFAULT_IOU_MATCH = 0.20


def _iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Interseção sobre união (IoU) entre duas caixas xyxy."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0.0 else 0.0


@dataclass
class _Track:
    """Uma ave rastreada e o instante da última detecção real do YOLO."""

    detection: Detection
    last_seen: float
    # Identificador estável do indivíduo (mantido enquanto a ave for rastreada).
    track_id: int
    # Quantidade de sincronizações em que o YOLO não confirmou esta faixa.
    misses: int = 0


@dataclass
class BoxTracker:
    """Rastreia as caixas por fluxo óptico, retendo aves que param de se mover.

    - retention_seconds: por quanto tempo uma ave continua sendo considerada
      presente após a última detecção real (3 a 10 s cobrem bem aves imóveis).
    - iou_match_threshold: sobreposição mínima para associar uma nova detecção
      a uma faixa já existente (evita duplicar a mesma ave).

    Cada faixa recebe um ``track_id`` estável, permitindo contar indivíduos
    distintos (bandos) ao longo da visita.
    """

    retention_seconds: float = 5.0
    iou_match_threshold: float = DEFAULT_IOU_MATCH
    _gray: np.ndarray | None = field(default=None, init=False, repr=False)
    _tracks: list[_Track] = field(default_factory=list, init=False, repr=False)
    _next_id: int = field(default=0, init=False, repr=False)
    _seen_ids: set[int] = field(default_factory=set, init=False, repr=False)

    def _novo_id(self) -> int:
        self._next_id += 1
        self._seen_ids.add(self._next_id)
        return self._next_id

    @staticmethod
    def _com_track_id(detection: Detection, track_id: int) -> Detection:
        """Cópia da detecção com o ``track_id`` atribuído."""
        return replace(detection, track_id=track_id)

    # ------------------------------------------------------------------ #
    # Sincronização com o YOLO (quadros de inferência)
    # ------------------------------------------------------------------ #
    def sync(self, frame: np.ndarray, detections: list[Detection]) -> list[Detection]:
        """Associa as novas detecções às faixas existentes e atualiza o quadro base.

        Mesmo que `detections` venha vazia (o YOLO não encontrou a ave neste
        quadro), as faixas conhecidas continuam válidas até a janela de
        retenção expirar.
        """
        now = time.monotonic()
        self._gray = self._to_gray(frame)

        matched: set[int] = set()
        updated: list[_Track] = []

        # 1) Cada detecção nova vira/atualiza uma faixa (casa com a existente por IoU).
        for detection in detections:
            best_index: int | None = None
            best_iou = self.iou_match_threshold
            for index, track in enumerate(self._tracks):
                if index in matched:
                    continue
                score = _iou(track.detection.bbox, detection.bbox)
                if score >= best_iou:
                    best_iou = score
                    best_index = index
            if best_index is not None:
                matched.add(best_index)
                # Reaproveita o identificador do indivíduo já rastreado.
                track_id = self._tracks[best_index].track_id
            else:
                # Nova ave: cria um identificador inédito.
                track_id = self._novo_id()
            # Faixa confirmada pelo YOLO: reinicia o relógio de retenção.
            updated.append(
                _Track(
                    detection=self._com_track_id(detection, track_id),
                    last_seen=now,
                    track_id=track_id,
                    misses=0,
                )
            )

        # 2) Faixas sem confirmação neste quadro permanecem "em espera".
        for index, track in enumerate(self._tracks):
            if index in matched:
                continue
            if now - track.last_seen <= self.retention_seconds:
                track.misses += 1
                updated.append(track)

        self._tracks = updated
        return self._visible()

    # ------------------------------------------------------------------ #
    # Quadros intermediários (entre inferências)
    # ------------------------------------------------------------------ #
    def update(self, frame: np.ndarray) -> list[Detection]:
        """Desloca as caixas por fluxo óptico e descarta faixas expiradas."""
        now = time.monotonic()
        gray = self._to_gray(frame)

        if self._gray is None or not self._tracks:
            self._gray = gray
            self._tracks = self._prune(now)
            return self._visible()

        for track in self._tracks:
            shifted = self._shift_with_optical_flow(self._gray, gray, track.detection.bbox)
            if shifted is None:
                # Fluxo óptico indisponível (ave imóvel sem textura suficiente):
                # mantém a última caixa conhecida em vez de perder a ave.
                shifted = track.detection.bbox
            track.detection = Detection(
                class_id=track.detection.class_id,
                class_name=track.detection.class_name,
                confidence=track.detection.confidence,
                bbox=shifted,
                track_id=track.track_id,
            )

        self._gray = gray
        self._tracks = self._prune(now)
        return self._visible()

    # ------------------------------------------------------------------ #
    # Auxiliares
    # ------------------------------------------------------------------ #
    def _prune(self, now: float) -> list[_Track]:
        """Remove faixas que ultrapassaram a janela de retenção."""
        return [
            track
            for track in self._tracks
            if now - track.last_seen <= self.retention_seconds
        ]

    def _visible(self) -> list[Detection]:
        return [track.detection for track in self._tracks]

    def has_tracks(self) -> bool:
        """Indica se existe alguma ave rastreada (mesmo que imóvel/em espera)."""
        return bool(self._tracks)

    def active_ids(self) -> set[int]:
        """Identificadores dos indivíduos presentes agora."""
        return {track.track_id for track in self._tracks}

    def seen_ids(self) -> set[int]:
        """Todos os identificadores já vistos desde o início do rastreio."""
        return set(self._seen_ids)

    def clear(self) -> None:
        """Descarta todas as faixas ativas e o quadro-base do fluxo óptico.

        Usado quando o Bem-Te-Vi Core é **pausado** para a câmera: ao retomar, o
        rastreio começa limpo, sem "fantasmas" de aves que já saíram de cena.
        Os identificadores já vistos (``seen_ids``) são preservados para não
        inflar a contagem de indivíduos do mesmo bando.
        """
        self._tracks = []
        self._gray = None

    @staticmethod
    def _to_gray(frame: np.ndarray) -> np.ndarray:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def _shift_with_optical_flow(
        self,
        previous_gray: np.ndarray,
        current_gray: np.ndarray,
        bbox: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float] | None:
        """Estima o novo bbox aplicando o deslocamento mediano dos pontos internos."""
        x1, y1, x2, y2 = bbox
        width, height = x2 - x1, y2 - y1
        if width < 2 or height < 2:
            return None

        points = np.array(
            [
                [x1 + width * 0.2, y1 + height * 0.2],
                [x1 + width * 0.8, y1 + height * 0.2],
                [x1 + width * 0.2, y1 + height * 0.8],
                [x1 + width * 0.8, y1 + height * 0.8],
                [x1 + width * 0.5, y1 + height * 0.5],
            ],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            previous_gray,
            current_gray,
            points,
            None,
            winSize=(15, 15),
            maxLevel=2,
        )
        if next_points is None or status is None:
            return None

        valid = status.reshape(-1).astype(bool)
        if np.count_nonzero(valid) < 3:
            return None
        displacement = np.median(
            (next_points.reshape(-1, 2) - points.reshape(-1, 2))[valid],
            axis=0,
        )

        frame_height, frame_width = current_gray.shape[:2]
        nx1 = max(0.0, min(float(frame_width - 1), x1 + float(displacement[0])))
        ny1 = max(0.0, min(float(frame_height - 1), y1 + float(displacement[1])))
        nx2 = max(0.0, min(float(frame_width - 1), x2 + float(displacement[0])))
        ny2 = max(0.0, min(float(frame_height - 1), y2 + float(displacement[1])))
        if nx2 <= nx1 or ny2 <= ny1:
            return None
        return (nx1, ny1, nx2, ny2)
