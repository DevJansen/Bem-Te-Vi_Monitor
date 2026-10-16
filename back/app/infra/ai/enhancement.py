"""Melhoria automática (Enhancement) do melhor quadro de uma visita.

Pega o quadro vencedor da seleção (:mod:`app.infra.ai.best_frame`) e aplica um
pipeline leve de imagem com OpenCV antes de salvá-lo como a foto oficial:

1. **Equalização de histograma adaptativa (CLAHE)** no canal de luminância
   (LAB). Realça o contraste local das penas e das cores sob sol forte ou
   sombra, sem estourar a imagem inteira.
2. **Redução de ruído leve** com ``fastNlMeansDenoisingColored``, preservando
   as texturas (penas) enquanto suaviza o ruído do sensor — comum em câmeras
   de segurança e em capturas noturnas.

Custo controlado: a imagem é redimensionada para uma faixa de largura
(configurável) antes do processamento. O denoise não-linear é o passo mais
caro; limitar a largura (padrão HD, 1280 px) mantém o tempo por visita na casa
de poucas centenas de milissegundos, rodando fora do laço de captura.
"""

from __future__ import annotations

import cv2
import numpy as np

# Faixa de largura da foto tratada: reduz acima do máximo (limita o custo do
# denoise) e amplia suavemente abaixo do mínimo (garante "alta definição").
LARGURA_MAXIMA_PADRAO = 1280
LARGURA_MINIMA_PADRAO = 720
# Intensidade do realce de contraste local (CLAHE).
CLAHE_CLIP_PADRAO = 2.0
CLAHE_GRID_PADRAO = 8
# Força da redução de ruído (parâmetro ``h`` do fastNlMeansDenoisingColored).
FORCA_RUIDO_PADRAO = 5.0


def _garantir_bgr(imagem: np.ndarray) -> np.ndarray:
    """Normaliza o quadro para 3 canais BGR (aceita cinza e BGRA)."""
    if imagem.ndim == 2:
        return cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
    if imagem.ndim == 3 and imagem.shape[2] == 4:
        return cv2.cvtColor(imagem, cv2.COLOR_BGRA2BGR)
    return imagem


def _redimensionar_para_largura(
    imagem: np.ndarray, largura_maxima: int, largura_minima: int
) -> np.ndarray:
    """Ajusta a largura para a faixa [mínima, máxima], preservando a proporção."""
    altura, largura = imagem.shape[:2]
    escala = 1.0
    if largura_maxima and largura > largura_maxima:
        escala = largura_maxima / float(largura)
    elif largura_minima and largura < largura_minima:
        escala = largura_minima / float(largura)
    if abs(escala - 1.0) < 1e-3:
        return imagem
    nova_largura = max(2, int(round(largura * escala)))
    nova_altura = max(2, int(round(altura * escala)))
    interpolacao = cv2.INTER_AREA if escala < 1.0 else cv2.INTER_CUBIC
    return cv2.resize(imagem, (nova_largura, nova_altura), interpolation=interpolacao)


def _aplicar_clahe(imagem: np.ndarray, clip: float, grid: int) -> np.ndarray:
    """Equaliza o contraste local (CLAHE) apenas no canal L do espaço LAB."""
    grid = max(2, int(grid))
    lab = cv2.cvtColor(imagem, cv2.COLOR_BGR2LAB)
    luminancia, canal_a, canal_b = cv2.split(lab)
    clahe = cv2.createCLAHE(
        clipLimit=max(1.0, float(clip)),
        tileGridSize=(grid, grid),
    )
    luminancia = clahe.apply(luminancia)
    return cv2.cvtColor(
        cv2.merge([luminancia, canal_a, canal_b]), cv2.COLOR_LAB2BGR
    )


def realcar_quadro_da_ave(
    frame: np.ndarray,
    *,
    clahe_clip: float = CLAHE_CLIP_PADRAO,
    clahe_grid: int = CLAHE_GRID_PADRAO,
    reduzir_ruido: bool = True,
    forca_ruido: float = FORCA_RUIDO_PADRAO,
    largura_maxima: int = LARGURA_MAXIMA_PADRAO,
    largura_minima: int = LARGURA_MINIMA_PADRAO,
) -> np.ndarray | None:
    """Aplica CLAHE + redução de ruído ao quadro e devolve a foto tratada.

    Retorna ``None`` se o quadro for inválido/vazio. Qualquer parâmetro pode
    ser desligado (``clahe_clip <= 1`` desativa o CLAHE; ``reduzir_ruido=False``
    ou ``forca_ruido <= 0`` desativa o denoise).
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None

    imagem = _garantir_bgr(frame).copy()
    imagem = _redimensionar_para_largura(imagem, largura_maxima, largura_minima)

    # 1) Contraste local (CLAHE) — realça penas e cores.
    if clahe_clip and float(clahe_clip) > 1.0:
        imagem = _aplicar_clahe(imagem, float(clahe_clip), int(clahe_grid))

    # 2) Redução de ruído leve — suaviza o sensor sem apagar textura.
    if reduzir_ruido and float(forca_ruido) > 0:
        h = float(forca_ruido)
        imagem = cv2.fastNlMeansDenoisingColored(
            imagem, None, h, h, 7, 15
        )

    return imagem
