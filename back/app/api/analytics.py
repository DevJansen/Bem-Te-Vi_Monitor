"""Habit analytics and bird life-list routes."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.domain.models import (
    AchievementOut,
    CameraWeatherOut,
    CollectorLevelOut,
    AnalyticsSummaryOut,
    FeedingWeatherGardenOut,
    FeedingWeatherInsightsOut,
    GardenRadarGardenOut,
    GardenRadarOut,
    GardenRadarSpeciesOut,
    HourlyDistributionOut,
    LifeListSpeciesOut,
    TimelapseGenerateRequest,
    TimelapseGenerateResult,
    TimelapseOut,
    TodayByGardenOut,
    WeatherCorrelationOut,
    WeatherInsightsOut,
)
from app.infra.camera.manager import get_camera_manager
from app.infra.database.analytics_repository import AnalyticsRepository
from app.infra.database.repository import CameraRepository
from app.services.camera_weather import get_camera_weather_service
from app.services.timelapse_service import get_timelapse_service
from app.services.weather_forecast import get_weather_forecast_service
from app.services.weather_insights import build_feeding_insight, build_weather_insights

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _repository() -> AnalyticsRepository:
    return AnalyticsRepository(get_settings().db_path)


@router.get("/summary", response_model=AnalyticsSummaryOut)
def get_analytics_summary(
    camera_id: str | None = Query(
        default=None,
        description="Restringe o resumo a um jardim (câmera). Omitido = consolidado.",
    ),
) -> AnalyticsSummaryOut:
    try:
        return AnalyticsSummaryOut(
            **_repository().summary(camera_id=camera_id)
        )
    except Exception as exc:
        logger.exception("get_analytics_summary failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular as estatísticas.",
        ) from exc


@router.get("/today", response_model=TodayByGardenOut)
def get_analytics_today() -> TodayByGardenOut:
    """Visitas de hoje consolidadas e segmentadas por jardim (câmera)."""
    try:
        return TodayByGardenOut(**_repository().today_by_garden())
    except Exception as exc:
        logger.exception("get_analytics_today failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular as visitas de hoje por jardim.",
        ) from exc


@router.get(
    "/hourly-distribution",
    response_model=list[HourlyDistributionOut],
)
def get_hourly_distribution(
    camera_id: str | None = Query(
        default=None,
        description="Restringe a distribuição a um jardim (câmera). Omitido = consolidado.",
    ),
) -> list[HourlyDistributionOut]:
    try:
        return [
            HourlyDistributionOut(**row)
            for row in _repository().hourly_distribution(camera_id=camera_id)
        ]
    except Exception as exc:
        logger.exception("get_hourly_distribution failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar a distribuição por horário.",
        ) from exc


@router.get("/lifelist", response_model=list[LifeListSpeciesOut])
def get_lifelist() -> list[LifeListSpeciesOut]:
    try:
        return [
            LifeListSpeciesOut(**row)
            for row in _repository().lifelist()
        ]
    except Exception as exc:
        logger.exception("get_lifelist failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar o álbum de espécies.",
        ) from exc


@router.get("/collector-level", response_model=CollectorLevelOut)
def get_collector_level() -> CollectorLevelOut:
    """Nível do Coletor baseado na quantidade de espécies descobertas."""
    try:
        return CollectorLevelOut(**_repository().collector_level())
    except Exception as exc:
        logger.exception("get_collector_level failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular o nível do coletor.",
        ) from exc


@router.get("/report/pdf")
def get_report_pdf():
    """Gera e baixa o Laudo Ornitológico automatizado em PDF."""
    from fastapi.responses import Response

    from app.services.ornithological_report import gerar_laudo_pdf

    try:
        pdf_bytes = gerar_laudo_pdf(get_settings().db_path)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    "attachment; filename=laudo-ornitologico-bem-te-vi.pdf"
                )
            },
        )
    except Exception as exc:
        logger.exception("get_report_pdf failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível gerar o laudo ornitológico.",
        ) from exc


@router.get("/achievements", response_model=list[AchievementOut])
def get_achievements() -> list[AchievementOut]:
    """Medalhas/marcos conquistados pelo observador."""
    try:
        return [
            AchievementOut(**row) for row in _repository().achievements()
        ]
    except Exception as exc:
        logger.exception("get_achievements failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar as conquistas.",
        ) from exc


@router.get("/weather-correlation", response_model=WeatherCorrelationOut)
def get_weather_correlation() -> WeatherCorrelationOut:
    """Cruza a frequência de visitas com as condições do tempo."""
    try:
        return WeatherCorrelationOut(**_repository().weather_correlation())
    except Exception as exc:
        logger.exception("get_weather_correlation failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular a correlação climática.",
        ) from exc


@router.get("/weather-insights", response_model=WeatherInsightsOut)
def get_weather_insights() -> WeatherInsightsOut:
    """Insights avançados cruzando clima e hábitos das aves.

    Combina temperatura, umidade e condição do tempo com o horário e a espécie
    de cada visita para produzir faixas de temperatura, chuva x tempo seco,
    horário médio no frio x no calor e cards de resumo inteligente.
    """
    repository = _repository()
    try:
        rows = repository.weather_visit_rows()
        total = repository.total_visits()
        return WeatherInsightsOut(
            **build_weather_insights(rows, total_visits=total)
        )
    except Exception as exc:
        logger.exception("get_weather_insights failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível calcular os insights de clima.",
        ) from exc


@router.get("/timelapses", response_model=list[TimelapseOut])
def list_timelapses() -> list[TimelapseOut]:
    """Resumos do dia (time-lapses) já gerados, do mais recente ao mais antigo."""
    try:
        return [
            TimelapseOut(**item) for item in get_timelapse_service().list()
        ]
    except Exception as exc:
        logger.exception("list_timelapses failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível listar os resumos do dia.",
        ) from exc


@router.post("/timelapses/generate", response_model=TimelapseGenerateResult)
def generate_timelapse(
    payload: TimelapseGenerateRequest,
) -> TimelapseGenerateResult:
    """Gera (sob demanda) o resumo de um dia a partir dos clipes gravados.

    Quando ``day`` não é informado, usa o dia atual. O campo ``force`` permite
    regerar um resumo que já existe.
    """
    if payload.day:
        try:
            day: date | None = date.fromisoformat(payload.day)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail="Data inválida. Use o formato AAAA-MM-DD.",
            ) from exc
    else:
        day = None

    try:
        result = get_timelapse_service().generate(day, force=payload.force)
    except Exception as exc:
        logger.exception("generate_timelapse failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível gerar o resumo do dia.",
        ) from exc

    timelapse = result.get("timelapse")
    return TimelapseGenerateResult(
        status=result["status"],
        message=result["message"],
        timelapse=TimelapseOut(**timelapse) if timelapse else None,
    )


@router.delete("/timelapses/{filename}")
def delete_timelapse(filename: str) -> dict[str, bool]:
    """Remove um resumo do dia pelo nome do arquivo."""
    try:
        removed = get_timelapse_service().delete(filename)
    except Exception as exc:
        logger.exception("delete_timelapse failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível remover o resumo do dia.",
        ) from exc
    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Resumo do dia não encontrado.",
        )
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Radar Global + Insights preditivos de alimentação
# --------------------------------------------------------------------------- #
def _camera_weather_out(row: dict, snapshot) -> CameraWeatherOut:
    """Converte o instantâneo da Open-Meteo no DTO do radar/insights."""
    latitude = float(row["latitude"])
    longitude = float(row["longitude"])
    if snapshot is None:
        return CameraWeatherOut(
            available=False,
            latitude=latitude,
            longitude=longitude,
            timezone=row.get("timezone"),
        )
    return CameraWeatherOut(
        available=snapshot.available,
        latitude=latitude,
        longitude=longitude,
        timezone=snapshot.timezone or row.get("timezone"),
        utc_offset_seconds=snapshot.utc_offset_seconds,
        local_time=snapshot.local_time,
        local_time_label=snapshot.local_time_label,
        temperature=snapshot.temperature,
        humidity=snapshot.humidity,
        wind_speed=snapshot.wind_speed,
        condition=snapshot.condition,
        category=snapshot.category,
        icon=snapshot.icon,
        weather_code=snapshot.code,
        is_day=snapshot.is_day,
        fetched_at=snapshot.fetched_at,
        source=snapshot.source,
    )


def _safe_camera_weather(row: dict):
    try:
        return get_camera_weather_service().current_for(
            float(row["latitude"]),
            float(row["longitude"]),
            timezone_name=row.get("timezone"),
        )
    except Exception:
        logger.exception("Falha ao buscar o clima do jardim %s", row.get("id"))
        return None


@router.get("/garden-radar", response_model=GardenRadarOut)
def get_garden_radar() -> GardenRadarOut:
    """Jardins geolocalizados para o Radar Global Interativo.

    Cada jardim traz o clima/horário locais, o resumo de hoje, as espécies mais
    frequentes e as URLs do vídeo/áudio ao vivo. As consultas de clima são
    feitas em paralelo com um orçamento curto: se a internet estiver lenta, o
    jardim aparece mesmo assim (com ``available=False``) e o clima é preenchido
    no próximo ciclo do painel.
    """
    try:
        data = _repository().garden_radar()
    except Exception as exc:
        logger.exception("get_garden_radar failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível montar o Radar Global de jardins.",
        ) from exc

    rows = data["gardens"]
    snapshots: dict[str, object] = {}
    if rows:
        pool = ThreadPoolExecutor(max_workers=4)
        futures = {
            pool.submit(_safe_camera_weather, row): row["id"] for row in rows
        }
        try:
            for future in as_completed(futures, timeout=7.0):
                snapshots[futures[future]] = future.result()
        except TimeoutError:
            logger.info("Radar Global: orçamento de clima esgotado, seguindo sem ele")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    manager = get_camera_manager()
    gardens: list[GardenRadarGardenOut] = []
    for row in rows:
        try:
            status = manager.get_status(row["id"])
        except Exception:
            status = "idle"
        garden = row.get("location_label") or row.get("name") or "Jardim sem nome"
        gardens.append(
            GardenRadarGardenOut(
                camera_id=row["id"],
                name=row["name"],
                garden=garden,
                country=row.get("country"),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                timezone=row.get("timezone"),
                is_active=bool(row.get("is_active")),
                ai_enabled=bool(row.get("ai_enabled", 1)),
                audio_enabled=bool(row.get("audio_enabled", 0)),
                status=str(status),
                weather=_camera_weather_out(row, snapshots.get(row["id"])),
                visits_today=int(row.get("visits_today") or 0),
                species_today=int(row.get("species_today") or 0),
                total_visits=int(row.get("total_visits") or 0),
                last_visit_at=row.get("last_visit_at"),
                top_species=[
                    GardenRadarSpeciesOut(**item)
                    for item in (row.get("top_species") or [])
                ],
                stream_url=f"/api/video-feed/{row['id']}?boxes=true",
                audio_url=(
                    f"/api/bioacoustics/audio/{row['id']}"
                    if row.get("audio_enabled")
                    else None
                ),
            )
        )

    return GardenRadarOut(
        gardens=gardens,
        without_location=int(data.get("without_location") or 0),
    )


@router.get(
    "/weather-feeding-insights", response_model=FeedingWeatherInsightsOut
)
def get_feeding_weather_insights(
    camera_id: str | None = Query(
        default=None,
        description="Restringe o card preditivo a um jardim (câmera).",
    ),
) -> FeedingWeatherInsightsOut:
    """Previsão de chuva × comportamento histórico de alimentação.

    Para cada jardim geolocalizado, o Alaris Core busca as próximas 12 horas na
    Open-Meteo e compara com o histórico **daquele** jardim (visitas/dia em dias
    de chuva versus dias secos). Sem nenhuma câmera geolocalizada, usa a
    localização global do alimentador (`LATITUDE`/`LONGITUDE`) como "Jardim
    Principal". O resultado alimenta o card "Insights Meteorológicos" do Painel,
    com uma frase pronta em pt-BR.
    """
    settings = get_settings()
    repository = _repository()
    forecast_service = get_weather_forecast_service()

    cameras = CameraRepository(settings.db_path).list_all()
    if camera_id:
        cameras = [camera for camera in cameras if camera["id"] == camera_id]

    located = [
        camera
        for camera in cameras
        if camera.get("latitude") is not None and camera.get("longitude") is not None
    ][:24]

    # Nenhuma câmera geolocalizada: usa a localização global do alimentador
    # (LATITUDE/LONGITUDE) como "Jardim Principal". Assim o card preditivo
    # funciona já na instalação padrão, sem exigir coordenadas por câmera.
    if not located:
        base = cameras[0] if cameras else None
        located = [
            {
                "id": base["id"] if base else "local",
                "name": base["name"] if base else "Jardim Principal",
                "location_label": base["location_label"] if base else None,
                "country": base["country"] if base else None,
                "timezone": base["timezone"] if base else None,
                "latitude": settings.latitude,
                "longitude": settings.longitude,
            }
        ]

    cameras = located

    def _history_for(camera: dict) -> list[dict]:
        # O jardim sintético ("local") agrega o histórico de todas as câmeras.
        return repository.weather_visit_rows(
            camera_id=None if camera["id"] == "local" else camera["id"]
        )

    def _load(camera: dict):
        forecast = forecast_service.next_hours(
            float(camera["latitude"]),
            float(camera["longitude"]),
            timezone_name=camera.get("timezone"),
            hours=12,
        )
        return forecast, _history_for(camera)

    loaded: dict[str, tuple[object | None, list[dict]]] = {}
    if cameras:
        pool = ThreadPoolExecutor(max_workers=4)
        futures = {pool.submit(_load, camera): camera["id"] for camera in cameras}
        try:
            for future in as_completed(futures, timeout=9.0):
                loaded[futures[future]] = future.result()
        except TimeoutError:
            logger.info(
                "Insights de alimentação: orçamento da previsão esgotado"
            )
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    gardens: list[FeedingWeatherGardenOut] = []
    for camera in cameras:
        forecast, history = loaded.get(camera["id"], (None, None))
        if history is None:
            try:
                history = _history_for(camera)
            except Exception:
                logger.exception(
                    "Falha ao carregar o histórico do jardim %s", camera["id"]
                )
                history = []
        garden = (
            camera.get("location_label")
            or camera.get("name")
            or "Jardim sem nome"
        )
        current = (
            forecast.current_payload
            if forecast is not None and getattr(forecast, "available", False)
            else None
        )
        insight = build_feeding_insight(
            camera_id=camera["id"],
            garden=garden,
            country=camera.get("country"),
            latitude=float(camera["latitude"]),
            longitude=float(camera["longitude"]),
            timezone_name=camera.get("timezone"),
            history_rows=history,
            forecast=forecast,
            current=current,
        )
        gardens.append(FeedingWeatherGardenOut(**insight))

    # Chuva iminente primeiro; depois os jardins com mais histórico.
    gardens.sort(
        key=lambda item: (
            0 if (item.forecast and item.forecast.rain_expected) else 1,
            item.forecast.rain_in_hours
            if (item.forecast and item.forecast.rain_in_hours is not None)
            else 99,
            -item.history.visits,
        )
    )
    highlight = next(
        (
            garden
            for garden in gardens
            if garden.forecast and garden.forecast.rain_expected
        ),
        gardens[0] if gardens else None,
    )
    return FeedingWeatherInsightsOut(gardens=gardens, highlight=highlight)
