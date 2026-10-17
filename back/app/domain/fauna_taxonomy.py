"""Taxonomia leve da fauna do jardim — o "anti-esquilo" do Alaris Core.

O detector de aves do AviaWatch é um YOLOv8 afinado para aves, mas o mundo real
não coopera: esquilos, gatos, gambás e outros bichos invadem o comedouro. Sem uma
camada de taxonomia, o Alaris Core acabaria cadastrando um **esquilo como nova
espécie de ave** na Life List ("Minhas Aves"), poluindo o Álbum e disparando
alertas de "ave nova".

Este módulo faz a **pós-classificação** desse rótulo, decidindo se o visitante é:

* :attr:`FaunaKind.AVE` — uma ave de verdade (segue o fluxo normal: Life List,
  alertas, estatísticas ornitológicas);
* :attr:`FaunaKind.MAMIFERO` — um mamífero (esquilo, gato, gambá…): vira
  **Visitante Especial**, ganha card próprio em "Convidados do Jardim" e **não**
  entra na Life List nem nos alertas de aves;
* :attr:`FaunaKind.OUTRO` — qualquer outro animal não identificado como ave.

A classificação é **conservadora**: na dúvida, presume-se ave. Assim o filtro
nunca descarta um pássaro legítimo — ele só intercepta o que reconhece
explicitamente como não-ave.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum

from app.domain.avifauna_sul import info_especie


class FaunaKind(str, Enum):
    """Grande grupo biológico do visitante do jardim."""

    AVE = "bird"
    MAMIFERO = "mammal"
    OUTRO = "other"


@dataclass(frozen=True)
class GrupoVisitante:
    """Identidade "divertida" de um Visitante Especial.

    ``categoria_galeria`` é o nome da prateleira onde as capturas do bicho
    aparecem na Galeria (ex.: *Convidados do Jardim (Esquilos)*).
    ``consumo_por_visita`` alimenta a estatística lúdica do painel (ex.: quantas
    sementes um esquilo leva por visita).
    """

    chave: str
    rotulo: str
    icone: str
    categoria_galeria: str
    consumo_por_visita: int = 0
    unidade: str = ""


# Prateleiras de "Convidados do Jardim". O esquilo é o astro principal.
GRUPO_ESQUILO = GrupoVisitante(
    chave="esquilo",
    rotulo="Esquilo",
    icone="🐿️",
    categoria_galeria="Convidados do Jardim (Esquilos)",
    consumo_por_visita=12,
    unidade="sementes",
)
GRUPO_ROEDOR = GrupoVisitante(
    chave="roedor",
    rotulo="Roedor",
    icone="🐭",
    categoria_galeria="Convidados do Jardim (Roedores)",
    consumo_por_visita=8,
    unidade="sementes",
)
GRUPO_FELINO = GrupoVisitante(
    chave="felino",
    rotulo="Felino",
    icone="🐱",
    categoria_galeria="Convidados do Jardim (Felinos)",
    consumo_por_visita=1,
    unidade="petiscos",
)
GRUPO_CANINO = GrupoVisitante(
    chave="canino",
    rotulo="Canino",
    icone="🐶",
    categoria_galeria="Convidados do Jardim (Caninos)",
    consumo_por_visita=1,
    unidade="petiscos",
)
GRUPO_GENERICO = GrupoVisitante(
    chave="visitante",
    rotulo="Visitante Silvestre",
    icone="🐾",
    categoria_galeria="Convidados do Jardim (Outros)",
)

# Índice por chave, para reidratar o grupo a partir do que foi gravado no banco.
GRUPOS: dict[str, GrupoVisitante] = {
    grupo.chave: grupo
    for grupo in (
        GRUPO_ESQUILO,
        GRUPO_ROEDOR,
        GRUPO_FELINO,
        GRUPO_CANINO,
        GRUPO_GENERICO,
    )
}


def grupo_por_chave(chave: str | None) -> GrupoVisitante:
    """Devolve o grupo de Visitante Especial pela sua chave (fallback genérico)."""
    return GRUPOS.get((chave or "").strip().lower(), GRUPO_GENERICO)

# Palavras-chave (pt-BR e inglês, sem acentos) que denunciam um mamífero.
# A ordem importa: o grupo mais específico (esquilo/roedor/felino/canino) vence.
_CHAVES_ESQUILO = (
    "esquilo",
    "serelepe",
    "caxinguele",
    "tamia",
    "marmota",
    "chipmunk",
    "squirrel",
    "sciurus",
    "sciuridae",
    "sciurillus",
    "tamiasciurus",
    "callosciurus",
    "funambulus",
    "xerus",
    "spermophilus",
    "marmota",
    "cynomys",
    "glaucomys",
)
_CHAVES_ROEDOR = (
    "roedor",
    "rodent",
    "rato",
    "camundongo",
    "rat",
    "mouse",
    "mus ",
    "rattus",
    "hamster",
    "porquinho-da-india",
    "prea",
    "paca",
    "cutia",
    "capivara",
    "hydrochoerus",
    "cavia",
    "lebre",
    "coelho",
    "rabbit",
    "hare",
    "oryctolagus",
    "tuco-tuco",
    "ctenomys",
)
_CHAVES_FELINO = (
    "gato",
    "felino",
    "cat",
    "felis",
    "felidae",
    "jaguatirica",
    "leopardus",
    "onca",
    "puma",
    "jaguar",
    "panthera",
    "lince",
    "lynx",
    "mao-pelada",
)
_CHAVES_CANINO = (
    "cachorro",
    "cao",
    "canino",
    "dog",
    "canis",
    "canidae",
    "raposa",
    "fox",
    "vulpes",
    "lobo",
    "wolf",
    "guara",
    "chrysocyon",
    "coiote",
    "coyote",
)
_CHAVES_MAMIFERO = (
    "mamifero",
    "mammal",
    "mammalia",
    "gamba",
    "opossum",
    "didelphis",
    "didelphidae",
    "quati",
    "coati",
    "nasua",
    "guaxinim",
    "raccoon",
    "procyon",
    "macaco",
    "monkey",
    "mico",
    "sagui",
    "callithrix",
    "primate",
    "morcego",
    "bat",
    "chiroptera",
    "tatu",
    "armadillo",
    "dasypus",
    "ouriço",
    "hedgehog",
    "erinaceus",
    "fuinha",
    "doninha",
    "mustela",
    "lontra",
    "lutra",
    "ariranha",
    "pteronura",
    "anta",
    "tapir",
    "porco",
    "pig",
    "suino",
    "javali",
    "sus scrofa",
    "cavalo",
    "horse",
    "equus",
    "vaca",
    "cow",
    "boi",
    "bos ",
    "ovelha",
    "sheep",
    "ovis",
    "cabra",
    "goat",
    "capra",
    "urso",
    "bear",
    "ursus",
    "veado",
    "cervo",
    "deer",
    "cervidae",
    "baleia",
    "golfinho",
    "dolphin",
    "lobo-marinho",
)

# Rótulos genéricos do detector que significam apenas "ave não identificada".
_GENERICOS_AVE = {
    "bird",
    "ave",
    "aves",
    "passaro",
    "passaros",
    "ave (generica)",
    "ave nao identificada",
    "nao identificada",
    "unidentified",
    "unknown",
    "desconhecida",
    "desconhecido",
}


def _normalizar(texto: str | None) -> str:
    """Minúsculas, sem acentos e com espaços colapsados (para comparação)."""
    base = " ".join((texto or "").strip().casefold().split())
    if not base:
        return ""
    decomposto = unicodedata.normalize("NFKD", base)
    return "".join(ch for ch in decomposto if not unicodedata.combining(ch))


def _contem(texto: str, chaves: tuple[str, ...]) -> bool:
    """Indica se alguma palavra-chave aparece no texto normalizado."""
    if not texto:
        return False
    return any(chave in texto for chave in chaves)


@dataclass(frozen=True)
class Visitante:
    """Veredito da taxonomia sobre o animal que apareceu no comedouro."""

    kind: FaunaKind
    # Preenchido apenas para não-aves (o "card" de Visitante Especial).
    grupo: GrupoVisitante | None
    # Nome exibido (nome popular informado ou o rótulo do grupo).
    nome: str
    common_name: str = ""
    scientific_name: str | None = None

    @property
    def eh_ave(self) -> bool:
        """True quando o visitante deve seguir o fluxo ornitológico normal."""
        return self.kind == FaunaKind.AVE

    @property
    def eh_mamifero(self) -> bool:
        return self.kind == FaunaKind.MAMIFERO

    def as_metadata(self) -> dict[str, object]:
        """Bloco ``metadata["visitor"]`` gravado na visita (lido pelo painel)."""
        return {
            "kind": self.kind.value,
            "is_bird": self.eh_ave,
            "group": self.grupo.chave if self.grupo else None,
            "label": self.nome,
            "icon": self.grupo.icone if self.grupo else "🐦",
            "gallery_category": self.grupo.categoria_galeria if self.grupo else None,
        }


def _grupo_para(texto: str) -> GrupoVisitante:
    """Escolhe o grupo de Visitante Especial mais específico para o texto."""
    if _contem(texto, _CHAVES_ESQUILO):
        return GRUPO_ESQUILO
    if _contem(texto, _CHAVES_ROEDOR):
        return GRUPO_ROEDOR
    if _contem(texto, _CHAVES_FELINO):
        return GRUPO_FELINO
    if _contem(texto, _CHAVES_CANINO):
        return GRUPO_CANINO
    return GRUPO_GENERICO


def _eh_mamifero(texto: str) -> bool:
    """True quando o texto casa com qualquer palavra-chave de mamífero."""
    return (
        _contem(texto, _CHAVES_ESQUILO)
        or _contem(texto, _CHAVES_ROEDOR)
        or _contem(texto, _CHAVES_FELINO)
        or _contem(texto, _CHAVES_CANINO)
        or _contem(texto, _CHAVES_MAMIFERO)
    )


def classificar_visitante(
    common_name: str | None, scientific_name: str | None = None
) -> FaunaKind:
    """Classifica o visitante em ave, mamífero ou outro.

    Regras, na ordem:

    1. rótulo genérico do detector (``bird``/``ave``) → **ave**;
    2. nome popular **ou** científico casa com mamífero conhecido → **mamífero**;
    3. a base regional de avifauna reconhece o nome → **ave**;
    4. na dúvida → **ave** (nunca descartamos um pássaro legítimo).
    """
    popular = _normalizar(common_name)
    cientifico = _normalizar(scientific_name)
    texto = f"{popular} {cientifico}".strip()

    if not texto or texto in _GENERICOS_AVE:
        return FaunaKind.AVE

    if _eh_mamifero(texto):
        return FaunaKind.MAMIFERO

    # Base regional (avifauna do Sul do Brasil / SC) como fonte de verdade.
    try:
        if info_especie(common_name=common_name, scientific_name=scientific_name):
            return FaunaKind.AVE
    except Exception:  # pragma: no cover - a base nunca deve derrubar o pipeline
        pass

    return FaunaKind.AVE


def descrever_visitante(
    common_name: str | None, scientific_name: str | None = None
) -> Visitante:
    """Resolve o visitante completo (grupo, ícone e prateleira da galeria)."""
    kind = classificar_visitante(common_name, scientific_name)
    if kind == FaunaKind.AVE:
        return Visitante(
            kind=kind,
            grupo=None,
            nome=(common_name or "Ave").strip(),
            common_name=(common_name or "").strip(),
            scientific_name=scientific_name,
        )

    grupo = _grupo_para(
        f"{_normalizar(common_name)} {_normalizar(scientific_name)}".strip()
    )
    nome = (common_name or "").strip() or grupo.rotulo
    return Visitante(
        kind=kind,
        grupo=grupo,
        nome=nome,
        common_name=(common_name or "").strip(),
        scientific_name=scientific_name,
    )


def eh_ave(common_name: str | None, scientific_name: str | None = None) -> bool:
    """Atalho booleano usado pelos guardas de Life List e de alertas."""
    return classificar_visitante(common_name, scientific_name) == FaunaKind.AVE
