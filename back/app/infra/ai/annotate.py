"""Overlays visuais do Bem-Te-Vi Core (caixas modernas + selos de identificação).

Este módulo desenha, sobre os quadros do OpenCV:

- **Caixas delimitadoras modernizadas** ao redor de cada ave/fauna, com
  cantos sutilmente arredondados, borda de **2 px semi-transparente** e cor
  dinâmica conforme o **status da identificação**:

  * **Ciano / Azul Prussiano** — ave **confirmada** (nome real de espécie);
  * **Âmbar** — **pré-associação** (ainda sem espécie: aguardando o Bem-Te-Vi Core
    Core ou a curadoria do observador);
  * **Rosa** — fauna não-ave (Visitante Especial).

- **Selos flutuantes** em *dark mode* (fundo ``slate-900`` translúcido, texto
  claro e destaque na cor do status) com a identificação real da ave, no formato
  ``Cardeal-do-norte • 88%``. A legenda genérica *"pássaro 25%"* foi removida:
  enquanto não há espécie, o selo informa ``Aguardando ID`` **sem** exibir uma
  confiança que não é da espécie.

- **Tarja de identificação** (watermark/legenda) para os clipes gravados,
  garantindo que o vídeo salvo já mostre a espécie mesmo fora do painel.

Tudo é desenhado de forma leve (poucas chamadas por caixa, com antialiasing,
mistura alfa restrita à região do desenho e sem cópias extras do quadro inteiro)
para **não introduzir atraso no stream em tempo real**.

Detalhe técnico: as fontes do OpenCV só renderizam ASCII. Por isso o "•" do
rótulo é desenhado como um pequeno círculo (via ``cv2.circle``) e o "✨" da
marca como um losango (``_draw_sparkle``) — nenhum caractere Unicode é
passado a ``cv2.putText``.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.domain.species_labels import is_generic_species
from app.infra.ai.detector import Detection, translate_class_name

# --- Paleta do Bem-Te-Vi Core (BGR) ----------------------------------------- #
CONFIRMED_BGR = (238, 211, 34)   # ciano #22D3EE — ave confirmada
PRUSSIAN_BGR = (107, 59, 18)    # azul prussiano moderno #123B6B
PENDING_BGR = (11, 158, 245)     # âmbar #F59E0B — pré-associação
FAUNA_BGR = (182, 114, 244)      # rosa #F472B6 — fauna não-ave
TAG_BG_BGR = (42, 23, 15)        # fundo dark mode do selo (slate-900)
TAG_TEXT_BGR = (240, 232, 226)   # texto claro (slate-200)
TAG_MUTED_BGR = (184, 163, 148)  # texto secundário (slate-400)
BANNER_BG_BGR = (10, 13, 12)     # fundo da tarja do clipe

# Marca do motor. Mantida em ASCII (putText não renderiza emoji).
ALARIS_LABEL = "Bem-Te-Vi Core"

#: Marca exibida no selo (alias oficial do nome do motor).
CORE_LABEL = ALARIS_LABEL
# Rótulo usado enquanto a ave ainda não tem espécie associada.
PENDING_LABEL = "Aguardando ID"

BOX_THICKNESS = 2
CORNER_RADIUS = 10
# Opacidade da borda da caixa (2 px) — semi-transparente, como no design system.
BOX_ALPHA = 0.85
# Opacidade do fundo do selo (equivalente a bg-slate-900/90).
TAG_ALPHA = 0.90


def _is_identified(label: str | None) -> bool:
    """Indica se o rótulo já é uma espécie real (não um rótulo genérico)."""
    return not is_generic_species(label)


def _color_for(class_name: str, label: str | None = None) -> tuple[int, int, int]:
    """Cor da caixa conforme a classe e o status da identificação.

    * ave **confirmada** → ciano;
    * ave em **pré-associação** → âmbar;
    * fauna (não-ave) → rosa.
    """
    is_bird = str(class_name).strip().lower() == "bird"
    if not is_bird:
        return FAUNA_BGR
    return CONFIRMED_BGR if _is_identified(label) else PENDING_BGR


def _rounded_rectangle(
    img: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple[int, int, int],
    *,
    thickness: int = 1,
    radius: int = CORNER_RADIUS,
    fill: bool = False,
) -> None:
    """Desenha um retângulo de cantos arredondados (contorno ou preenchimento).

    Feito com 4 retas + 4 arcos de elipse — barato e com antialiasing, sem
    depender de bibliotecas externas.
    """
    r = int(max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2)))
    if fill:
        cv2.rectangle(img, (x1 + r, y1), (x2 - r, y2), color, -1)
        cv2.rectangle(img, (x1, y1 + r), (x2, y2 - r), color, -1)
        for cx, cy, ang in (
            (x1 + r, y1 + r, 180),
            (x2 - r, y1 + r, 270),
            (x2 - r, y2 - r, 0),
            (x1 + r, y2 - r, 90),
        ):
            cv2.ellipse(img, (cx, cy), (r, r), ang, 0, 90, color, -1, cv2.LINE_AA)
        return

    cv2.line(img, (x1 + r, y1), (x2 - r, y1), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x1 + r, y2), (x2 - r, y2), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x1, y1 + r), (x1, y2 - r), color, thickness, cv2.LINE_AA)
    cv2.line(img, (x2, y1 + r), (x2, y2 - r), color, thickness, cv2.LINE_AA)
    for cx, cy, ang in (
        (x1 + r, y1 + r, 180),
        (x2 - r, y1 + r, 270),
        (x2 - r, y2 - r, 0),
        (x1 + r, y2 - r, 90),
    ):
        cv2.ellipse(
            img, (cx, cy), (r, r), ang, 0, 90, color, thickness, cv2.LINE_AA
        )


def _soft_shape(
    img: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple[int, int, int],
    *,
    thickness: int = 1,
    radius: int = CORNER_RADIUS,
    alpha: float = BOX_ALPHA,
    fill: bool = False,
) -> None:
    """Desenha uma forma arredondada **semi-transparente**.

    A mistura alfa é restrita à região (ROI) afetada pelo desenho — o quadro
    inteiro nunca é copiado, mantendo o custo por caixa muito baixo. A máscara
    é suavizada com um blur de 3×3 para preservar o antialiasing nas bordas.
    """
    altura, largura = img.shape[:2]
    pad = thickness + radius + 2
    x0 = max(0, x1 - pad)
    y0 = max(0, y1 - pad)
    x3 = min(largura, x2 + pad + 1)
    y3 = min(altura, y2 + pad + 1)
    if x3 <= x0 or y3 <= y0:
        return

    roi = img[y0:y3, x0:x3]
    local_x1 = x1 - x0
    local_y1 = y1 - y0
    local_x2 = x2 - x0
    local_y2 = y2 - y0

    overlay = roi.copy()
    _rounded_rectangle(
        overlay,
        local_x1,
        local_y1,
        local_x2,
        local_y2,
        color,
        thickness=thickness,
        radius=radius,
        fill=fill,
    )
    mask = np.zeros(roi.shape[:2], dtype=np.uint8)
    _rounded_rectangle(
        mask,
        local_x1,
        local_y1,
        local_x2,
        local_y2,
        255,
        thickness=thickness,
        radius=radius,
        fill=fill,
    )
    mask = cv2.GaussianBlur(mask, (3, 3), 0)

    pesos = (mask.astype(np.float32) / 255.0) * float(alpha)
    misturado = (
        overlay.astype(np.float32) * pesos[..., None]
        + roi.astype(np.float32) * (1.0 - pesos[..., None])
    )
    roi[:] = np.clip(misturado, 0, 255).astype(np.uint8)


def _draw_sparkle(
    img: np.ndarray, cx: int, cy: int, size: int, color: tuple[int, int, int]
) -> None:
    """Desenha um pequeno losango de 4 pontas (aproxima o "✨" da marca)."""
    pontos = np.array(
        [
            [cx, cy - size],
            [cx + max(1, size // 3), cy - max(1, size // 3)],
            [cx + size, cy],
            [cx + max(1, size // 3), cy + max(1, size // 3)],
            [cx, cy + size],
            [cx - max(1, size // 3), cy + max(1, size // 3)],
            [cx - size, cy],
            [cx - max(1, size // 3), cy - max(1, size // 3)],
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(img, [pontos], color, lineType=cv2.LINE_AA)


def _species_label(det: Detection, species_by_track: dict[int, str] | None) -> str:
    """Resolve o nome de exibição: espécie do rastreio ou a classe traduzida."""
    if species_by_track and det.track_id is not None:
        nome = species_by_track.get(det.track_id)
        if nome:
            return nome
    return translate_class_name(det.class_name)


def _draw_name_with_dot(
    img: np.ndarray,
    x: int,
    y: int,
    name: str,
    percent: str | None,
    *,
    font: int,
    scale: float,
    thickness: int,
    text_color: tuple[int, int, int],
    dot_color: tuple[int, int, int],
) -> int:
    """Escreve ``<nome> • <NN>%`` e devolve a largura total (em px).

    O separador "•" é um círculo desenhado (as fontes do OpenCV não suportam
    Unicode), e a porcentagem só aparece quando a ave já tem espécie real — a
    confiança do detector não é confiança de espécie.
    """
    cv2.putText(img, name, (x, y), font, scale, text_color, thickness, cv2.LINE_AA)
    (name_w, _), _ = cv2.getTextSize(name, font, scale, thickness)
    cursor = x + name_w
    if not percent:
        return cursor - x

    gap = 8
    radius = 2
    cursor += gap
    cv2.circle(img, (cursor + radius, y - 5), radius, dot_color, -1, cv2.LINE_AA)
    cursor += radius * 2 + gap
    cv2.putText(
        img, percent, (cursor, y), font, scale, dot_color, thickness, cv2.LINE_AA
    )
    (pct_w, _), _ = cv2.getTextSize(percent, font, scale, thickness)
    return cursor + pct_w - x


def _draw_core_tag(
    annotated: np.ndarray,
    x1: int,
    y1: int,
    species: str,
    confidence: float,
    color: tuple[int, int, int],
    *,
    identified: bool = True,
) -> None:
    """Desenha o selo flutuante do Bem-Te-Vi Core acima da caixa delimitadora.

    Layout (2 linhas) no estilo *dark mode*:

    * linha 1 — ``Bem-Te-Vi Core`` (marca, na cor do status) com losango;
    * linha 2 — ``<espécie> • <NN>%`` quando a ave está associada, ou
      ``Aguardando ID`` enquanto a associação ainda não aconteceu.

    O fundo é translúcido (``slate-900`` a 90%) e o selo é posicionado acima da
    caixa; quando não há espaço, encaixa dentro do topo dela.
    """
    altura, largura = annotated.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    f1, t1 = 0.38, 1   # marca
    f2, t2 = 0.52, 1   # espécie + confiança

    nome = str(species or "").strip()
    percentual = f"{int(round(float(confidence) * 100))}%" if identified else None
    if not identified:
        nome = PENDING_LABEL

    (w1, h1), b1 = cv2.getTextSize(ALARIS_LABEL, font, f1, t1)
    (w_nome, h2), b2 = cv2.getTextSize(nome, font, f2, t2)
    w_pct = 0
    if percentual:
        (w_pct, _), _ = cv2.getTextSize(percentual, font, f2, t2)
    # Largura da linha 2: nome + separador + porcentagem.
    largura_linha2 = w_nome + (8 * 2 + 4 + w_pct if percentual else 0)

    pad = 7
    accent_w = 4
    sparkle = 5
    gap = 6
    conteudo = max(sparkle * 2 + gap + w1, largura_linha2)
    tag_w = pad + accent_w + pad + conteudo + pad
    tag_h = pad + h1 + b1 + gap + h2 + b2 + pad

    tag_w = min(tag_w, largura - 2)
    tag_h = min(tag_h, altura - 2)
    tag_x = max(0, min(x1, largura - tag_w - 1))
    tag_y = y1 - tag_h - 6
    if tag_y < 0:
        # Sem espaço acima: encaixa dentro do topo da caixa.
        tag_y = max(0, min(y1 + 2, altura - tag_h - 1))

    # Fundo escuro translúcido + borda de destaque (visual "dark tech").
    _soft_shape(
        annotated,
        tag_x,
        tag_y,
        tag_x + tag_w,
        tag_y + tag_h,
        TAG_BG_BGR,
        radius=8,
        alpha=TAG_ALPHA,
        fill=True,
    )
    _soft_shape(
        annotated,
        tag_x,
        tag_y,
        tag_x + tag_w,
        tag_y + tag_h,
        color,
        thickness=1,
        radius=8,
        alpha=0.9,
        fill=False,
    )
    # Barra de destaque à esquerda (identidade visual do Bem-Te-Vi Core).
    _soft_shape(
        annotated,
        tag_x,
        tag_y,
        tag_x + accent_w + 2,
        tag_y + tag_h,
        color,
        radius=3,
        alpha=1.0,
        fill=True,
    )

    content_x = tag_x + pad + accent_w + 2
    linha1_y = tag_y + pad + h1
    _draw_sparkle(annotated, content_x + sparkle, linha1_y - h1 // 2, sparkle, color)
    cv2.putText(
        annotated, ALARIS_LABEL, (content_x + sparkle * 2 + gap, linha1_y),
        font, f1, color, t1, cv2.LINE_AA,
    )
    _draw_name_with_dot(
        annotated,
        content_x,
        linha1_y + b1 + gap + h2,
        nome,
        percentual,
        font=font,
        scale=f2,
        thickness=t2,
        text_color=TAG_TEXT_BGR,
        dot_color=color if identified else TAG_MUTED_BGR,
    )


def draw_bird_detections(
    frame: np.ndarray,
    detections: list[Detection],
    *,
    min_confidence: float | None = None,
    species_by_track: dict[int, str] | None = None,
    show_core: bool = True,
) -> np.ndarray:
    """Retorna cópia do quadro com as caixas modernas e os selos do Bem-Te-Vi Core.

    ``species_by_track`` mapeia ``track_id`` → nome da espécie identificada,
    permitindo ao selo exibir o nome real da ave (e não apenas "Ave"). A cor da
    caixa acompanha o status: **ciano** para ave confirmada e **âmbar** para a
    pré-associação.
    """
    if frame is None or frame.size == 0:
        return frame

    annotated = frame.copy()
    altura, largura = annotated.shape[:2]

    for det in detections:
        if min_confidence is not None and det.confidence < min_confidence:
            continue

        rotulo = _species_label(det, species_by_track)
        identified = _is_identified(rotulo)
        color = _color_for(det.class_name, rotulo)
        x1, y1, x2, y2 = det.bbox
        x1_i = max(0, min(largura - 1, int(round(x1))))
        y1_i = max(0, min(altura - 1, int(round(y1))))
        x2_i = max(0, min(largura - 1, int(round(x2))))
        y2_i = max(0, min(altura - 1, int(round(y2))))
        if x2_i <= x1_i or y2_i <= y1_i:
            continue

        # Caixa arredondada com borda de 2 px semi-transparente.
        _soft_shape(
            annotated,
            x1_i,
            y1_i,
            x2_i,
            y2_i,
            color,
            thickness=BOX_THICKNESS,
            radius=CORNER_RADIUS,
            alpha=BOX_ALPHA,
        )

        if show_core:
            _draw_core_tag(
                annotated,
                x1_i,
                y1_i,
                rotulo,
                det.confidence,
                color,
                identified=identified,
            )
        else:
            # Modo simples (compatibilidade): rótulo curto com a espécie/confiança.
            pct = f"{int(round(det.confidence * 100))}%" if identified else None
            font = cv2.FONT_HERSHEY_SIMPLEX
            (tw, th), baseline = cv2.getTextSize(
                rotulo if identified else PENDING_LABEL, font, 0.55, 1
            )
            largura_texto = tw + (24 if pct else 0)
            topo = max(0, y1_i - th - baseline - 8)
            cv2.rectangle(
                annotated,
                (x1_i, topo),
                (x1_i + largura_texto + 8, max(th + baseline + 8, y1_i)),
                color,
                -1,
            )
            _draw_name_with_dot(
                annotated,
                x1_i + 4,
                max(th + baseline + 4, y1_i) - baseline - 4,
                rotulo if identified else PENDING_LABEL,
                pct,
                font=font,
                scale=0.55,
                thickness=1,
                text_color=TAG_BG_BGR,
                dot_color=TAG_BG_BGR,
            )

    return annotated


# --------------------------------------------------------------------------- #
# Tarja de identificação dos clipes gravados (watermark/legenda)
# --------------------------------------------------------------------------- #
def build_clip_banner(
    width: int,
    *,
    species: str,
    confidence: float,
    camera_name: str | None = None,
    timestamp: str | None = None,
) -> np.ndarray:
    """Pré-renderiza a tarja fosca de identificação (largura total) do clipe.

    A tarja é montada **uma única vez** por clipe e depois apenas mesclada em
    cada quadro (``apply_banner``), mantendo a gravação barata.
    """
    altura = 58
    largura = max(2, int(width))
    strip = np.zeros((altura, largura, 3), dtype=np.uint8)
    strip[:] = BANNER_BG_BGR

    font = cv2.FONT_HERSHEY_SIMPLEX
    # Linha de destaque no topo da tarja (identidade do Bem-Te-Vi Core).
    cv2.line(strip, (0, 0), (largura, 0), CONFIRMED_BGR, 2, cv2.LINE_AA)

    x = 16
    # Marca: sparkle + "Bem-Te-Vi Core".
    _draw_sparkle(strip, x + 6, 20, 6, CONFIRMED_BGR)
    cv2.putText(
        strip, ALARIS_LABEL, (x + 20, 25), font, 0.5, CONFIRMED_BGR, 1, cv2.LINE_AA
    )

    # Espécie (destaque) + separador + confiança.
    rotulo = str(species).strip() or PENDING_LABEL
    percentual = f"{int(round(float(confidence) * 100))}%"
    cv2.putText(
        strip, rotulo, (x, 50), font, 0.72, TAG_TEXT_BGR, 2, cv2.LINE_AA
    )
    (tw, _), _ = cv2.getTextSize(rotulo, font, 0.72, 2)
    cv2.circle(strip, (x + tw + 14, 42), 2, CONFIRMED_BGR, -1, cv2.LINE_AA)
    cv2.putText(
        strip,
        percentual,
        (x + tw + 24, 50),
        font,
        0.62,
        CONFIRMED_BGR,
        2,
        cv2.LINE_AA,
    )

    # Rodapé à direita: câmera e horário (secundário, alinhado à direita).
    rodape = " · ".join(parte for parte in (camera_name, timestamp) if parte)
    if rodape:
        (rw, _), _ = cv2.getTextSize(rodape, font, 0.45, 1)
        cv2.putText(
            strip,
            rodape,
            (max(x, largura - rw - 16), 34),
            font,
            0.45,
            TAG_MUTED_BGR,
            1,
            cv2.LINE_AA,
        )
    return strip


def apply_banner(
    frame: np.ndarray,
    strip: np.ndarray,
    *,
    alpha: float = 0.62,
    position: str = "bottom",
) -> np.ndarray:
    """Mescla a tarja de identificação em uma cópia do quadro (clipe gravado).

    Retorna uma **cópia** para não alterar os quadros originais (que ainda
    alimentam a foto oficial/melhor quadro da visita).
    """
    if frame is None or frame.size == 0 or strip is None or strip.size == 0:
        return frame
    altura, largura = frame.shape[:2]
    sh, sw = strip.shape[:2]
    if sw != largura:
        strip = cv2.resize(strip, (largura, sh), interpolation=cv2.INTER_AREA)
    sh = min(sh, altura)

    saida = frame.copy()
    if position == "top":
        regiao = saida[0:sh]
    else:
        regiao = saida[altura - sh : altura]
    mesclado = cv2.addWeighted(regiao, 1.0 - alpha, strip[:sh], alpha, 0.0)
    if position == "top":
        saida[0:sh] = mesclado
    else:
        saida[altura - sh : altura] = mesclado
    return saida
