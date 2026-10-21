"""Vocabulário controlado dos rótulos de espécie do Bem-Te-Vi.

O detector (YOLOv8/BirdNET) trabalha com rótulos grosseiros: ``bird``,
``ave``, ``pássaro desconhecido``… Esses rótulos **não são** uma espécie e
nunca devem virar classe de treino, card da Life List ou rótulo definitivo na
Galeria.

Este módulo é a **fonte única da verdade** sobre o que é um rótulo genérico.
Ele normaliza o texto (caixa, acentos e espaços) antes da comparação, de modo
que ``"Pássaro Desconhecido"``, ``"passaro  desconhecido"`` e ``"PASSARO
DESCONHECIDO"`` caiam todos na mesma chave.

Dependência zero (somente a biblioteca padrão) para poder ser importado por
qualquer camada — domínio, IA, infraestrutura e API.
"""

from __future__ import annotations

import re
import unicodedata

#: Rótulos genéricos (sem acento, minúsculos, espaços colapsados).
GENERIC_SPECIES_LABELS: frozenset[str] = frozenset(
    {
        "bird",
        "passaro",
        "passaros",
        "passaro desconhecido",
        "ave",
        "aves",
        "ave generica",
        "ave (generica)",
        "passaro (generico)",
        "ave nao identificada",
        "nao identificada",
        "desconhecida",
        "desconhecido",
        "unidentified",
        "unknown",
        "visitante especial",
        "nao identificado",
        "nao identificado",
    }
)

_ESPACOS = re.compile(r"\s+")


def normalize_species_label(value: str | None) -> str:
    """Normaliza um rótulo de espécie para comparação segura.

    Remove acentos, colapsa espaços, aplica minúsculas e descarta caracteres
    de controle. Rótulos vazios viram ``""``.
    """
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", str(value))
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    cleaned = "".join(
        char for char in without_accents if char.isprintable() or char == " "
    )
    return _ESPACOS.sub(" ", cleaned).strip().casefold()


def is_generic_species(value: str | None) -> bool:
    """Indica se o rótulo é genérico (não houve identificação real).

    Texto vazio também é considerado genérico: uma ave sem nome não é uma
    espécie do catálogo.
    """
    normalized = normalize_species_label(value)
    if not normalized:
        return True
    return normalized in GENERIC_SPECIES_LABELS


def is_known_species(value: str | None) -> bool:
    """Invólucro legível: o rótulo **é** o nome de uma espécie real."""
    return not is_generic_species(value)
