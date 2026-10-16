"""Contagem de indivíduos e bandos (multi-espécie) por janela de visita.

Recebe, a cada quadro, as detecções **já rastreadas** (com ``track_id`` estável
atribuído pelo :class:`~app.infra.ai.box_tracker.BoxTracker`) e mantém:

- o **total de indivíduos distintos** observados na janela (nº de ``track_id``);
- o **pico simultâneo** (maior número de aves presentes ao mesmo tempo);
- o pico por classe (ex.: "Pássaro") e por espécie (ex.: "Cambacica").

Isso permite registrar frases como *"3 Cambacicas e 2 Saíras presentes
simultaneamente"* — o instante de maior movimento do comedouro.

O contador é barato: apenas conjuntos e contadores, sem custo de imagem.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.infra.ai.detector import Detection


def _pluralizar(nome: str, quantidade: int) -> str:
    """Deixa o nome no plural simples para o resumo em pt-BR."""
    if quantidade == 1:
        return nome
    if nome.endswith("s"):
        return nome
    if nome.endswith("l"):
        return nome + "is"  # ex.: "Cardeal" -> "Cardeais"
    if nome.endswith("r") or nome.endswith("z"):
        return nome + "es"
    if nome.endswith("m"):
        return nome[:-1] + "ns"  # ex.: "Bem" -> "Bens"
    return nome + "s"


@dataclass
class ContadorIndividuos:
    """Agrega a contagem de indivíduos ao longo de uma janela de evento."""

    # Piso para considerar uma ave "nova" (evita contar ruído de rastreio).
    _ids_vistos: set[int] = field(default_factory=set, init=False)
    _pico_simultaneo: int = field(default=0, init=False)
    _pico_por_classe: dict[str, int] = field(default_factory=dict, init=False)
    _pico_por_especie: dict[str, int] = field(default_factory=dict, init=False)
    _quadros: int = field(default=0, init=False)

    # ------------------------------------------------------------------ #
    # Alimentação
    # ------------------------------------------------------------------ #
    def registrar(
        self,
        deteccoes: list[Detection],
        especies_por_track: dict[int, str] | None = None,
    ) -> None:
        """Registra um quadro de detecções rastreadas.

        ``especies_por_track`` mapeia ``track_id`` → nome da espécie (quando um
        classificador de espécies está disponível); sem ele, agrega por classe.
        """
        self._quadros += 1
        ids_ativos: set[int] = set()
        por_classe: dict[str, int] = {}
        por_especie: dict[str, int] = {}

        for deteccao in deteccoes:
            track_id = deteccao.track_id
            if track_id is not None:
                ids_ativos.add(track_id)
                self._ids_vistos.add(track_id)

            classe = str(deteccao.class_name or "bird")
            por_classe[classe] = por_classe.get(classe, 0) + 1

            if especies_por_track and track_id is not None:
                especie = especies_por_track.get(track_id)
                if especie:
                    por_especie[especie] = por_especie.get(especie, 0) + 1

        # Sem track_id (ex.: rastreio desligado): usa a contagem do quadro.
        if not ids_ativos:
            self._pico_simultaneo = max(self._pico_simultaneo, len(deteccoes))
        else:
            self._pico_simultaneo = max(self._pico_simultaneo, len(ids_ativos))

        for classe, quantidade in por_classe.items():
            self._pico_por_classe[classe] = max(
                self._pico_por_classe.get(classe, 0), quantidade
            )
        for especie, quantidade in por_especie.items():
            self._pico_por_especie[especie] = max(
                self._pico_por_especie.get(especie, 0), quantidade
            )

    # ------------------------------------------------------------------ #
    # Resultados
    # ------------------------------------------------------------------ #
    @property
    def individuos_total(self) -> int:
        """Nº de indivíduos distintos observados na janela."""
        return len(self._ids_vistos)

    @property
    def pico_simultaneo(self) -> int:
        """Maior número de aves presentes ao mesmo tempo."""
        return self._pico_simultaneo

    @property
    def pico_por_especie(self) -> dict[str, int]:
        return dict(self._pico_por_especie)

    @property
    def pico_por_classe(self) -> dict[str, int]:
        return dict(self._pico_por_classe)

    def resumo(self) -> dict[str, object]:
        """Resumo estruturado pronto para os metadados da visita."""
        return {
            "individuos_total": self.individuos_total,
            "pico_simultaneo": self.pico_simultaneo,
            "pico_por_classe": self.pico_por_classe,
            "pico_por_especie": self.pico_por_especie,
            "descricao": self.descricao(),
        }

    def descricao(self) -> str:
        """Frase legível do bando no pico (ex.: "3 Cambacicas e 2 Saíras")."""
        pico = self._pico_por_especie
        if not pico:
            if self.pico_simultaneo > 1:
                return f"{self.pico_simultaneo} aves simultâneas"
            return ""

        # Ordena da espécie mais numerosa para a menos numerosa.
        itens = sorted(pico.items(), key=lambda item: (-item[1], item[0]))
        partes = [
            f"{quantidade} {_pluralizar(nome, quantidade)}"
            for nome, quantidade in itens
            if quantidade > 0
        ]
        return " e ".join(partes[:3])
