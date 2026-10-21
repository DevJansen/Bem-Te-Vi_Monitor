"""Anotação ornitológica gerada por IA.

Compõe, a partir dos metadados estruturados da janela de evento (espécie, status
ecológico, comportamento, contagem, clima, nitidez e certeza), uma **frase
natural em pt-BR** que resume o registro como um breve laudo de campo.

O texto é determinístico e *template-based* (não é um LLM): usa apenas dados que a
própria IA já mediu, evitando qualquer alucinação. É a "voz" do motor cognitivo
no painel — por exemplo:

    "Registro de Tangara sayaca (Sanhaçu-cinzento), alimentando-se em grupo de
     3 indivíduos, sob temperatura de 24°C e céu limpo. Espécie nativa."

Nada aqui levanta exceção: sem dados, devolve uma frase neutra e honesta.
"""

from __future__ import annotations

from typing import Any

# Trecho de comportamento (usa o tipo cru: feeding/perching/moving).
_COMPORTAMENTO_TEXTO: dict[str, str] = {
    "feeding": "alimentando-se ativamente",
    "perching": "pousada nas proximidades",
    "moving": "em deslocamento",
}


def _temperatura_texto(temperatura: float | None) -> str | None:
    if temperatura is None:
        return None
    try:
        return f"{round(float(temperatura))}°C"
    except (TypeError, ValueError):
        return None


def _clima_texto(
    temperatura: float | None, categoria_clima: str | None
) -> str | None:
    """Monta o trecho climático ("sob temperatura de 24°C e céu limpo")."""
    temp = _temperatura_texto(temperatura)
    categoria = (categoria_clima or "").strip()
    if temp and categoria:
        return f"sob temperatura de {temp} e {categoria.lower()}"
    if temp:
        return f"sob temperatura de {temp}"
    if categoria:
        return f"sob {categoria.lower()}"
    return None


def _nitidez_texto(nitidez: float | None) -> str | None:
    """Qualifica a nitidez do quadro escolhido (Laplacian variância)."""
    if nitidez is None:
        return None
    try:
        valor = float(nitidez)
    except (TypeError, ValueError):
        return None
    if valor >= 300:
        qualidade = "excelente"
    elif valor >= 120:
        qualidade = "boa"
    elif valor >= 40:
        qualidade = "aceitável"
    else:
        qualidade = "baixa"
    return f"nitidez {qualidade} ({round(valor, 1)})"


def gerar_anotacao(
    *,
    species: str | None = None,
    scientific_name: str | None = None,
    ecological_label: str | None = None,
    ecological_status: str | None = None,
    behavior: str | None = None,
    individuals_peak: int | None = None,
    temperature: float | None = None,
    weather_category: str | None = None,
    confidence: float | None = None,
    sharpness: float | None = None,
) -> str:
    """Compõe a anotação ornitológica em pt-BR a partir dos dados da visita."""
    nome = (species or "").strip() or "Ave"
    nome_cientifico = (scientific_name or "").strip()

    # Sujeito: "Registro de Tangara sayaca (Sanhaçu-cinzento)".
    if nome_cientifico and nome_cientifico.lower() != nome.lower():
        sujeito = f"Registro de {nome_cientifico} ({nome})"
    else:
        sujeito = f"Registro de {nome}"

    # Orações descritivas (comportamento, grupo, clima, nitidez).
    oracoes: list[str] = []

    comportamento = _COMPORTAMENTO_TEXTO.get((behavior or "").strip().lower())
    if comportamento:
        oracoes.append(comportamento)

    if individuals_peak is not None:
        try:
            total = int(individuals_peak)
        except (TypeError, ValueError):
            total = 0
        if total > 1:
            oracoes.append(f"em grupo de {total} indivíduos")

    clima = _clima_texto(temperature, weather_category)
    if clima:
        oracoes.append(clima)

    nitidez = _nitidez_texto(sharpness)
    if nitidez:
        oracoes.append(nitidez)

    frase = sujeito
    if oracoes:
        frase = f"{sujeito}, " + ", ".join(oracoes)
    frase += "."

    # Fecho ecológico: dá sentido de conservação ao registro.
    status = (ecological_status or "").strip().lower()
    rotulo = (ecological_label or "").strip()
    if status == "rara":
        frase += " Espécie de registro raro — atenção para conservação."
    elif status == "endemica":
        frase += " Espécie endêmica da região."
    elif status == "migratoria":
        frase += " Espécie migratória de passagem pela região."
    elif status == "exotica":
        frase += " Espécie exótica (não nativa)."
    elif rotulo and status not in {"", "desconhecida"}:
        frase += f" Espécie {rotulo.lower()}."

    return frase


def montar_analise_ia(
    *,
    species: str | None = None,
    scientific_name: str | None = None,
    ecological: dict[str, Any] | None = None,
    behavior: str | None = None,
    behavior_label: str | None = None,
    individuals_peak: int | None = None,
    temperature: float | None = None,
    weather_category: str | None = None,
    confidence: float | None = None,
    sharpness: float | None = None,
) -> dict[str, Any]:
    """Empacota a análise enriquecida da IA (JSON pronto para a visita).

    Reúne o que a IA "pensou" sobre o melhor quadro: identificação, contagem
    simultânea no comedouro, status ecológico, nitidez, certeza e a anotação
    ornitológica gerada automaticamente.
    """
    eco = ecological or {}
    status = eco.get("status")
    rotulo = eco.get("label")
    return {
        "engine": "Bem-Te-Vi Core v1.0",
        "species": species,
        "scientific_name": scientific_name,
        "individuals_peak": individuals_peak,
        "ecological_status": status,
        "ecological_label": rotulo,
        "ecological_badge": eco.get("badge"),
        "behavior": behavior,
        "behavior_label": behavior_label,
        "confidence": round(float(confidence), 4) if confidence is not None else None,
        "sharpness": round(float(sharpness), 2) if sharpness is not None else None,
        "temperature": temperature,
        "weather": weather_category,
        "annotation": gerar_anotacao(
            species=species,
            scientific_name=scientific_name,
            ecological_label=rotulo,
            ecological_status=status,
            behavior=behavior,
            individuals_peak=individuals_peak,
            temperature=temperature,
            weather_category=weather_category,
            confidence=confidence,
            sharpness=sharpness,
        ),
    }
