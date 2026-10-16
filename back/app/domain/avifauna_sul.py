"""Módulo de inteligência biogeográfica — avifauna do Sul do Brasil (SC).

Base de metadados ornitológicos local, curada a partir do conhecimento sobre a
avifauna de Santa Catarina / Mata Atlântica do Sul. Serve para rotular
automaticamente o **status ecológico** de cada espécie identificada, permitindo
uso científico/ conservacionista (monitoramento de espécies migratórias, raras e
endêmicas).

O cruzamento é tolerante a variações de escrita: compara o nome científico e o
popular normalizados (caixa, acentos e espaços). Espécies fora da base caem no
status ``DESCONHECIDA`` — nunca inventamos um rótulo.

⚠️ Curadoria: os status refletem o padrão regional do Sul do Brasil e podem ser
refinados por biólogos. O módulo é a fonte única de verdade para os rótulos.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum


class StatusEcologico(str, Enum):
    """Status ecológico/regional de uma espécie no Sul do Brasil."""

    NATIVA = "nativa"
    MIGRATORIA = "migratoria"
    ENDEMICA = "endemica"
    RARA = "rara"
    EXOTICA = "exotica"
    DESCONHECIDA = "desconhecida"


# Rótulo legível (pt-BR) de cada status.
STATUS_LABELS: dict[StatusEcologico, str] = {
    StatusEcologico.NATIVA: "Nativa",
    StatusEcologico.MIGRATORIA: "Migratória",
    StatusEcologico.ENDEMICA: "Endêmica",
    StatusEcologico.RARA: "Rara / Acidental",
    StatusEcologico.EXOTICA: "Exótica",
    StatusEcologico.DESCONHECIDA: "Desconhecida",
}

# Selo visual (emoji + rótulo) exibido no painel/galeria.
STATUS_BADGES: dict[StatusEcologico, str] = {
    StatusEcologico.NATIVA: "🟢 Nativa",
    StatusEcologico.MIGRATORIA: "🟡 Migratória",
    StatusEcologico.ENDEMICA: "🔵 Endêmica",
    StatusEcologico.RARA: "⭐ Espécie Rara",
    StatusEcologico.EXOTICA: "🟠 Exótica",
    StatusEcologico.DESCONHECIDA: "⚪ Status desconhecido",
}

# Ícone curto (sem texto) para espaços compactos.
STATUS_ICONS: dict[StatusEcologico, str] = {
    StatusEcologico.NATIVA: "🟢",
    StatusEcologico.MIGRATORIA: "🟡",
    StatusEcologico.ENDEMICA: "🔵",
    StatusEcologico.RARA: "⭐",
    StatusEcologico.EXOTICA: "🟠",
    StatusEcologico.DESCONHECIDA: "⚪",
}

# Ordem de "interesse científico" para destaque no painel (quanto maior, mais
# relevante). Espécies raras/endêmicas/migratórias merecem selo de destaque.
STATUS_PRIORIDADE: dict[StatusEcologico, int] = {
    StatusEcologico.RARA: 4,
    StatusEcologico.ENDEMICA: 3,
    StatusEcologico.MIGRATORIA: 2,
    StatusEcologico.EXOTICA: 1,
    StatusEcologico.NATIVA: 0,
    StatusEcologico.DESCONHECIDA: 0,
}


@dataclass(frozen=True)
class EspecieSul:
    """Metadados ornitológicos de uma espécie da região."""

    common_name: str
    scientific_name: str
    status: StatusEcologico
    # Observação curta (habitat, sazonalidade ou motivo do status).
    notes: str = ""


def _normalizar(texto: str | None) -> str:
    """Normaliza um nome para comparação.

    Remove acentos, colapsa espaços e baixa a caixa — assim "Sanhaço-cinza",
    "sanhaco cinza" e "SANHAÇO CINZA" casam entre si.
    """
    base = str(texto or "").strip().lower()
    if not base:
        return ""
    # Remove acentos (NFD → mantém apenas o caractere base).
    decomposto = unicodedata.normalize("NFKD", base)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    # Unifica hífens/underscores em espaço e colapsa espaços repetidos.
    for separador in ("-", "_", "/"):
        sem_acento = sem_acento.replace(separador, " ")
    return " ".join(sem_acento.split())


# --------------------------------------------------------------------------- #
# Base curada da avifauna do Sul do Brasil / Santa Catarina
# --------------------------------------------------------------------------- #
_N = StatusEcologico.NATIVA
_M = StatusEcologico.MIGRATORIA
_E = StatusEcologico.ENDEMICA
_R = StatusEcologico.RARA
_X = StatusEcologico.EXOTICA

ESPECIES_SUL: tuple[EspecieSul, ...] = (
    # --- Comedouro / quintal (residentes comuns) ---
    EspecieSul("Bem-te-vi", "Pitangus sulphuratus", _N, "Muito comum em quintais e bordas de mata."),
    EspecieSul("Cambacica", "Coereba flaveola", _N, "Visitante frequente de bebedouros com açúcar."),
    EspecieSul("Sanhaço-cinza", "Thraupis sayaca", _N, "Comum em frutíferas e comedouros."),
    EspecieSul("Sanhaço-frade", "Stephanophorus diadematus", _N, "Endêmico do Sul/Sudeste; comum em pomares."),
    EspecieSul("Tico-tico", "Zonotrichia capensis", _N, "Comum em solo e comedouros de chão."),
    EspecieSul("Corruíra", "Troglodytes musculus", _N, "Pequena e ativa; comum em jardins."),
    EspecieSul("Sabiá-laranjeira", "Turdus rufiventris", _N, "Ave-símbolo do Brasil; comum em todo o Sul."),
    EspecieSul("Sabiá-barranco", "Turdus leucomelas", _N, "Comum em áreas abertas e pomares."),
    EspecieSul("Sabiá-poca", "Turdus amaurochalinus", _M, "Parcialmente migratória; aparece no inverno."),
    EspecieSul("Sabiá-una", "Turdus flavipes", _N, "Habita mata; visita frutíferas."),
    EspecieSul("João-de-barro", "Furnarius rufus", _N, "Constrói o ninho de barro; comum no Sul."),
    EspecieSul("Quero-quero", "Vanellus chilensis", _N, "Comum em gramados e campos."),
    EspecieSul("Suiriri", "Tyrannus melancholicus", _N, "Comum em cercas e fios; parcialmente migratório."),
    EspecieSul("Bem-te-vizinho", "Myiozetetes similis", _N, "Semelhante ao bem-te-vi, menor."),
    EspecieSul("Canário-da-terra", "Sicalis flaveola", _N, "Comum em comedouros de sementes."),
    EspecieSul("Tiziu", "Volatinia jacarina", _N, "Comum em capinzais."),
    EspecieSul("Cardeal", "Paroaria coronata", _N, "Mais comum no Sul; visitante de comedouros."),
    EspecieSul("Pintassilgo", "Spinus magellanicus", _N, "Comum em comedouros de sementes."),
    EspecieSul("Coleirinho", "Sporophila caerulescens", _M, "Migratória parcial; aparece em bandos."),
    EspecieSul("Chupim", "Molothrus bonariensis", _N, "Parasita de ninhos; comum em bandos."),
    EspecieSul("Graúna", "Gnorimopsar chopi", _N, "Comum no Sul; frequenta comedouros."),
    EspecieSul("Garibaldi", "Chrysomus ruficapillus", _N, "Comum em banhados e campos úmidos."),
    EspecieSul("Sabiá-do-campo", "Mimus saturninus", _N, "Comum em áreas abertas."),
    EspecieSul("Trinca-ferro", "Saltator similis", _N, "Canto marcante; comum em mata secundária."),
    EspecieSul("Tiê-de-topete", "Trichothraupis melanops", _N, "Habita sub-bosque; ocasional em comedouros."),

    # --- Beija-flores ---
    EspecieSul("Beija-flor-tesoura", "Eupetomena macroura", _N, "Grande e comum em jardins urbanos."),
    EspecieSul("Beija-flor-de-fronte-violeta", "Thalurania glaucopis", _N, "Comum em bebedouros; mata e jardim."),
    EspecieSul("Beija-flor-de-papo-branco", "Leucochloris albicollis", _N, "Endêmico do Sul/Sudeste; frequente em bebedouros."),
    EspecieSul("Beija-flor-preto", "Florisuga fusca", _N, "Comum na Mata Atlântica; visita bebedouros."),
    EspecieSul("Beija-flor-de-barba-branca", "Amazilia versicolor", _N, "Comum em jardins e bordas de mata."),

    # --- Endêmicas da Mata Atlântica ---
    EspecieSul("Saíra-sete-cores", "Tangara seledon", _E, "Endêmica da Mata Atlântica; frutíferas."),
    EspecieSul("Saíra-militar", "Tangara cyanocephala", _E, "Endêmica da Mata Atlântica."),
    EspecieSul("Tiê-sangue", "Ramphocelus bresilius", _E, "Endêmica da Mata Atlântica; frutíferas."),
    EspecieSul("Periquito-rico", "Brotogeris tirica", _E, "Endêmico da Mata Atlântica; comum em cidades."),
    EspecieSul("Tiriba-de-testa-vermelha", "Pyrrhura frontalis", _E, "Endêmica da Mata Atlântica; bando ruidoso."),
    EspecieSul("Tangará", "Chiroxiphia caudata", _N, "Comum na Mata Atlântica; macho azul e preto."),
    EspecieSul("Tucano-de-bico-verde", "Ramphastos dicolorus", _N, "Mata Atlântica; visita frutíferas."),
    EspecieSul("Araponga", "Procnias nudicollis", _N, "Vulnerável; canto metálico, Mata Atlântica."),

    # --- Outras nativas notáveis ---
    EspecieSul("Pica-pau-de-banda-branca", "Dryocopus lineatus", _N, "Grande; comum em mata e capoeira."),
    EspecieSul("Pica-pau-verde-barrado", "Colaptes melanochloros", _N, "Comum em áreas abertas arborizadas."),
    EspecieSul("Anu-preto", "Crotophaga ani", _N, "Comum em pastos e capoeiras."),
    EspecieSul("Anu-branco", "Guira guira", _N, "Comum em bandos no campo."),
    EspecieSul("Alma-de-gato", "Piaya cayana", _N, "Comum em mata e cerrado."),
    EspecieSul("Curicaca", "Theristicus caudatus", _N, "Comum em campos do Sul."),
    EspecieSul("Garça-branca-pequena", "Egretta thula", _N, "Comum em corpos d'água."),
    EspecieSul("Biguá", "Nannopterum brasilianus", _N, "Comum em rios e lagoas."),
    EspecieSul("Gavião-carijó", "Rupornis magnirostris", _N, "Rapinosa mais comum do Brasil."),
    EspecieSul("Caracará", "Caracara plancus", _N, "Comum em campos e estradas."),
    EspecieSul("Quiriquiri", "Falco sparverius", _N, "Pequeno falcão; comum em áreas abertas."),
    EspecieSul("Coruja-buraqueira", "Athene cunicularia", _N, "Vive em tocas no solo."),
    EspecieSul("Suindara", "Tyto furcata", _N, "Coruja-das-torres; comum em construções."),
    EspecieSul("Caturrita", "Myiopsitta monachus", _N, "Nativa do Sul; nidifica em colônias."),
    EspecieSul("Choca-da-mata", "Thamnophilus caerulescens", _N, "Comum no sub-bosque."),
    EspecieSul("Andorinha-pequena-de-casa", "Pygochelidon cyanoleuca", _N, "Comum em áreas urbanas."),
    EspecieSul("Rolinha-picui", "Columbina picui", _N, "Comum em solo e comedouros de chão."),

    # --- Migratórias / sazonais ---
    EspecieSul("Tesourinha", "Tyrannus savana", _M, "Migratória austral; aparece na primavera/verão."),
    EspecieSul("Andorinha-azul", "Progne chalybea", _M, "Migratória; chega no verão."),
    EspecieSul("Andorinha-do-campo", "Progne tapera", _M, "Migratória; bandos no verão."),
    EspecieSul("Bem-te-vi-rajado", "Myiodynastes maculatus", _M, "Migratória; reproduz-se no Sul."),
    EspecieSul("Maçarico", "Tringa flavipes", _M, "Migratória neártica; banhados."),
    EspecieSul("Batuíra-de-coleira", "Charadrius collaris", _M, "Migratória; praias e margens."),
    EspecieSul("Trinta-réis-boreal", "Sterna hirundo", _M, "Migratória; costeira."),
    EspecieSul("Papagaio-charão", "Amazona pretrei", _M, "Sazonal; ameaçado, Sul do Brasil."),

    # --- Raras / acidentais / ameaçadas ---
    EspecieSul("Saíra-apunhalada", "Nemosia rourei", _R, "Criticamente ameaçada; raríssima, Espírito Santo/SC."),
    EspecieSul("Jacutinga", "Aburria jacutinga", _R, "Ameaçada; rara na Mata Atlântica."),
    EspecieSul("Macuco", "Tinamus solitarius", _R, "Ameaçada; rara, interior de mata."),
    EspecieSul("Papagaio-de-peito-roxo", "Amazona vinacea", _R, "Ameaçado; registros localizados."),
    EspecieSul("Mutum-de-penacho", "Crax fasciolata", _R, "Raro e ameaçado no Sul."),

    # --- Exóticas / invasoras ---
    EspecieSul("Pardal", "Passer domesticus", _X, "Exótico/invasor; comum em cidades."),
    EspecieSul("Pombo-doméstico", "Columba livia", _X, "Exótico; comum em áreas urbanas."),
    EspecieSul("Mainá", "Acridotheres cristatellus", _X, "Exótico/invasor; vem se expandindo no Sul."),
)

# Índices normalizados para busca O(1).
_POR_CIENTIFICO: dict[str, EspecieSul] = {}
_POR_POPULAR: dict[str, EspecieSul] = {}
for _especie in ESPECIES_SUL:
    _POR_CIENTIFICO.setdefault(_normalizar(_especie.scientific_name), _especie)
    _POR_POPULAR.setdefault(_normalizar(_especie.common_name), _especie)


def info_especie(
    common_name: str | None = None, scientific_name: str | None = None
) -> EspecieSul | None:
    """Devolve os metadados da espécie, se ela estiver na base regional."""
    chave_cientifica = _normalizar(scientific_name)
    if chave_cientifica and chave_cientifica in _POR_CIENTIFICO:
        return _POR_CIENTIFICO[chave_cientifica]
    chave_popular = _normalizar(common_name)
    if chave_popular and chave_popular in _POR_POPULAR:
        return _POR_POPULAR[chave_popular]
    return None


def classificar_status(
    common_name: str | None = None, scientific_name: str | None = None
) -> StatusEcologico:
    """Classifica o status ecológico regional de uma espécie.

    Cruza primeiro o nome científico e, na falta, o popular. Espécies fora da
    base caem em :class:`StatusEcologico.DESCONHECIDA`.
    """
    info = info_especie(common_name=common_name, scientific_name=scientific_name)
    return info.status if info is not None else StatusEcologico.DESCONHECIDA


def descrever(
    common_name: str | None = None, scientific_name: str | None = None
) -> dict[str, str]:
    """Devolve o status e o selo visual prontos para exibição/registro."""
    status = classificar_status(common_name=common_name, scientific_name=scientific_name)
    return {
        "status": status.value,
        "label": STATUS_LABELS[status],
        "badge": STATUS_BADGES[status],
        "icon": STATUS_ICONS[status],
    }
