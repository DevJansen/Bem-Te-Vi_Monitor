"""Insights estatísticos que cruzam visitas com dados meteorológicos.

Recebe as visitas já resolvidas por ``AnalyticsRepository.weather_visit_rows`` e
produz agregações e frases prontas em pt-BR para o painel:

* faixas de temperatura × nº de visitas e de espécies diferentes;
* dias/visitas chuvosos vs. secos (visitas por dia);
* horário médio de aparecimento em condições frias vs. quentes;
* mudança de horário por espécie conforme a temperatura;
* cards de "resumo inteligente".

O cálculo é feito em Python (o volume é local e modesto), o que facilita tratar
fusos horários, mediana e formatação de horário com clareza.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable

from app.services.weather_service import (
    CATEGORY_CLOUDY,
    CATEGORY_FOG,
    CATEGORY_RAIN,
    CATEGORY_SNOW,
    CATEGORY_STORM,
    CATEGORY_SUNNY,
    CATEGORY_UNKNOWN,
    category_for_label,
)

logger = logging.getLogger(__name__)

# Faixas de temperatura: (limite inferior, limite superior, rótulo pt-BR).
# O limite inferior é inclusivo e o superior é exclusivo.
TEMPERATURE_BANDS: tuple[tuple[float | None, float | None, str], ...] = (
    (None, 10.0, "< 10°C"),
    (10.0, 15.0, "10–15°C"),
    (15.0, 20.0, "15–20°C"),
    (20.0, 25.0, "20–25°C"),
    (25.0, 30.0, "25–30°C"),
    (30.0, None, "≥ 30°C"),
)

# Categorias consideradas "chuva" ao comparar dias chuvosos e secos.
RAIN_CATEGORIES = {CATEGORY_RAIN, CATEGORY_STORM}

# Emoji por categoria ampla de clima (usado nos gráficos).
_CATEGORY_ICONS: dict[str, str] = {
    CATEGORY_SUNNY: "☀️",
    CATEGORY_CLOUDY: "☁️",
    CATEGORY_RAIN: "🌧️",
    CATEGORY_STORM: "⛈️",
    CATEGORY_SNOW: "❄️",
    CATEGORY_FOG: "🌫️",
}

# Mínimos para considerar confiável um insight de horário por espécie.
SPECIES_MIN_TOTAL = 4
SPECIES_MIN_PER_SIDE = 2
# Diferença mínima (minutos) para dizer que o horário realmente mudou.
TIMING_RELEVANT_MINUTES = 15


def _as_float(value: Any) -> float | None:
    """Converte um valor (possivelmente nulo) em float, ou ``None``."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_local(value: Any) -> datetime | None:
    """Interpreta a data/hora gravada (UTC) e converte para o fuso local.

    Aceita o formato do pipeline (``...Z``) e o ``isoformat`` com offset. O
    horário local é o que o observador vê no painel, tornando os insights de
    "horário de aparecimento" coerentes com o restante da interface.
    """
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def _mean(values: Iterable[float | None]) -> float | None:
    data = [value for value in values if value is not None]
    if not data:
        return None
    return sum(data) / len(data)


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _format_hour(decimal_hour: float | None) -> str | None:
    """Converte uma hora decimal (ex.: 7.5) no rótulo ``HH:MM``."""
    if decimal_hour is None:
        return None
    total_minutes = int(round(decimal_hour * 60)) % (24 * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _humanize_minutes(minutes: float) -> str:
    """Transforma minutos em um texto curto (``35 min``, ``1h27``)."""
    total = int(round(abs(minutes)))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins} min"


def _top_species(visits: list[dict[str, Any]]) -> str | None:
    if not visits:
        return None
    counts: dict[str, int] = defaultdict(int)
    for visit in visits:
        counts[visit["species"]] += 1
    return max(counts.items(), key=lambda item: (item[1], item[0]))[0]


def _normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Padroniza uma linha do banco em um dicionário de análise."""
    moment = _parse_local(row.get("detected_at"))
    if moment is None:
        return None
    condition = row.get("weather_code")
    return {
        "moment": moment,
        "hour": moment.hour + moment.minute / 60.0,
        "date": moment.date(),
        "temperature": _as_float(row.get("temperature")),
        "humidity": _as_float(row.get("humidity")),
        "condition": condition or None,
        "category": category_for_label(condition),
        "species": row.get("species_name") or "Ave (genérica)",
        "scientific": row.get("scientific_name"),
    }


def _summarize(visits: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumo estatístico de um conjunto de visitas.

    Devolve contagens, médias de horário/temperatura/umidade e a espécie mais
    frequente — a base comum de todas as agregações de insights.
    """
    days = {visit["date"] for visit in visits}
    avg_hour = _mean(visit["hour"] for visit in visits)
    temperatures = [visit["temperature"] for visit in visits]
    humidities = [visit["humidity"] for visit in visits]
    return {
        "visits": len(visits),
        "distinct_species": len({visit["species"] for visit in visits}),
        "active_days": len(days),
        "visits_per_day": _round(len(visits) / max(1, len(days)), 2),
        "avg_hour": _round(avg_hour, 2),
        "avg_hour_label": _format_hour(avg_hour),
        "avg_temperature": _round(_mean(temperatures)),
        "avg_humidity": _round(_mean(humidities)),
        "top_species": _top_species(visits),
    }


def _temperature_ranges(with_temp: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distribui as visitas pelas faixas de temperatura."""
    ranges: list[dict[str, Any]] = []
    for lower, upper, label in TEMPERATURE_BANDS:
        band = [
            visit
            for visit in with_temp
            if (lower is None or visit["temperature"] >= lower)
            and (upper is None or visit["temperature"] < upper)
        ]
        summary = _summarize(band)
        summary.update(
            {
                "label": label,
                "min_temperature": lower,
                "max_temperature": upper,
            }
        )
        ranges.append(summary)
    return ranges


def _condition_summaries(visits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa as visitas por categoria ampla de clima (ex.: Ensolarado, Chuva)."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for visit in visits:
        if visit["category"] == CATEGORY_UNKNOWN:
            continue
        groups[visit["category"]].append(visit)

    summaries: list[dict[str, Any]] = []
    for category, group in groups.items():
        summary = _summarize(group)
        summary.update(
            {"condition": category, "icon": _CATEGORY_ICONS.get(category, "🌡️")}
        )
        summaries.append(summary)
    summaries.sort(key=lambda item: (-item["visits"], item["condition"]))
    return summaries


def _labeled_summary(
    label: str, icon: str, visits: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Resumo de um grupo rotulado (usado em "chuva" e "tempo seco")."""
    if not visits:
        return None
    summary = _summarize(visits)
    summary.update({"condition": label, "icon": icon})
    return summary


def _relative_diff(
    rainy: dict[str, Any] | None, dry: dict[str, Any] | None
) -> float | None:
    """Diferença percentual de visitas/dia entre chuva e tempo seco."""
    if not rainy or not dry:
        return None
    base = dry.get("visits_per_day") or 0
    if base <= 0:
        return None
    return (rainy["visits_per_day"] - base) / base * 100.0


def _temperature_threshold(with_temp: list[dict[str, Any]]) -> float | None:
    """Limiar (mediana) que separa condições "frias" e "quentes".

    Com dois ou mais dias, usa a mediana da temperatura média de cada dia; com
    um único dia, usa a mediana das temperaturas das visitas.
    """
    if not with_temp:
        return None
    by_day: dict[Any, list[float]] = defaultdict(list)
    for visit in with_temp:
        by_day[visit["date"]].append(visit["temperature"])
    if len(by_day) >= 2:
        day_averages = [
            value for value in (_mean(temps) for temps in by_day.values())
            if value is not None
        ]
        threshold = median(day_averages) if day_averages else None
    else:
        threshold = median([visit["temperature"] for visit in with_temp])
    return None if threshold is None else round(threshold, 1)


def _split_by_temperature(
    with_temp: list[dict[str, Any]], threshold: float | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separa as visitas em frias (≤ limiar) e quentes (> limiar)."""
    if threshold is None:
        return [], []
    cold = [v for v in with_temp if v["temperature"] <= threshold]
    hot = [v for v in with_temp if v["temperature"] > threshold]
    if not cold or not hot:
        # Garante dois lados mesmo quando há pouquíssima variação de temperatura.
        visit_median = median([v["temperature"] for v in with_temp])
        cold = [v for v in with_temp if v["temperature"] <= visit_median]
        hot = [v for v in with_temp if v["temperature"] > visit_median]
    return cold, hot


def _periods(
    cold: list[dict[str, Any]],
    hot: list[dict[str, Any]],
    threshold: float | None,
) -> list[dict[str, Any]]:
    """Resumos dos períodos "mais frio" e "mais quente"."""
    if threshold is None:
        return []
    cold_summary = _summarize(cold)
    cold_summary.update(
        {"period": "frio", "label": f"Dias mais frios (≤ {threshold:g}°C)"}
    )
    hot_summary = _summarize(hot)
    hot_summary.update(
        {"period": "quente", "label": f"Dias mais quentes (> {threshold:g}°C)"}
    )
    return [cold_summary, hot_summary]


def _timing_summary(
    species: str, minutes_earlier: float, direction: str, threshold: float
) -> str:
    """Frase pronta sobre a mudança de horário de uma espécie."""
    if direction == "similar":
        return (
            f"{species} mantêm horários parecidos em condições frias e quentes."
        )
    delta = _humanize_minutes(minutes_earlier)
    when = "mais cedo" if direction == "earlier" else "mais tarde"
    return (
        f"{species} aparecem cerca de {delta} {when} quando a temperatura "
        f"passa de {threshold:g}°C."
    )


def _species_timing(
    with_temp: list[dict[str, Any]], threshold: float | None
) -> list[dict[str, Any]]:
    """Mudança de horário por espécie entre condições frias e quentes."""
    if threshold is None:
        return []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for visit in with_temp:
        groups[visit["species"]].append(visit)

    results: list[dict[str, Any]] = []
    for species, visits in groups.items():
        if len(visits) < SPECIES_MIN_TOTAL:
            continue
        cold = [v for v in visits if v["temperature"] <= threshold]
        hot = [v for v in visits if v["temperature"] > threshold]
        if len(cold) < SPECIES_MIN_PER_SIDE or len(hot) < SPECIES_MIN_PER_SIDE:
            continue
        cold_hour = _mean(v["hour"] for v in cold)
        hot_hour = _mean(v["hour"] for v in hot)
        if cold_hour is None or hot_hour is None:
            continue
        minutes_earlier = (cold_hour - hot_hour) * 60.0
        if abs(minutes_earlier) >= TIMING_RELEVANT_MINUTES:
            direction = "earlier" if minutes_earlier > 0 else "later"
        else:
            direction = "similar"
        scientific = next(
            (v["scientific"] for v in visits if v["scientific"]), None
        )
        results.append(
            {
                "species": species,
                "scientific_name": scientific,
                "cold_avg_hour": _round(cold_hour, 2),
                "hot_avg_hour": _round(hot_hour, 2),
                "cold_visits": len(cold),
                "hot_visits": len(hot),
                "minutes_earlier": _round(minutes_earlier, 1),
                "direction": direction,
                "summary": _timing_summary(
                    species, minutes_earlier, direction, threshold
                ),
            }
        )
    results.sort(key=lambda item: abs(item["minutes_earlier"] or 0), reverse=True)
    return results[:5]


def _insight_cards(
    *,
    best_range: dict[str, Any] | None,
    rainy: dict[str, Any] | None,
    dry: dict[str, Any] | None,
    rainy_vs_dry: float | None,
    periods: list[dict[str, Any]],
    species_timing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Monta os cards de "resumo inteligente" exibidos no painel."""
    cards: list[dict[str, Any]] = []

    if best_range and best_range["visits"] > 0:
        cards.append(
            {
                "id": "best_temperature_range",
                "icon": "🌡️",
                "title": "Faixa de temperatura preferida",
                "description": (
                    f"A faixa de {best_range['label']} é a que atrai mais "
                    f"espécies diferentes: {best_range['distinct_species']} "
                    f"espécie(s) em {best_range['visits']} visita(s)."
                ),
                "tone": "positive",
            }
        )

    if rainy and dry and rainy_vs_dry is not None:
        direction = "mais" if rainy_vs_dry >= 0 else "menos"
        cards.append(
            {
                "id": "rainy_vs_dry",
                "icon": "🌧️",
                "title": "Chuva x tempo seco",
                "description": (
                    f"Em condições de chuva a média é de "
                    f"{rainy['visits_per_day']:.2f} visita(s)/dia, "
                    f"{abs(rainy_vs_dry):.0f}% {direction} do que em tempo seco "
                    f"({dry['visits_per_day']:.2f}/dia)."
                ),
                "tone": "info",
            }
        )

    cold_period = next((p for p in periods if p["period"] == "frio"), None)
    hot_period = next((p for p in periods if p["period"] == "quente"), None)
    if (
        cold_period
        and hot_period
        and cold_period["avg_hour_label"]
        and hot_period["avg_hour_label"]
    ):
        diff_minutes = (cold_period["avg_hour"] - hot_period["avg_hour"]) * 60.0
        if abs(diff_minutes) >= TIMING_RELEVANT_MINUTES:
            when = "mais cedo" if diff_minutes > 0 else "mais tarde"
            detail = (
                f"cerca de {_humanize_minutes(diff_minutes)} {when} no calor"
            )
        else:
            detail = "praticamente no mesmo horário"
        cards.append(
            {
                "id": "cold_vs_hot_timing",
                "icon": "⏰",
                "title": "Horário no frio x no calor",
                "description": (
                    f"No frio as aves aparecem em média às "
                    f"{cold_period['avg_hour_label']}; no calor, às "
                    f"{hot_period['avg_hour_label']} ({detail})."
                ),
                "tone": "neutral",
            }
        )

    if species_timing:
        first = species_timing[0]
        cards.append(
            {
                "id": "species_timing",
                "icon": "🐦",
                "title": "Horário por espécie",
                "description": first["summary"],
                "tone": "positive" if first["direction"] != "similar" else "neutral",
            }
        )

    return cards


def build_weather_insights(
    rows: list[dict[str, Any]], *, total_visits: int
) -> dict[str, Any]:
    """Constrói o payload completo do endpoint de insights de clima e hábitos."""
    visits = [n for n in (_normalize_row(row) for row in rows) if n is not None]
    with_temp = [v for v in visits if v["temperature"] is not None]

    ranges = _temperature_ranges(with_temp) if with_temp else []
    best_range: dict[str, Any] | None = None
    candidates = [r for r in ranges if r["visits"] > 0]
    if candidates:
        best_range = max(
            candidates, key=lambda r: (r["distinct_species"], r["visits"])
        )

    conditions = _condition_summaries(visits)
    rainy_visits = [v for v in visits if v["category"] in RAIN_CATEGORIES]
    dry_visits = [
        v
        for v in visits
        if v["category"] not in RAIN_CATEGORIES
        and v["category"] != CATEGORY_UNKNOWN
    ]
    rainy = _labeled_summary("Chuva", "🌧️", rainy_visits)
    dry = _labeled_summary("Tempo seco", "🌤️", dry_visits)
    rainy_vs_dry = _relative_diff(rainy, dry)

    threshold = _temperature_threshold(with_temp)
    cold, hot = _split_by_temperature(with_temp, threshold)
    periods = _periods(cold, hot, threshold)
    species_timing = _species_timing(with_temp, threshold)

    insights = _insight_cards(
        best_range=best_range,
        rainy=rainy,
        dry=dry,
        rainy_vs_dry=rainy_vs_dry,
        periods=periods,
        species_timing=species_timing,
    )

    return {
        "total_visits": int(total_visits),
        "visits_with_weather": len(visits),
        "cold_threshold_celsius": threshold,
        "temperature_ranges": ranges,
        "best_temperature_range": best_range,
        "conditions": conditions,
        "rainy": rainy,
        "dry": dry,
        "rainy_vs_dry_percent": _round(rainy_vs_dry, 1),
        "periods": periods,
        "species_timing": species_timing,
        "insights": insights,
    }
