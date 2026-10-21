"""Gera os ícones do aplicativo desktop **Bem-Te-Vi Monitor** (Tauri).

Reproduz a marca oficial (mesma do `front/public/favicon.svg`): fundo grafite
arredondado + ave esmeralda + olho escuro.

Uso (a partir da raiz do repositório):

    python front/src-tauri/icons/generate_icons.py

Gera: 32x32.png, 128x128.png, 128x128@2x.png, icon.png (512) e icon.ico.
Para ícones de outras plataformas (icns, webp), use o comando oficial:
`npm run tauri icon front/src-tauri/icons/icon.png`.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# --- Paleta oficial -------------------------------------------------------- #
FUNDO = (10, 15, 13)  # #0a0f0d
AVE = (16, 185, 129)  # #10b981

# Caminho vetorial do favicon (viewBox 32x32), como uma sequência de curvas
# cúbicas de Bézier em coordenadas de 32x32.
CURVAS = [
    ((6.0, 20.0), (10.0, 12.0), (16.0, 8.0), (22.0, 8.0)),
    ((22.0, 8.0), (24.0, 12.0), (24.0, 16.0), (22.0, 20.0)),
    ((22.0, 20.0), (18.0, 21.0), (14.0, 22.0), (10.0, 22.0)),
    ((10.0, 22.0), (8.0, 21.0), (7.0, 20.0), (6.0, 20.0)),
]
OLHO = (20.0, 12.0, 1.5)


def _bezier(p0, p1, p2, p3, passos: int = 64) -> list[tuple[float, float]]:
    """Amostra uma curva cúbica de Bézier."""
    pontos: list[tuple[float, float]] = []
    for i in range(passos + 1):
        t = i / passos
        u = 1 - t
        x = (
            u**3 * p0[0]
            + 3 * u**2 * t * p1[0]
            + 3 * u * t**2 * p2[0]
            + t**3 * p3[0]
        )
        y = (
            u**3 * p0[1]
            + 3 * u**2 * t * p1[1]
            + 3 * u * t**2 * p2[1]
            + t**3 * p3[1]
        )
        pontos.append((x, y))
    return pontos


def _contorno() -> list[tuple[float, float]]:
    """Contorno fechado da ave em coordenadas de 32x32."""
    pontos: list[tuple[float, float]] = []
    for curva in CURVAS:
        pontos.extend(_bezier(*curva))
    return pontos


def _desenhar(tamanho: int) -> Image.Image:
    """Desenha o ícone do Bem-Te-Vi Monitor no tamanho pedido."""
    escala = tamanho / 32.0
    supersample = 4
    lado = tamanho * supersample
    imagem = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(imagem)

    # Fundo arredondado (raio equivalente a 6/32 do viewBox).
    raio = 6 * escala * supersample
    desenho.rounded_rectangle(
        (0, 0, lado - 1, lado - 1), radius=raio, fill=FUNDO + (255,)
    )

    # Ave esmeralda.
    contorno = [(x * escala * supersample, y * escala * supersample) for x, y in _contorno()]
    desenho.polygon(contorno, fill=AVE + (255,))

    # Olho escuro.
    cx, cy, r = OLHO
    desenho.ellipse(
        (
            (cx - r) * escala * supersample,
            (cy - r) * escala * supersample,
            (cx + r) * escala * supersample,
            (cy + r) * escala * supersample,
        ),
        fill=FUNDO + (255,),
    )

    return imagem.resize((tamanho, tamanho), Image.LANCZOS)


def main() -> None:
    destino = Path(__file__).resolve().parent
    alvos = {
        "32x32.png": 32,
        "128x128.png": 128,
        "128x128@2x.png": 256,
        "icon.png": 512,
    }
    maior: Image.Image | None = None
    for nome, tamanho in alvos.items():
        imagem = _desenhar(tamanho)
        imagem.save(destino / nome)
        if nome == "icon.png":
            maior = imagem
        print(f"gerado: {nome} ({tamanho}x{tamanho})")

    if maior is not None:
        maior.save(
            destino / "icon.ico",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        print("gerado: icon.ico")


if __name__ == "__main__":
    main()
