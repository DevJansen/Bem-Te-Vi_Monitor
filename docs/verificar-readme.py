"""Verifica os links e imagens referenciados nos READMEs do repositório.

- imagens: o arquivo referenciado precisa existir em `docs/images/`;
- links internos (`README-DEV.md#âncora`): o arquivo precisa existir e a âncora
  precisa corresponder a um heading do arquivo destino.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
READMES = ["README.md", "README-DEV.md"]


def normalizar(texto: str) -> str:
    """Normaliza um texto para o padrão de âncora do GitHub."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9\- _]", "", sem_acento.lower()).replace(" ", "-")


def headings(caminho: Path) -> set[str]:
    """Coleta as âncoras (headings) de um arquivo markdown."""
    found: set[str] = set()
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if linha.startswith("#"):
            found.add(normalizar(linha.lstrip("#").strip()))
    return found


def main() -> int:
    erros: list[str] = []
    total_imagens = 0
    total_links = 0

    for nome in READMES:
        caminho = RAIZ / nome
        texto = caminho.read_text(encoding="utf-8")

        for alvo in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", texto):
            total_imagens += 1
            destino = (RAIZ / alvo).resolve()
            if not destino.is_file():
                erros.append(f"{nome}: imagem ausente -> {alvo}")

        for rotulo, alvo in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", texto):
            if alvo.startswith(("http://", "https://", "mailto:")):
                continue
            total_links += 1
            arquivo, _, ancora = alvo.partition("#")
            destino = (RAIZ / arquivo).resolve() if arquivo else caminho
            if not destino.is_file():
                erros.append(f"{nome}: link quebrado -> {alvo}")
                continue
            if ancora and destino.suffix == ".md":
                if normalizar(ancora) not in headings(destino):
                    erros.append(f"{nome}: âncora inexistente -> {alvo}")

    print(f"imagens verificadas: {total_imagens}")
    print(f"links internos verificados: {total_links}")
    if erros:
        print("\nPROBLEMAS:")
        for erro in erros:
            print(" -", erro)
        return 1
    print("\nTudo certo: imagens e links internos resolvem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
