"""Diário de Campo geolocalizado e exportação para ciência cidadã.

O serviço compila, para um dia (e opcionalmente um jardim/câmera), um relatório
pronto para leitura e para envio ao **eBird** (Cornell Lab of Ornithology) ou
para uma planilha CSV limpa:

* agrupa as visitas de aves por espécie e por jardim;
* recupera coordenadas, fuso e país da câmera;
* resume o clima do dia a partir das condições gravadas em cada visita
  (Open-Meteo) e, quando não há registro, consulta o clima atual do jardim;
* seleciona foto tratada, clipe e thumbnail de cada espécie;
* gera um texto de diário em pt-BR, com horários, comportamento e confiança.

O módulo é somente leitura: nenhuma exportação altera o banco ou a mídia.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import re
import unicodedata
from collections import Counter
from datetime import date as date_type
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.domain.avifauna_sul import STATUS_LABELS, StatusEcologico
from app.infra.database.connection import db_session

logger = logging.getLogger(__name__)

_MONTHS_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

# Ordem oficial das 19 colunas do **eBird Record Format** (formato de registro,
# uma linha por observação). O eBird exige que o arquivo seja enviado **sem a
# linha de cabeçalho**; esta constante fica como documentação e referência de
# testes. Nomes de colunas e ordem seguem o modelo oficial do Cornell Lab.
_EBIRD_COLUMNS = (
    "Common Name",
    "Genus",
    "Species",
    "Number",
    "Species Comments",
    "Location Name",
    "Latitude",
    "Longitude",
    "Date",
    "Start Time",
    "State/Province",
    "Country",
    "Protocol",
    "Number of Observers",
    "Duration",
    "All observations reported?",
    "Effort Distance Miles",
    "Effort area acres",
    "Submission Comments",
)

_CLEAN_COLUMNS = (
    "data",
    "horario",
    "jardim",
    "camera",
    "especie",
    "nome_cientifico",
    "status_ecologico",
    "quantidade",
    "confianca_maxima",
    "primeiro_registro",
    "ultimo_registro",
    "latitude",
    "longitude",
    "temperatura_c",
    "umidade",
    "clima",
    "observacoes",
)

# Rótulos genéricos não têm valor taxonômico para o eBird: ficam fora do
# checklist, mas continuam visíveis no diário/planilha para o observador.
_GENERIC_SPECIES = {
    "bird",
    "ave",
    "passaro",
    "pássaro",
    "passaro desconhecido",
    "pássaro desconhecido",
    "ave desconhecida",
    "ave (generica)",
    "ave (genérica)",
}

# O eBird exige o código de duas letras do país. A câmera guarda o país como
# texto livre (preenchido pela busca de coordenadas), então normalizamos nomes
# comuns em pt-BR/en para o código ISO 3166-1 alpha-2. Países não listados ficam
# em branco; o eBird ainda pode inferir o local pelas coordenadas.
_COUNTRY_CODES = {
    "brasil": "BR",
    "brazil": "BR",
    "argentina": "AR",
    "uruguai": "UY",
    "uruguay": "UY",
    "paraguai": "PY",
    "paraguay": "PY",
    "chile": "CL",
    "bolivia": "BO",
    "peru": "PE",
    "colombia": "CO",
    "equador": "EC",
    "ecuador": "EC",
    "venezuela": "VE",
    "guiana": "GY",
    "guyana": "GY",
    "suriname": "SR",
    "guiana francesa": "GF",
    "costa rica": "CR",
    "panama": "PA",
    "mexico": "MX",
    "guatemala": "GT",
    "belize": "BZ",
    "honduras": "HN",
    "el salvador": "SV",
    "nicaragua": "NI",
    "cuba": "CU",
    "jamaica": "JM",
    "haiti": "HT",
    "republica dominicana": "DO",
    "porto rico": "PR",
    "puerto rico": "PR",
    "estados unidos": "US",
    "united states": "US",
    "eua": "US",
    "usa": "US",
    "canada": "CA",
    "portugal": "PT",
    "espanha": "ES",
    "spain": "ES",
    "franca": "FR",
    "france": "FR",
    "alemanha": "DE",
    "germany": "DE",
    "italia": "IT",
    "italy": "IT",
    "reino unido": "GB",
    "united kingdom": "GB",
    "uk": "GB",
    "irlanda": "IE",
    "ireland": "IE",
    "holanda": "NL",
    "paises baixos": "NL",
    "netherlands": "NL",
    "belgica": "BE",
    "belgium": "BE",
    "suica": "CH",
    "switzerland": "CH",
    "austria": "AT",
    "suecia": "SE",
    "sweden": "SE",
    "noruega": "NO",
    "norway": "NO",
    "dinamarca": "DK",
    "denmark": "DK",
    "finlandia": "FI",
    "finland": "FI",
    "polonia": "PL",
    "poland": "PL",
    "republica tcheca": "CZ",
    "czechia": "CZ",
    "hungria": "HU",
    "hungary": "HU",
    "romenia": "RO",
    "romania": "RO",
    "grecia": "GR",
    "greece": "GR",
    "turquia": "TR",
    "turkey": "TR",
    "russia": "RU",
    "ucrania": "UA",
    "ukraine": "UA",
    "australia": "AU",
    "nova zelandia": "NZ",
    "new zealand": "NZ",
    "africa do sul": "ZA",
    "south africa": "ZA",
    "japao": "JP",
    "japan": "JP",
    "china": "CN",
    "india": "IN",
    "indonesia": "ID",
    "tailandia": "TH",
    "thailand": "TH",
    "filipinas": "PH",
    "philippines": "PH",
    "israel": "IL",
    "emirados arabes unidos": "AE",
    "united arab emirates": "AE",
}

_WEATHER_ICONS = (
    ("tempestade", "⛈️"),
    ("trovoada", "⛈️"),
    ("neve", "❄️"),
    ("granizo", "🌨️"),
    ("chuva", "🌧️"),
    ("garoa", "🌦️"),
    ("névoa", "🌫️"),
    ("neblina", "🌫️"),
    ("nublado", "☁️"),
    ("encoberto", "☁️"),
    ("limpo", "☀️"),
    ("sol", "☀️"),
    ("claro", "🌤️"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_local() -> str:
    return datetime.now().astimezone().date().isoformat()


def _parse_day(day: str | None) -> str:
    """Valida ``YYYY-MM-DD`` (ou devolve a data local de hoje)."""
    if not day:
        return _today_local()
    try:
        return date_type.fromisoformat(day.strip()).isoformat()
    except ValueError as exc:
        raise ValueError("Data inválida. Use o formato AAAA-MM-DD.") from exc


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _time_label(
    iso_timestamp: str | None, timezone_name: str | None = None
) -> str:
    """Horário local (HH:MM) de um timestamp ISO, no fuso do jardim.

    Usa ``zoneinfo`` quando o banco traz o fuso da câmera (ex.: jardins em
    outros países). Se o fuso for inválido ou a base IANA não estiver
    disponível, cai no fuso local do servidor.
    """
    if not iso_timestamp:
        return "--:--"
    try:
        moment = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        zone = None
        if timezone_name:
            try:
                from zoneinfo import ZoneInfo

                zone = ZoneInfo(str(timezone_name))
            except Exception:
                zone = None
        return moment.astimezone(zone).strftime("%H:%M")
    except (TypeError, ValueError):
        return "--:--"


def _first_time_label(
    sightings: list[dict[str, Any]], timezone_name: str | None
) -> str:
    """Rótulo do primeiro horário do grupo no fuso do jardim."""
    if not sightings:
        return "--:--"
    first = min(value.get("detected_at") or "" for value in sightings)
    for sighting in sightings:
        if sighting.get("detected_at") == first and sighting.get("time_label"):
            return str(sighting["time_label"])
    return _time_label(first, timezone_name)


def _duration_minutes(first: str | None, last: str | None) -> int:
    try:
        start = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(1, int(math.ceil((end - start).total_seconds() / 60.0)))
    except (TypeError, ValueError):
        return 1


def _ebird_text(value: Any) -> str:
    """Sanitiza um campo para o eBird Record Format.

    O eBird não aceita aspas, retornos de linha nem delimitadores soltos no
    conteúdo. Trocamos aspas por apóstrofo, quebras por espaço e vírgulas por
    ponto e vírgula; assim o CSV permanece com vírgula como único delimitador e
    sem campos entre aspas.
    """
    if value is None:
        return ""
    text = str(value)
    text = text.replace('"', "'").replace("\r", " ").replace("\n", " ")
    text = text.replace(",", ";")
    return " ".join(text.split())


def _ebird_date(day: str) -> str:
    """Data no formato exigido pelo eBird: ``mês/dia/ano``."""
    try:
        parsed = date_type.fromisoformat(str(day))
        return f"{parsed.month}/{parsed.day}/{parsed.year}"
    except (TypeError, ValueError):
        return _ebird_text(day)


def _scientific_parts(scientific_name: str | None) -> tuple[str, str]:
    """Separa o nome científico em ``(gênero, espécie)`` para o eBird."""
    tokens = str(scientific_name or "").strip().split()
    if len(tokens) >= 2:
        return tokens[0], " ".join(tokens[1:])
    if tokens:
        return tokens[0], ""
    return "", ""


def _normalize_region_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold().strip()


def _ebird_region(country: str | None) -> tuple[str, str]:
    """Converte o país livre da câmera em ``(estado, país)`` do eBird.

    Aceita ``Brasil``, ``Brazil``, ``BR``, ``BR-SP`` e ``Brasil, SP``. O estado
    só é preenchido quando o texto traz um código de 1 a 3 letras; caso
    contrário fica vazio e o eBird usa as coordenadas para localizar o jardim.
    """
    text = str(country or "").strip()
    if not text:
        return "", ""

    code_match = re.match(
        r"^([A-Za-z]{2})\s*[-/]\s*([A-Za-z]{1,3})$", text
    )
    if code_match:
        return code_match.group(2).upper(), code_match.group(1).upper()

    parts = [
        part.strip()
        for part in re.split(r"[,/;|]", text)
        if part.strip()
    ]
    name = parts[0] if parts else ""
    state = ""
    if len(parts) > 1 and 1 <= len(parts[1]) <= 3:
        state = parts[1].upper()

    if len(name) == 2 and name.isalpha():
        return state, name.upper()
    return state, _COUNTRY_CODES.get(_normalize_region_name(name), "")


def _long_date(day: str) -> str:
    try:
        parsed = date_type.fromisoformat(day)
        return f"{parsed.day} de {_MONTHS_PT[parsed.month - 1]} de {parsed.year}"
    except (ValueError, IndexError):
        return day


def _weather_icon(condition: str | None) -> str:
    text = (condition or "").casefold()
    for token, icon in _WEATHER_ICONS:
        if token in text:
            return icon
    return "🌤️"


def _ecological_label(status: str | None) -> str | None:
    if not status:
        return None
    try:
        return STATUS_LABELS[StatusEcologico(status)]
    except (ValueError, KeyError):
        return str(status).replace("_", " ").title()


def _media_url(relative: str | None) -> str | None:
    if not relative:
        return None
    normalized = relative.replace("\\", "/").lstrip("/")
    if normalized.startswith("captures/"):
        return f"/{normalized}"
    return f"/captures/{normalized}"


def _clip_url(relative: str | None) -> str | None:
    if not relative:
        return None
    name = Path(relative.replace("\\", "/")).name
    return f"/api/videos/{name}" if name else None


def _crop_url(
    visit_id: str,
    metadata: dict[str, Any],
    crops_dir: Path | None = None,
) -> str | None:
    """URL do recorte apenas quando ele realmente existe no padrão esperado.

    Algumas visitas antigas não têm ``crop_path`` no metadado, mas o recorte
    tratado existe em ``app-data/crops/{visit_id}.jpg``. Nesse caso a URL
    continua válida (o endpoint ``/api/visits/{id}/crop`` reconstrói o caminho).
    """
    expected = f"crops/{visit_id}.jpg"
    if metadata.get("crop_path") == expected:
        return f"/api/visits/{visit_id}/crop"
    if crops_dir is not None and (crops_dir / f"{visit_id}.jpg").is_file():
        return f"/api/visits/{visit_id}/crop"
    return None


def _condition_from_rows(rows: list[dict[str, Any]]) -> str | None:
    values = [
        str(row.get("weather_code")).strip()
        for row in rows
        if str(row.get("weather_code") or "").strip()
    ]
    if not values:
        return None
    # A condição mais frequente do dia representa melhor o período observado.
    return Counter(values).most_common(1)[0][0]


def _summarize_weather(
    rows: list[dict[str, Any]],
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    timezone_name: str | None = None,
    allow_live_fetch: bool = True,
) -> dict[str, Any]:
    """Resume o clima gravado nas visitas e, se vazio, consulta a Open-Meteo."""
    temperatures = [
        value
        for row in rows
        if (value := _safe_float(row.get("temperature"))) is not None
    ]
    humidities = [
        value
        for row in rows
        if (value := _safe_float(row.get("humidity"))) is not None
    ]
    winds = [
        value
        for row in rows
        if (value := _safe_float(row.get("wind_speed"))) is not None
    ]
    condition = _condition_from_rows(rows)
    source = "Registros da visita (Open-Meteo)" if (temperatures or humidities) else ""

    # Sem clima registrado (visitas antigas ou app recém-instalado), usa o clima
    # atual do jardim. A chamada tem cache e nunca levanta exceção.
    if not temperatures and not humidities and allow_live_fetch:
        if latitude is not None and longitude is not None:
            try:
                from app.services.camera_weather import (
                    get_camera_weather_service,
                )

                snapshot = get_camera_weather_service().current_for(
                    latitude, longitude, timezone_name=timezone_name
                )
                if snapshot is not None and snapshot.available:
                    temperatures = (
                        [snapshot.temperature]
                        if snapshot.temperature is not None
                        else []
                    )
                    humidities = (
                        [snapshot.humidity] if snapshot.humidity is not None else []
                    )
                    winds = (
                        [snapshot.wind_speed] if snapshot.wind_speed is not None else []
                    )
                    condition = snapshot.condition
                    source = "Open-Meteo (clima atual)"
            except Exception:
                logger.debug("Clima do diário indisponível", exc_info=True)

    temperature = round(sum(temperatures) / len(temperatures), 1) if temperatures else None
    humidity = round(sum(humidities) / len(humidities), 0) if humidities else None
    wind_speed = round(sum(winds) / len(winds), 1) if winds else None
    available = temperature is not None or humidity is not None or bool(condition)
    parts: list[str] = []
    if temperature is not None:
        parts.append(f"{temperature:.1f} °C")
    if humidity is not None:
        parts.append(f"{humidity:.0f}% UR")
    if condition:
        parts.append(condition)
    if wind_speed is not None:
        parts.append(f"vento {wind_speed:.1f} km/h")
    return {
        "available": available,
        "temperature": temperature,
        "humidity": humidity,
        "condition": condition,
        "icon": _weather_icon(condition) if condition else "🌤️",
        "wind_speed": wind_speed,
        "source": source,
        "summary": " · ".join(parts) if parts else "Clima não registrado",
    }


def _camera_coordinates(
    row: dict[str, Any], settings: Any
) -> tuple[float | None, float | None]:
    latitude = _safe_float(row.get("camera_latitude"))
    longitude = _safe_float(row.get("camera_longitude"))
    if latitude is None:
        latitude = _safe_float(settings.latitude)
    if longitude is None:
        longitude = _safe_float(settings.longitude)
    return latitude, longitude


def _garden_name(row: dict[str, Any]) -> str:
    return (
        str(row.get("camera_location") or "").strip()
        or str(row.get("camera_name") or "").strip()
        or "Jardim Bem-Te-Vi Monitor"
    )


def _species_media(sightings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sighting in sightings:
        for kind, url, label in (
            ("photo", sighting.get("crop_url"), "Foto tratada"),
            ("clip", sighting.get("clip_url"), "Clipe de vídeo"),
            ("photo", sighting.get("thumbnail_url"), "Captura original"),
        ):
            if not url or url in seen:
                continue
            seen.add(url)
            media.append(
                {
                    "kind": kind,
                    "url": url,
                    "label": label,
                    "visit_id": sighting.get("visit_id"),
                }
            )
            if len(media) >= 9:
                return media
    return media


def _journal_text(
    *,
    day: str,
    gardens: list[dict[str, Any]],
    species: list[dict[str, Any]],
    weather: dict[str, Any],
    total_visits: int,
) -> str:
    lines: list[str] = [
        "DIÁRIO DE CAMPO BEM-TE-VI MONITOR",
        _long_date(day).upper(),
        "",
    ]
    if gardens:
        names = ", ".join(garden["name"] for garden in gardens)
        lines.append(f"Jardim: {names}")
        first = gardens[0]
        if first.get("coordinates_label"):
            lines.append(f"Coordenadas: {first['coordinates_label']}")
    lines.append(f"Clima: {weather.get('summary') or 'não registrado'}")
    lines.append("")

    if not species:
        lines.append("Nenhuma ave registrada neste dia.")
        return "\n".join(lines)

    lines.append(f"{total_visits} visita(s) · {len(species)} espécie(s) observada(s)")
    lines.append("")
    for item in species:
        lines.append(
            f"{item['first_time_label']} — {item['species']}"
            + (f" ({item['scientific_name']})" if item.get("scientific_name") else "")
        )
        details = [
            f"{item['count']} indivíduo(s)",
            f"confiança máx. {round(item['max_confidence'] * 100)}%",
        ]
        if item.get("ecological_label"):
            details.append(item["ecological_label"])
        if item.get("behavior_summary"):
            details.append(item["behavior_summary"])
        lines.append("    " + " · ".join(details))
        if item["first_time_label"] != item["last_time_label"]:
            lines.append(
                f"    Avistada entre {item['first_time_label']} e "
                f"{item['last_time_label']}."
            )
        if item.get("media"):
            lines.append(f"    Mídia: {item['media'][0]['url']}")
        lines.append("")
    lines.append("Registro gerado automaticamente pelo Bem-Te-Vi Core.")
    return "\n".join(lines).strip()


class FieldJournalService:
    """Compila o diário de campo e as exportações de um dia de observação."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.settings = get_settings()
        self.db_path = db_path or self.settings.db_path

    # ------------------------------------------------------------------
    # Consulta e montagem
    # ------------------------------------------------------------------
    def _rows(self, day: str, camera_id: str | None) -> list[dict[str, Any]]:
        clauses = [
            "COALESCE(NULLIF(v.visitor_kind, ''), 'bird') = 'bird'",
            "COALESCE(NULLIF(v.local_date, ''), substr(v.detected_at, 1, 10)) = ?",
        ]
        params: list[Any] = [day]
        if camera_id:
            clauses.append("v.camera_id = ?")
            params.append(camera_id)
        sql = f"""
            SELECT
                v.id, v.camera_id, v.species, v.species_id, v.confidence,
                v.detected_at, v.local_hour, v.local_date, v.location_label,
                v.thumbnail_path, v.clip_path, v.metadata_json,
                v.temperature, v.humidity, v.weather_code, v.wind_speed,
                v.dwell_seconds,
                c.name AS camera_name,
                c.location_label AS camera_location,
                c.latitude AS camera_latitude,
                c.longitude AS camera_longitude,
                c.timezone AS camera_timezone,
                c.country AS camera_country,
                COALESCE(bs.common_name, v.species) AS species_common_name,
                bs.scientific_name AS species_scientific_name,
                bs.ecological_status AS ecological_status
            FROM visits v
            JOIN cameras c ON c.id = v.camera_id
            LEFT JOIN bird_species bs ON bs.id = v.species_id
            WHERE {' AND '.join(clauses)}
            ORDER BY v.detected_at ASC
        """
        with db_session(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def _sighting(self, row: dict[str, Any]) -> dict[str, Any]:
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
        except (TypeError, ValueError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        visit_id = str(row["id"])
        return {
            "visit_id": visit_id,
            "camera_id": str(row["camera_id"]),
            "detected_at": str(row["detected_at"]),
            "time_label": _time_label(
                row.get("detected_at"), row.get("camera_timezone")
            ),
            "confidence": round(_safe_float(row.get("confidence")) or 0.0, 4),
            "garden_name": _garden_name(row),
            "camera_name": str(row.get("camera_name") or ""),
            "temperature": _safe_float(row.get("temperature")),
            "humidity": _safe_float(row.get("humidity")),
            "weather_code": row.get("weather_code"),
            "wind_speed": _safe_float(row.get("wind_speed")),
            "behavior": metadata.get("behavior_label")
            or metadata.get("behavior")
            or None,
            "individuals_peak": _safe_int(metadata.get("individuals_peak")) or 1,
            "crop_url": _crop_url(visit_id, metadata, self.settings.crops_dir),
            "thumbnail_url": _media_url(row.get("thumbnail_path")),
            "clip_url": _clip_url(row.get("clip_path")),
        }

    def resolve_day(self, day: str | None = None) -> str:
        """Valida e normaliza a data do diário (pública para os controllers)."""
        return _parse_day(day)

    def build(self, day: str | None = None, camera_id: str | None = None) -> dict[str, Any]:
        """Monta o diário completo (JSON serializável) do dia solicitado."""
        target_day = _parse_day(day)
        rows = self._rows(target_day, camera_id)
        sightings = [self._sighting(row) for row in rows]

        # --- Jardins e coordenadas -------------------------------------
        gardens: dict[str, dict[str, Any]] = {}
        for row in rows:
            camera_key = str(row["camera_id"])
            if camera_key in gardens:
                continue
            latitude, longitude = _camera_coordinates(row, self.settings)
            garden_weather = _summarize_weather(
                [item for item in rows if str(item["camera_id"]) == camera_key],
                latitude=latitude,
                longitude=longitude,
                timezone_name=row.get("camera_timezone"),
                allow_live_fetch=True,
            )
            gardens[camera_key] = {
                "camera_id": camera_key,
                "name": _garden_name(row),
                "location_label": row.get("camera_location"),
                "latitude": latitude,
                "longitude": longitude,
                "timezone": row.get("camera_timezone"),
                "country": row.get("camera_country"),
                "coordinates_label": (
                    f"{latitude:.5f}, {longitude:.5f}"
                    if latitude is not None and longitude is not None
                    else None
                ),
                "weather": garden_weather,
            }

        weather = _summarize_weather(
            rows,
            latitude=next(iter(gardens.values()))["latitude"] if gardens else None,
            longitude=next(iter(gardens.values()))["longitude"] if gardens else None,
            timezone_name=(
                next(iter(gardens.values()))["timezone"] if gardens else None
            ),
            allow_live_fetch=not bool(rows),
        )
        if not weather.get("available") and gardens:
            # Visitas antigas podem não ter clima gravado; aproveita o resumo
            # (já consultado ao vivo) do primeiro jardim do dia.
            weather = next(iter(gardens.values()))["weather"]

        # --- Agrupamento por espécie -----------------------------------
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for sighting, row in zip(sightings, rows):
            common = str(row.get("species_common_name") or row.get("species") or "Ave")
            scientific = str(row.get("species_scientific_name") or "").strip() or None
            key = (common.casefold().strip(), (scientific or "").casefold())
            item = grouped.get(key)
            if item is None:
                item = {
                    "species": common,
                    "scientific_name": scientific,
                    "ecological_status": row.get("ecological_status"),
                    "ecological_label": _ecological_label(row.get("ecological_status")),
                    "count": 1,
                    "visits": 0,
                    "max_confidence": 0.0,
                    "first_seen_at": sighting["detected_at"],
                    "last_seen_at": sighting["detected_at"],
                    "first_time_label": sighting["time_label"],
                    "last_time_label": sighting["time_label"],
                    "behavior_summary": sighting.get("behavior"),
                    "sightings": [],
                }
                grouped[key] = item
            item["visits"] += 1
            item["count"] = max(item["count"], sighting["individuals_peak"])
            item["max_confidence"] = max(
                item["max_confidence"], sighting["confidence"]
            )
            item["last_seen_at"] = sighting["detected_at"]
            item["last_time_label"] = sighting["time_label"]
            if sighting.get("behavior") and not item.get("behavior_summary"):
                item["behavior_summary"] = sighting["behavior"]
            item["sightings"].append(sighting)

        species_list: list[dict[str, Any]] = []
        for item in grouped.values():
            item["sightings"].sort(key=lambda value: value["detected_at"])
            item["media"] = _species_media(item["sightings"])
            item["count"] = max(1, item["count"])
            species_list.append(item)
        species_list.sort(
            key=lambda value: (
                value["first_seen_at"],
                value["species"].casefold(),
            )
        )

        total_visits = len(rows)
        journal_text = _journal_text(
            day=target_day,
            gardens=list(gardens.values()),
            species=species_list,
            weather=weather,
            total_visits=total_visits,
        )
        first_seen = min((row["detected_at"] for row in rows), default=None)
        last_seen = max((row["detected_at"] for row in rows), default=None)
        primary_timezone = (
            next(iter(gardens.values()))["timezone"] if gardens else None
        )

        return {
            "date": target_day,
            "generated_at": _now_iso(),
            "title": f"Diário de Campo · {_long_date(target_day)}",
            "subtitle": (
                f"{total_visits} visita(s) · {len(species_list)} espécie(s)"
                if total_visits
                else "Nenhuma ave registrada neste dia"
            ),
            "journal_text": journal_text,
            "weather": weather,
            "summary": {
                "total_visits": total_visits,
                "total_species": len(species_list),
                "total_gardens": len(gardens),
                "first_observation_at": first_seen,
                "last_observation_at": last_seen,
                "first_time_label": _time_label(first_seen, primary_timezone),
                "last_time_label": _time_label(last_seen, primary_timezone),
                "latitude": (
                    next(iter(gardens.values()))["latitude"] if gardens else None
                ),
                "longitude": (
                    next(iter(gardens.values()))["longitude"] if gardens else None
                ),
            },
            "gardens": list(gardens.values()),
            "species": species_list,
        }

    # ------------------------------------------------------------------
    # Exportações
    # ------------------------------------------------------------------
    def export_ebird(
        self, day: str | None = None, camera_id: str | None = None
    ) -> str:
        """Checklist no **eBird Record Format** (CSV UTF-8, sem cabeçalho).

        Uma linha por espécie/jardim. O eBird agrupa as linhas em checklists por
        data, local, horário e esforço. Datas vão em ``mês/dia/ano``; o arquivo
        não tem linha de cabeçalho, aspas, quebras de linha ou vírgulas dentro
        dos campos — exatamente como o importador do Cornell Lab exige.
        """
        report = self.build(day, camera_id)
        day_iso = report["date"]
        gardens = {garden["camera_id"]: garden for garden in report["gardens"]}
        checklist_weather = report["weather"].get("summary") or "não registrado"
        rows: list[list[str]] = []

        # Esforço único por jardim/dia: todas as espécies do mesmo jardim devem
        # compartilhar o mesmo horário de início e a mesma duração para o eBird
        # agrupá-las em **um** checklist, e não em vários.
        all_sightings_by_garden: dict[str, list[dict[str, Any]]] = {}
        for item in report["species"]:
            for sighting in item["sightings"]:
                all_sightings_by_garden.setdefault(
                    sighting["camera_id"], []
                ).append(sighting)

        checklist_effort: dict[str, tuple[str, str]] = {}
        for garden_id, garden_sightings in all_sightings_by_garden.items():
            garden = gardens.get(garden_id, {})
            first = min(value["detected_at"] for value in garden_sightings)
            last = max(value["detected_at"] for value in garden_sightings)
            start_time = _first_time_label(
                garden_sightings, garden.get("timezone")
            )
            if start_time == "--:--":
                start_time = ""
            checklist_effort[garden_id] = (
                start_time,
                str(_duration_minutes(first, last)),
            )

        for item in report["species"]:
            if str(item.get("species") or "").strip().casefold() in _GENERIC_SPECIES:
                continue
            by_garden: dict[str, list[dict[str, Any]]] = {}
            for sighting in item["sightings"]:
                by_garden.setdefault(sighting["camera_id"], []).append(sighting)

            for garden_id, garden_sightings in by_garden.items():
                garden = gardens.get(garden_id, {})
                lat = garden.get("latitude")
                lon = garden.get("longitude")
                count = max(
                    [value.get("individuals_peak") or 1 for value in garden_sightings]
                    or [1]
                )
                confidence = max(
                    (
                        float(value.get("confidence") or 0)
                        for value in garden_sightings
                    ),
                    default=0.0,
                )
                cameras = sorted(
                    {
                        str(value.get("camera_name"))
                        for value in garden_sightings
                        if value.get("camera_name")
                    }
                )

                comments = ["Detecção automática Bem-Te-Vi Core"]
                if cameras:
                    comments.append(f"Câmera: {'; '.join(cameras)}")
                if confidence > 0:
                    comments.append(f"Confiança máx.: {confidence:.0%}")
                if item.get("behavior_summary"):
                    comments.append(str(item["behavior_summary"]))
                if item.get("ecological_label"):
                    comments.append(str(item["ecological_label"]))

                state, country = _ebird_region(garden.get("country"))
                genus, species = _scientific_parts(item.get("scientific_name"))
                start_time, duration = checklist_effort.get(
                    garden_id, ("", "1")
                )

                submission_comments = (
                    f"Bem-Te-Vi Core · Clima: {checklist_weather} · "
                    "Checklist automático; as observações podem não representar "
                    "todos os indivíduos presentes no jardim."
                )
                row = [
                    item["species"],
                    genus,
                    species,
                    str(count),
                    " · ".join(comments),
                    garden.get("name") or "Jardim Bem-Te-Vi Monitor",
                    f"{lat:.6f}" if lat is not None else "",
                    f"{lon:.6f}" if lon is not None else "",
                    _ebird_date(day_iso),
                    start_time,
                    state,
                    country,
                    "Stationary",
                    "1",
                    duration,
                    "N",
                    "",
                    "",
                    submission_comments,
                ]
                rows.append([_ebird_text(value) for value in row])

        # Ordem estável e legível ao abrir no editor: local, horário e espécie.
        rows.sort(key=lambda row: (row[5].casefold(), row[9], row[0].casefold()))

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        # O eBird Record Format exige que a primeira linha seja uma observação,
        # nunca o cabeçalho. Por isso não escrevemos ``_EBIRD_COLUMNS``.
        writer.writerows(rows)
        return output.getvalue()

    def export_csv(
        self, day: str | None = None, camera_id: str | None = None
    ) -> str:
        """Planilha limpa em pt-BR, uma linha por espécie e jardim."""
        report = self.build(day, camera_id)
        gardens = {garden["camera_id"]: garden for garden in report["gardens"]}
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(_CLEAN_COLUMNS)

        for item in report["species"]:
            by_garden: dict[str, list[dict[str, Any]]] = {}
            for sighting in item["sightings"]:
                by_garden.setdefault(sighting["camera_id"], []).append(sighting)

            for garden_id, garden_sightings in by_garden.items():
                garden = gardens.get(garden_id, {})
                garden_weather = garden.get("weather") or {}
                first = min(value["detected_at"] for value in garden_sightings)
                last = max(value["detected_at"] for value in garden_sightings)
                count = max(
                    [value.get("individuals_peak") or 1 for value in garden_sightings]
                    or [1]
                )
                notes = "Registro automático Bem-Te-Vi Core"
                if item.get("behavior_summary"):
                    notes = f"{notes} · {item['behavior_summary']}"
                writer.writerow(
                    [
                        report["date"],
                        _first_time_label(garden_sightings, garden.get("timezone")),
                        garden.get("name") or "",
                        garden_sightings[0].get("camera_name") or "",
                        item["species"],
                        item.get("scientific_name") or "",
                        item.get("ecological_label") or "",
                        count,
                        f"{item['max_confidence']:.3f}",
                        first,
                        last,
                        (
                            f"{garden.get('latitude'):.6f}"
                            if garden.get("latitude") is not None
                            else ""
                        ),
                        (
                            f"{garden.get('longitude'):.6f}"
                            if garden.get("longitude") is not None
                            else ""
                        ),
                        (
                            f"{garden_weather.get('temperature'):.1f}"
                            if garden_weather.get("temperature") is not None
                            else ""
                        ),
                        (
                            f"{garden_weather.get('humidity'):.0f}"
                            if garden_weather.get("humidity") is not None
                            else ""
                        ),
                        garden_weather.get("condition") or "",
                        notes,
                    ]
                )
        return output.getvalue()


def get_field_journal_service() -> FieldJournalService:
    """Instância leve (sem cache) usada pelas rotas do diário."""
    return FieldJournalService()
