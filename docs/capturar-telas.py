"""Captura as telas do **Bem-Te-Vi Monitor** para a documentação.

Usa o Google Chrome em modo headless para renderizar cada aba do painel e
salvar a imagem em ``docs/images/``. As abas são abertas por hash (deep-link
adicionado em ``front/src/app/App.tsx``), o que torna as capturas
reproduzíveis: basta rodar o backend e o frontend e executar este script.

Uso:

    python docs/capturar-telas.py [--url http://127.0.0.1:5173] [--saida docs/images]

Requer: Google Chrome/Edge instalado e o Bem-Te-Vi Core rodando (API local).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

#: Aba do painel → arquivo de imagem gerado (altura opcional da viewport).
TELAS: list[tuple[str, str, int | None]] = [
    ("dashboard", "painel.png", None),
    ("cameras", "cameras.png", 1500),
    ("gallery", "galeria.png", None),
    ("journal", "diario-de-campo.png", None),
    ("audio", "deteccao-sonora.png", 620),
    ("species", "minhas-aves.png", None),
    ("analytics", "estatisticas.png", None),
    ("settings", "configuracoes.png", None),
]

#: Candidatos de navegador (Windows/macOS/Linux).
NAVEGADORES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def encontrar_navegador() -> str:
    """Localiza o executável do Chrome/Edge."""
    for caminho in NAVEGADORES:
        if Path(caminho).is_file():
            return caminho
    encontrado = shutil.which("google-chrome") or shutil.which("chromium")
    if encontrado:
        return encontrado
    raise SystemExit(
        "Chrome/Edge não encontrado. Instale o Google Chrome ou informe o "
        "caminho manualmente."
    )


def capturar(navegador: str, url: str, destino: Path, largura: int, altura: int) -> None:
    """Renderiza uma URL em modo headless e grava a captura em ``destino``."""
    with tempfile.TemporaryDirectory(prefix="bemtevi-shots-") as perfil:
        comando = [
            navegador,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--user-data-dir={perfil}",
            f"--window-size={largura},{altura}",
            "--virtual-time-budget=15000",
            f"--screenshot={destino}",
            url,
        ]
        subprocess.run(
            comando,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--saida", default=str(RAIZ / "docs" / "images"))
    parser.add_argument("--largura", type=int, default=1600)
    parser.add_argument("--altura", type=int, default=1000)
    args = parser.parse_args()

    navegador = encontrar_navegador()
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)

    for aba, arquivo, altura in TELAS:
        destino = saida / arquivo
        try:
            capturar(
                navegador,
                f"{args.url}/#{aba}",
                destino,
                args.largura,
                altura or args.altura,
            )
            tamanho = destino.stat().st_size if destino.is_file() else 0
            print(f"ok  {arquivo} ({tamanho // 1024} KB)")
        except subprocess.CalledProcessError as exc:
            print(f"erro ao capturar {arquivo}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
