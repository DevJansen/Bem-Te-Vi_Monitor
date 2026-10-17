"""Per-camera vision pipeline: capture → detect → zone → clip → notify."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import cv2
import numpy as np

from app.core.config import get_settings
from app.domain.avifauna_sul import descrever, info_especie
from app.domain.models import RoiType, RoiZone, VisitOut, ZoneConfig, ZoneMode
from app.infra.ai.annotate import (
    apply_banner,
    build_clip_banner,
    draw_bird_detections,
)
from app.infra.ai.band_counting import ContadorIndividuos
from app.infra.ai.behavior import (
    Comportamento,
    classificar_comportamento,
    energia_movimento,
)
from app.infra.ai.best_frame import MelhorQuadro, SeletorMelhorQuadro
from app.infra.ai.box_tracker import BoxTracker
from app.infra.ai.detector import (
    BirdDetector,
    Detection,
    get_bird_detector,
    translate_class_name,
)
from app.infra.ai.enhancement import realcar_quadro_da_ave
from app.infra.ai.motion import MotionDetector
from app.infra.ai.night_vision import NightVisionProcessor
from app.infra.ai.pre_record_buffer import PreRecordBuffer
from app.infra.ai.species_classifier import SpeciesClassifier, get_default_species_classifier
from app.infra.ai.zone_validator import ZoneValidator, point_in_polygon
from app.infra.camera.manager import get_camera_manager
from app.infra.camera.streamer import CameraStreamer, StreamStatus
from app.infra.streams.registry import get_stream_registry
from app.infra.database.repository import CameraRepository, SettingsRepository, VisitRepository
from app.infra.media.storage import (
    relative_to_captures,
    save_bird_crop,
    save_clip_mp4,
    save_thumbnail,
)
from app.services.ai_cognitive_log import (
    NIVEL_ALERTA,
    NIVEL_ANALISE,
    NIVEL_ATENCAO,
    NIVEL_INFO,
    NIVEL_SUCESSO,
    registrar_pensamento,
)
from app.services.ai_telemetry import (
    ESTADO_ANALISANDO,
    get_ai_telemetry,
)
from app.services.anomaly_log import registrar_retorno_especie
from app.services.calibration import get_calibration_service
from app.services.ornithological_annotation import montar_analise_ia
from app.services.system_context import ajustar_sensibilidade

logger = logging.getLogger(__name__)

VisitHandler = Callable[[VisitOut], None]

# Número máximo de ciclos de inferência que podem ser pulados por ausência de
# movimento. Funciona como rede de segurança: garante uma inferência periódica
# mesmo em cenas aparentemente paradas (ex.: ave que aparece lentamente).
IDLE_INFER_MAX_SKIPS = 8


class CameraPipeline(threading.Thread):
    def __init__(
        self,
        camera_id: str,
        detector: BirdDetector | None = None,
        classifier: SpeciesClassifier | None = None,
        on_visit: VisitHandler | None = None,
    ) -> None:
        super().__init__(name=f"pipeline-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.settings = get_settings()
        self.detector = detector or get_bird_detector()
        self.classifier = classifier or get_default_species_classifier()
        self.on_visit = on_visit
        self._stop = threading.Event()
        # Sinaliza que zonas/ROI devem ser recarregadas sem reiniciar o pipeline.
        self._zones_reload = threading.Event()
        self.camera_repo = CameraRepository(self.settings.db_path)
        self.visit_repo = VisitRepository(self.settings.db_path)
        self.settings_repo = SettingsRepository(self.settings.db_path)
        self.buffer = PreRecordBuffer(seconds=self.settings.pre_record_seconds)
        # Validador de zonas com supressão anti-spam: a mesma ave permanecendo no
        # comedouro NÃO gera novos alertas/registros (mesmo evento).
        self.zone_validator = ZoneValidator(
            presence_grace_seconds=self.settings.presence_grace_seconds,
            alert_cooldown_seconds=self.settings.alert_cooldown_seconds,
        )
        # Portão de movimento inicial: evita rodar o YOLO em cenas paradas.
        self.motion = MotionDetector(sensitivity=self.settings.motion_sensitivity)
        # Visão noturna: realce de contraste para quadros escuros / infravermelho.
        self.night_vision = NightVisionProcessor(
            mode=self.settings.night_vision_mode,
            threshold=self.settings.night_vision_threshold,
            clahe_clip=self.settings.night_vision_clahe_clip,
            clahe_grid=self.settings.night_vision_clahe_grid,
            denoise=self.settings.night_vision_denoise,
        )
        # Estado do quadro atual (atualizado a cada ciclo; lido ao registrar visita).
        self._night_active = False
        self._configured_zones: list[ZoneConfig] = []
        # Zonas de interesse (ROI) retangulares: incluir (monitorar) ou excluir.
        self._roi_zones: list[RoiZone] = []
        self._post_frames_remaining = 0
        self._pending_event: dict[str, Any] | None = None
        self._post_collected: list[np.ndarray] = []
        self._last_detections: list[Detection] = []
        # Seleção do melhor quadro da janela (nitidez + confiança + enquadramento).
        self._best_selector: SeletorMelhorQuadro | None = None
        # --- Inteligência avançada (contagem, comportamento, contexto) ---
        # Contador de indivíduos/bandos da janela de evento.
        self._contador: ContadorIndividuos | None = None
        # Cache de espécie por indivíduo rastreado (para contagem multi-espécie).
        self._especies_por_track: dict[int, str] = {}
        # Comportamento mais relevante observado na janela (feeding > perching).
        self._comportamento_evento: Comportamento | None = None
        # Quadro anterior em escala de cinza (energia de movimento do comportamento).
        self._prev_gray: np.ndarray | None = None
        # CLAHE reutilizável do filtro de contraste adaptativo (lazy).
        self._clahe = None
        # Categoria de clima em cache (evita consultar a Open-Meteo a cada quadro).
        self._clima_categoria: str | None = None
        self._clima_ts = 0.0
        # Último ajuste contextual aplicado (registrado nos metadados da visita).
        self._ultimo_ajuste = None
        # Chave do último ajuste contextual registrado no log cognitivo (para só
        # anunciar mudanças de auto-calibração, evitando repetir a cada quadro).
        self._ultimo_ajuste_chave: tuple | None = None
        # Throttling do log de supressão anti-spam (mesma ave = mesmo evento).
        self._ultimo_log_supressao = 0.0
        # Contador de inferências executadas neste fluxo (Alaris Core por stream).
        self._inferencias = 0
        # Executor dedicado ao pós-processamento (clipe + foto tratada). Rodar
        # fora do laço evita travar a leitura da câmera durante o ffmpeg e o
        # denoise da imagem.
        self._finalizer = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix=f"finalize-{camera_id}"
        )
        self._finalizer_closed = False

    def stop(self) -> None:
        self._stop.set()

    def request_zones_reload(self) -> None:
        """Pede a recarga das zonas e ROI no próximo ciclo do laço."""
        self._zones_reload.set()

    def _pensar(self, mensagem: str, *, nivel: str = NIVEL_INFO, **dados: Any) -> None:
        """Registra um "pensamento" da IA no log cognitivo (se habilitado).

        Nunca levanta exceção: a telemetria é sempre *best-effort* e não pode
        afetar a captura.
        """
        if not self.settings.ai_insights_enabled:
            return
        mensagem = (
            mensagem if mensagem.startswith("[Alaris]") else f"[Alaris] {mensagem}"
        )
        registrar_pensamento(mensagem, nivel=nivel, origem=self.camera_id, **dados)

    def _load_zones(self) -> None:
        row = self.camera_repo.get(self.camera_id)
        if not row:
            self._configured_zones = []
            self.zone_validator.set_zones([])
            self._load_roi()
            return
        try:
            data = json.loads(row.get("zones_json") or '{"zones":[]}')
            zones = [ZoneConfig.model_validate(z) for z in data.get("zones", [])]
        except Exception:
            logger.exception("Invalid zones for camera %s", self.camera_id)
            zones = []
        self._configured_zones = [zone for zone in zones if zone.enabled]
        self.zone_validator.set_zones(
            [zone for zone in self._configured_zones if zone.mode == ZoneMode.INCLUDE]
        )
        self._load_roi()

    def _load_roi(self) -> None:
        """Carrega as zonas de interesse (ROI) retangulares da câmera."""
        try:
            stored = self.settings_repo.get_json(
                f"roi_zones:{self.camera_id}", {"zones": []}
            )
            raw_zones = (stored or {}).get("zones", []) if stored else []
            self._roi_zones = [RoiZone.model_validate(z) for z in raw_zones]
        except Exception:
            logger.exception("Invalid ROI for camera %s", self.camera_id)
            self._roi_zones = []

    def _apply_calibration(self, tracker: BoxTracker) -> None:
        """Lê a calibração ativa e aplica nos componentes do pipeline.

        Chamado periodicamente (não a cada quadro) para refletir ajustes feitos
        no painel sem reiniciar o backend. A leitura é em memória (rápida).
        """
        calibration = get_calibration_service().current()
        self.detector.set_confidence(calibration.yolo_confidence)
        tracker.retention_seconds = calibration.object_persistence_time
        self.motion.set_sensitivity(calibration.motion_sensitivity)
        # Visão noturna: modo e limiar de luminância aplicados sem reiniciar.
        self.night_vision.configure(
            mode=calibration.night_vision_mode,
            threshold=calibration.night_vision_threshold,
        )
        # Fauna noturna: expande (opcionalmente) as classes aceitas na inferência.
        self._apply_detection_classes(calibration.night_fauna_enabled)

    def _apply_detection_classes(self, fauna_enabled: bool) -> None:
        """Define as classes aceitas pelo YOLO (ave sempre; fauna se habilitada)."""
        class_ids = {self.detector.bird_class_id}
        if fauna_enabled:
            class_ids.update(self.settings.night_fauna_class_id_list())
        self.detector.set_class_ids(class_ids)

    def _notify_enabled(self) -> bool:
        raw = self.settings_repo.get("notifications_enabled", "true")
        return str(raw).lower() in {"1", "true", "yes", "on"}

    def _min_confidence_notify(self) -> float:
        raw = self.settings_repo.get("min_confidence_notify")
        if raw is not None:
            try:
                return float(raw)
            except ValueError:
                pass
        return self.settings.yolo_confidence

    def _limiar_minimo(self, confianca_base: float) -> float:
        """Menor limiar aplicável (base global ou o mais permissivo das ROI)."""
        limiar = float(confianca_base)
        for zona in self._roi_zones:
            if zona.type == RoiType.INCLUDE and zona.confidence is not None:
                limiar = min(limiar, float(zona.confidence))
        return limiar

    def _limiar_para_ponto(
        self, x: float, y: float, confianca_base: float
    ) -> float:
        """Limiar de confiança que se aplica a um ponto normalizado.

        Zonas de inclusão (ex.: comedouro) podem definir um limiar mais
        permissivo para aves pequenas/camufladas; fora delas vale o global.
        """
        limiar = float(confianca_base)
        for zona in self._roi_zones:
            if zona.type != RoiType.INCLUDE or zona.confidence is None:
                continue
            if zona.contains(x, y):
                limiar = min(limiar, float(zona.confidence))
        return limiar

    def _contraste_adaptativo(self, frame: np.ndarray) -> np.ndarray:
        """CLAHE no canal de luminância (revela aves camufladas).

        Aplicado **apenas** ao quadro de inferência — a imagem gravada permanece
        original. Reaproveita uma instância de CLAHE para não realocar por quadro.
        """
        if self._clahe is None:
            self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        luminancia, a, b = cv2.split(lab)
        luminancia = self._clahe.apply(luminancia)
        return cv2.cvtColor(cv2.merge((luminancia, a, b)), cv2.COLOR_LAB2BGR)

    def _detect_in_zones(
        self,
        frame: np.ndarray,
        *,
        tta: bool = False,
        contraste: bool = False,
        confianca_base: float | None = None,
    ) -> list[Detection]:
        """Mascarar áreas inválidas, realçar contraste e filtrar por limiar.

        Sensibilidade dinâmica por ROI: o YOLO roda no limiar mais permissivo
        disponível e cada detecção é validada contra o limiar da sua zona.
        """
        height, width = frame.shape[:2]
        base = (
            float(self.detector.confidence)
            if confianca_base is None
            else float(confianca_base)
        )
        inclusion_zones = [
            zone for zone in self._configured_zones if zone.mode == ZoneMode.INCLUDE
        ]
        exclusion_zones = [
            zone for zone in self._configured_zones if zone.mode == ZoneMode.EXCLUDE
        ]

        mask = np.zeros((height, width), dtype=np.uint8)
        if not inclusion_zones:
            mask.fill(255)
        else:
            for zone in inclusion_zones:
                points = np.array(
                    [
                        [
                            round(point.x * (width - 1)),
                            round(point.y * (height - 1)),
                        ]
                        for point in zone.points
                    ],
                    dtype=np.int32,
                )
                cv2.fillPoly(mask, [points], 255)

        for zone in exclusion_zones:
            points = np.array(
                [
                    [
                        round(point.x * (width - 1)),
                        round(point.y * (height - 1)),
                    ]
                    for point in zone.points
                ],
                dtype=np.int32,
            )
            cv2.fillPoly(mask, [points], 0)

        masked_frame = cv2.bitwise_and(frame, frame, mask=mask)
        # Contraste adaptativo (CLAHE): ligado pelo contexto (clima adverso) ou
        # pela configuração — que já vem LIGADA por padrão para destacar aves
        # pequenas/camufladas contra o fundo do comedouro. Aplicado só ao quadro
        # de inferência (a imagem gravada permanece original).
        usar_contraste = contraste or self.settings.roi_adaptive_contrast
        infer_frame = (
            self._contraste_adaptativo(masked_frame) if usar_contraste else masked_frame
        )
        # Roda no limiar mais permissivo; a validação fina é feita por detecção.
        detections = self.detector.detect(
            infer_frame, confidence=self._limiar_minimo(base), augment=tta
        )
        aceitas: list[Detection] = []
        for detection in detections:
            if not self._is_detection_allowed(detection, width, height):
                continue
            centro_x, centro_y = detection.normalized_center(width, height)
            if detection.confidence + 1e-9 < self._limiar_para_ponto(
                centro_x, centro_y, base
            ):
                continue
            aceitas.append(detection)
        return aceitas

    def _categoria_clima(self) -> str | None:
        """Categoria de clima atual, com cache (atualiza no máx. a cada 5 min)."""
        agora = time.time()
        if agora - self._clima_ts > 300.0:
            self._clima_ts = agora
            try:
                from app.services.system_context import clima_atual_categoria

                self._clima_categoria = clima_atual_categoria()
            except Exception:
                self._clima_categoria = None
        return self._clima_categoria

    def _anunciar_ajuste(self, ajuste: Any, confianca_base: float) -> None:
        """Anuncia a auto-calibração contextual no log cognitivo da IA.

        Só é chamado quando o ajuste efetivo muda (clima/horário), evitando
        repetir a mesma mensagem a cada ciclo de inferência.
        """
        base = round(float(confianca_base), 4)
        efetiva = round(float(ajuste.confianca_efetiva), 4)
        if not ajuste.motivos:
            self._pensar(
                f"Auto-calibração: condições normais — limiar {efetiva:.2f}.",
                nivel=NIVEL_INFO,
                confidence=efetiva,
                base=base,
            )
            return
        motivos = "; ".join(ajuste.motivos)
        self._pensar(
            f"Auto-calibração: {motivos}. Limiar {efetiva:.2f} (base {base:.2f}).",
            nivel=NIVEL_ANALISE,
            confidence=efetiva,
            base=base,
            tta=bool(ajuste.tta),
            adaptive_contrast=bool(ajuste.contraste_adaptativo),
            reasons=list(ajuste.motivos),
        )

    def _reportar_stream(
        self,
        streamer: CameraStreamer | None,
        detections: list[Detection],
        species_by_track: dict[int, str] | None = None,
    ) -> None:
        """Publica o estado do Alaris Core deste fluxo no registro de streams.

        Alimenta os selos em tempo real do grid multi-câmera (status de conexão,
        FPS, backend, aves ativas no comedouro, pico de indivíduos e as espécies
        rastreadas neste instante).
        """
        if streamer is None:
            return
        pico = 0
        if self._contador is not None:
            try:
                pico = int(self._contador.resumo().get("pico_simultaneo", 0))
            except Exception:
                pico = 0
        # Espécies distintas rastreadas agora (cards de status do painel).
        especies: list[str] = []
        if species_by_track:
            vistas = {
                species_by_track.get(det.track_id)
                for det in detections
                if det.track_id is not None
            }
            especies = sorted(nome for nome in vistas if nome)
        try:
            get_stream_registry().update(
                self.camera_id,
                name=streamer.config.name,
                status=streamer.status.value,
                fps=round(streamer.fps, 1),
                backend=self.detector.backend,
                active_birds=len(detections),
                individuals_peak=pico,
                active_species=especies,
                inferences=self._inferencias,
                last_error=streamer.last_error,
            )
        except Exception:
            logger.debug("Falha ao publicar estatísticas do stream", exc_info=True)

    def _especies_dos_tracks(
        self, frame: np.ndarray, detections: list[Detection]
    ) -> dict[int, str]:
        """Mapeia cada indivíduo rastreado à sua espécie (cache por track_id).

        Classifica uma vez por indivíduo (barato com o classificador padrão) e
        reutiliza o resultado, permitindo a contagem multi-espécie do bando.
        """
        limite = 64  # teto de segurança para não pesar em cenas com muitas aves
        for detection in detections:
            if detection.track_id is None:
                continue
            if detection.track_id in self._especies_por_track:
                continue
            if len(self._especies_por_track) >= limite:
                break
            if detection.class_id == self.detector.bird_class_id:
                try:
                    pred = self.classifier.classify(frame, detection.bbox)
                    self._especies_por_track[detection.track_id] = pred.species
                except Exception:
                    logger.exception("Falha ao classificar a espécie do indivíduo")
            else:
                self._especies_por_track[detection.track_id] = translate_class_name(
                    detection.class_name
                )
        return self._especies_por_track

    def _guardar_comportamento(self, comportamento: Comportamento) -> None:
        """Retém o comportamento mais relevante observado na janela."""
        prioridade = {"feeding": 3, "perching": 2, "moving": 1, "desconhecido": 0}
        atual = self._comportamento_evento
        if atual is None or prioridade.get(comportamento.tipo, 0) > prioridade.get(
            atual.tipo, 0
        ):
            self._comportamento_evento = comportamento

    def _observar_janela(
        self, frame: np.ndarray, gray: np.ndarray, detections: list[Detection]
    ) -> None:
        """Alimenta a contagem de bandos e a análise de comportamento da janela."""
        try:
            especies = self._especies_dos_tracks(frame, detections)
            if self._contador is not None:
                self._contador.registrar(detections, especies)
            altura, largura = frame.shape[:2]
            energias: dict[int, float | None] = {}
            for detection in detections:
                if detection.track_id is not None:
                    energias[detection.track_id] = energia_movimento(
                        self._prev_gray, gray, detection.bbox
                    )
            comportamento = classificar_comportamento(
                detections,
                self._roi_zones,
                largura=largura,
                altura=altura,
                energias=energias,
            )
            self._guardar_comportamento(comportamento)
        except Exception:
            logger.exception("Falha ao observar a janela do evento")

    def _log_supressao(self) -> None:
        """Registra (com throttling) que a mesma ave continua — alerta suprimido.

        Transparência do Alaris Core: a ave permanece no comedouro, então o
        sistema mantém o rastreio e o buffer ativos, porém **não** cria um novo
        alerta/registro — evitando spam da mesma visita. O log é limitado a uma
        mensagem a cada 15 s para não poluir o painel.
        """
        agora = time.time()
        if agora - self._ultimo_log_supressao < 15.0:
            return
        self._ultimo_log_supressao = agora
        self._pensar(
            "Mesma ave ainda no comedouro — novo alerta/registro suprimido "
            "(mesmo evento em andamento).",
            nivel=NIVEL_INFO,
            zonas=self.zone_validator.active_presence_zones(),
        )

    def _is_detection_allowed(
        self, detection: Detection, width: int, height: int
    ) -> bool:
        """Valida a detecção contra as ROI retangulares e as zonas poligonais.

        Regras (aplicadas ao centro da caixa delimitadora):

        - Se existir qualquer região de inclusão (ROI ou polígono), a ave
          precisa estar dentro de ao menos uma delas.
        - Se o centro cair em qualquer região de exclusão (ROI ou polígono),
          a detecção é descartada — útil para ignorar galhos, reflexos ou
          tráfego.
        """
        center_x, center_y = detection.normalized_center(width, height)

        roi_includes = [z for z in self._roi_zones if z.type == RoiType.INCLUDE]
        roi_excludes = [z for z in self._roi_zones if z.type == RoiType.EXCLUDE]
        inclusion_zones = [
            zone for zone in self._configured_zones if zone.mode == ZoneMode.INCLUDE
        ]

        # Inclusão: exige que o centro esteja dentro de alguma região válida.
        if roi_includes or inclusion_zones:
            inside_include = any(
                zone.contains(center_x, center_y) for zone in roi_includes
            ) or any(
                point_in_polygon(
                    center_x,
                    center_y,
                    [(point.x, point.y) for point in zone.points],
                )
                for zone in inclusion_zones
            )
            if not inside_include:
                return False

        # Exclusão: descarta detecções dentro de áreas ignoradas.
        if any(zone.contains(center_x, center_y) for zone in roi_excludes):
            return False
        return not any(
            point_in_polygon(
                center_x, center_y, [(point.x, point.y) for point in zone.points]
            )
            for zone in self._configured_zones
            if zone.mode == ZoneMode.EXCLUDE
        )

    def _ensure_stream(self) -> CameraStreamer | None:
        manager = get_camera_manager()
        streamer = manager.get_streamer(self.camera_id)
        if streamer is None:
            streamer = manager.upsert_streamer(self.camera_id)
        if streamer is None:
            return None
        if streamer.status != StreamStatus.ONLINE:
            streamer.open()
        return streamer

    def _handle_trigger(
        self,
        frame: np.ndarray,
        detection: Detection,
        trigger_zone_id: str,
        dwell: float,
        pre_frames: list[np.ndarray],
        fps: float,
        pre_seconds: float,
    ) -> None:
        visit_id = str(uuid.uuid4())
        # Aves passam pelo classificador de espécies; a fauna noturna (não-ave)
        # usa diretamente o nome traduzido da classe detectada (ex.: "Gato").
        if detection.class_id == self.detector.bird_class_id:
            species_pred = self.classifier.classify(frame, detection.bbox)
            species = species_pred.species
            species_extras = species_pred.extras or {}
        else:
            species = translate_class_name(detection.class_name)
            species_extras = {"fauna_noturna": True}
        conf = float(detection.confidence)

        post_sec = float(
            self.settings_repo.get("post_record_seconds")
            or self.settings.post_record_seconds
        )
        # Seletor do melhor quadro: avalia nitidez, confiança e enquadramento ao
        # longo de toda a janela. A foto oficial passa a ser o quadro mais nítido,
        # e não mais o instante exato do gatilho.
        self._best_selector = (
            SeletorMelhorQuadro(
                escala_nitidez=self.settings.best_frame_sharpness_scale,
                proporcao_ideal=self.settings.best_frame_ideal_area_ratio,
                nitidez_minima=self.settings.best_frame_min_sharpness,
            )
            if self.settings.best_frame_enabled
            else None
        )
        self._pending_event = {
            "visit_id": visit_id,
            "species": species,
            "confidence": conf,
            "detection": detection,
            "zone_id": trigger_zone_id,
            "dwell": dwell,
            "pre_frames": pre_frames,
            "fps": fps,
            "species_extras": species_extras,
            # Registra se a captura ocorreu com o realce de visão noturna ativo.
            "night_mode": self._night_active,
            "pre_seconds": float(pre_seconds),
            "post_seconds": post_sec,
            # Contexto sistêmico aplicado à inferência (clima/horário).
            "contexto": self._ultimo_ajuste,
        }
        # Reinicia a inteligência da janela: contagem de bandos e comportamento.
        self._contador = ContadorIndividuos()
        self._especies_por_track = {}
        if detection.track_id is not None and species:
            self._especies_por_track[detection.track_id] = species
        self._comportamento_evento = None
        # Pensamento da IA: detecção que disparou a janela de evento.
        self._pensar(
            f"IA detectou {species} (Conf: {conf:.2f}) — iniciando janela de "
            f"{float(pre_seconds):.0f}s + {post_sec:.0f}s.",
            nivel=NIVEL_SUCESSO,
            species=species,
            confidence=round(conf, 4),
            zone=trigger_zone_id,
        )
        self._post_frames_remaining = max(int(post_sec * fps), 0)
        self._post_collected = []
        if self._post_frames_remaining == 0:
            self._finalize_visit()

    def _finalize_visit(self) -> None:
        """Fecha a janela do evento e delega a persistência ao executor."""
        event = self._pending_event
        self._pending_event = None
        selector = self._best_selector
        self._best_selector = None
        contador = self._contador
        self._contador = None
        comportamento = self._comportamento_evento
        self._comportamento_evento = None
        self._especies_por_track = {}
        if event is None:
            return

        frames = list(event["pre_frames"]) + list(self._post_collected)
        self._post_collected = []
        best = selector.resultado() if selector is not None else None

        # Durante o encerramento o executor pode estar fechado: nesse caso grava
        # de forma síncrona para não perder a última visita.
        if self._finalizer_closed:
            self._persist_visit(event, frames, best, contador, comportamento)
            return
        try:
            self._finalizer.submit(
                self._persist_visit, event, frames, best, contador, comportamento
            )
        except RuntimeError:
            self._persist_visit(event, frames, best, contador, comportamento)

    def _enhance_frame(
        self, frame: np.ndarray, night_mode: bool
    ) -> np.ndarray | None:
        """Aplica o pipeline de melhoria (CLAHE + denoise) ao melhor quadro."""
        if not self.settings.enhancement_enabled:
            return None
        clip = float(self.settings.enhancement_clahe_clip)
        if night_mode:
            # A visão noturna já realçou o contraste; suaviza para não saturar.
            clip = max(1.0, clip * 0.6)
        try:
            return realcar_quadro_da_ave(
                frame,
                clahe_clip=clip,
                clahe_grid=self.settings.enhancement_clahe_grid,
                reduzir_ruido=self.settings.enhancement_denoise,
                forca_ruido=self.settings.enhancement_denoise_strength,
                largura_maxima=self.settings.enhancement_max_width,
                largura_minima=self.settings.enhancement_min_width,
            )
        except Exception:
            logger.exception("Falha ao realçar o melhor quadro da visita")
            return None

    @staticmethod
    def _escala_caixa(
        bbox: tuple[float, float, float, float],
        origem: np.ndarray,
        destino: np.ndarray,
    ) -> tuple[float, float, float, float]:
        """Reescala a caixa da ave quando a foto tratada muda de resolução.

        O enhancement pode redimensionar o quadro (ex.: 1920 → 1280 px). A caixa
        detectada está nas coordenadas originais; sem este ajuste o recorte da
        ave sairia deslocado na imagem tratada.
        """
        altura_o, largura_o = origem.shape[:2]
        altura_d, largura_d = destino.shape[:2]
        if (
            largura_o <= 0
            or altura_o <= 0
            or (largura_o == largura_d and altura_o == altura_d)
        ):
            return bbox
        escala_x = largura_d / float(largura_o)
        escala_y = altura_d / float(altura_o)
        x1, y1, x2, y2 = bbox
        return (x1 * escala_x, y1 * escala_y, x2 * escala_x, y2 * escala_y)

    def _clip_overlay(self, event: dict[str, Any], detected_at: str, frames):
        """Monta a função que grava a tarja de identificação em cada quadro.

        A tarja (largura total) é pré-renderizada **uma única vez** por clipe, no
        tamanho real do quadro; cada quadro apenas a mescla — mantendo a gravação
        barata. Retorna ``None`` quando o recurso está desligado nas configurações.
        """
        if not self.settings.clip_overlay_enabled or not frames:
            return None
        try:
            largura = int(frames[0].shape[1])
        except Exception:
            largura = 1920
        try:
            camera = self.camera_repo.get(self.camera_id)
            camera_name = camera.get("name") if camera else None
        except Exception:
            camera_name = None
        hora = detected_at.replace("T", " ").replace("Z", " UTC")
        strip = build_clip_banner(
            largura,
            species=str(event.get("species") or "Ave"),
            confidence=float(event.get("confidence") or 0.0),
            camera_name=camera_name,
            timestamp=hora,
        )
        return lambda frame: apply_banner(frame, strip)

    def _persist_visit(
        self,
        event: dict[str, Any],
        frames: list[np.ndarray],
        best: MelhorQuadro | None,
        contador: ContadorIndividuos | None = None,
        comportamento: Comportamento | None = None,
    ) -> None:
        """Grava o clipe, gera a foto tratada e registra a visita (worker).

        Executa fora do laço de captura. Isola falhas: um erro aqui não derruba
        o pipeline nem a próxima captura.
        """
        # Portão de comportamento: quando exigido, só registra se a ave estiver
        # efetivamente se alimentando (bico no comedouro/bebedouro).
        if (
            self.settings.behavior_require_feeding
            and comportamento is not None
            and comportamento.tipo != "feeding"
        ):
            logger.info(
                "Visita descartada (comportamento=%s; exige alimentação) camera=%s",
                comportamento.tipo,
                self.camera_id,
            )
            return

        visit_id = event["visit_id"]
        detected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # Tarja de identificação do Alaris gravada no clipe: o vídeo salvo já
        # mostra a espécie e a confiança, mesmo fora do painel.
        overlay_fn = self._clip_overlay(event, detected_at, frames)
        clip_path = save_clip_mp4(
            frames, self.camera_id, visit_id, event["fps"], overlay_fn=overlay_fn
        )
        clip_rel = relative_to_captures(clip_path) if clip_path else None

        # Foto oficial: melhor quadro (mais nítido) realçado. Reserva: se a
        # seleção estiver desligada ou falhar, usa o último quadro da janela.
        source_frame: np.ndarray | None = None
        source_bbox: tuple[float, float, float, float] = tuple(
            event["detection"].bbox
        )
        if best is not None:
            source_frame = best.frame
            source_bbox = best.bbox
        elif frames:
            source_frame = frames[-1]

        thumb_rel: str | None = None
        crop_path: str | None = None
        enhanced = False
        if source_frame is not None:
            enhanced_frame = self._enhance_frame(
                source_frame, bool(event.get("night_mode"))
            )
            if enhanced_frame is not None:
                enhanced = True
                quality = self.settings.enhancement_jpeg_quality
                thumb = save_thumbnail(
                    enhanced_frame, self.camera_id, visit_id, quality=quality
                )
                thumb_rel = relative_to_captures(thumb) if thumb else None
                # A caixa é reescalada se o enhancement mudou a resolução.
                crop_bbox = self._escala_caixa(
                    source_bbox, source_frame, enhanced_frame
                )
                crop_path = save_bird_crop(
                    enhanced_frame,
                    crop_bbox,
                    visit_id,
                    quality=quality,
                    margin=self.settings.smart_crop_margin,
                    min_dimension=self.settings.smart_crop_min_dimension,
                    max_dimension=self.settings.smart_crop_max_dimension,
                )
            if thumb_rel is None:
                # Reserva: nunca deixa a visita sem foto.
                thumb = save_thumbnail(source_frame, self.camera_id, visit_id)
                thumb_rel = relative_to_captures(thumb) if thumb else None
                if crop_path is None:
                    crop_path = save_bird_crop(
                        source_frame,
                        source_bbox,
                        visit_id,
                        margin=self.settings.smart_crop_margin,
                        min_dimension=self.settings.smart_crop_min_dimension,
                        max_dimension=self.settings.smart_crop_max_dimension,
                    )

        metadata: dict[str, Any] = {
            "class_name": event["detection"].class_name,
            "species_extras": event.get("species_extras") or {},
            "crop_path": crop_path,
            "night_mode": bool(event.get("night_mode")),
            # Marca que a foto passou pelo pipeline de melhoria (selo "HD").
            "enhanced": enhanced,
            "clip_seconds": round(
                float(event.get("pre_seconds", 0.0))
                + float(event.get("post_seconds", 0.0)),
                2,
            ),
        }
        if best is not None:
            metricas = best.metricas
            metadata.update(
                {
                    "best_frame_score": round(metricas.escore, 4),
                    "best_frame_sharpness": round(metricas.nitidez, 2),
                    "best_frame_area_ratio": round(metricas.proporcao_area, 5),
                    "best_frame_confidence": round(metricas.confianca, 4),
                    # Falso só quando TODOS os quadros eram desfoque (fallback).
                    "best_frame_sharpness_ok": bool(best.nitidez_aprovada),
                }
            )

        # Contagem de indivíduos/bandos da janela (multi-espécie quando possível).
        if contador is not None:
            resumo_bandos = contador.resumo()
            metadata["individuals_total"] = resumo_bandos["individuos_total"]
            metadata["individuals_peak"] = resumo_bandos["pico_simultaneo"]
            metadata["individuals_by_species"] = resumo_bandos["pico_por_especie"]
            metadata["individuals_by_class"] = resumo_bandos["pico_por_classe"]
            metadata["individuals_summary"] = resumo_bandos["descricao"]

        # Comportamento predominante (alimentando-se × pousada × em movimento).
        if comportamento is not None:
            metadata.update(comportamento.as_metadata())

        # Contexto sistêmico aplicado (clima/horário) — para auditoria.
        contexto = event.get("contexto")
        if contexto is not None:
            metadata["context_adjustment"] = {
                "confidence": round(float(contexto.confianca_efetiva), 4),
                "tta": bool(contexto.tta),
                "adaptive_contrast": bool(contexto.contraste_adaptativo),
                "reasons": list(contexto.motivos),
            }

        # Aceleração em uso (telemetria de Edge AI).
        if self.detector.backend:
            metadata["inference_backend"] = self.detector.backend

        # Status ecológico regional, quando a espécie já é conhecida na captura.
        especie_evento = str(event.get("species") or "")
        tem_especie = bool(especie_evento) and especie_evento.lower() != "bird"
        if tem_especie:
            metadata["ecological"] = descrever(especie_evento)

        # --- Análise enriquecida da IA ("laudo" estruturado da visita) ---
        nome_cientifico = self._nome_cientifico(event, especie_evento)
        nitidez = (
            round(float(best.metricas.nitidez), 2) if best is not None else None
        )
        temperatura, categoria_clima = self._clima_para_anotacao()
        if self.settings.ai_insights_enabled:
            metadata["ai_analysis"] = montar_analise_ia(
                species=especie_evento or event["species"],
                scientific_name=nome_cientifico,
                ecological=metadata.get("ecological"),
                behavior=(comportamento.tipo if comportamento is not None else None),
                behavior_label=(
                    comportamento.rotulo if comportamento is not None else None
                ),
                individuals_peak=metadata.get("individuals_peak"),
                temperature=temperatura,
                weather_category=categoria_clima,
                confidence=float(event["confidence"]),
                sharpness=nitidez,
            )
            self._anunciar_analise(
                species=especie_evento or event["species"],
                scientific_name=nome_cientifico,
                ecological=metadata.get("ecological"),
                behavior_label=(
                    comportamento.rotulo if comportamento is not None else None
                ),
                individuals_peak=metadata.get("individuals_peak"),
                sharpness=nitidez,
                clip_seconds=metadata.get("clip_seconds"),
            )

        try:
            visit = self.visit_repo.create(
                visit_id=visit_id,
                camera_id=self.camera_id,
                species=event["species"],
                confidence=float(event["confidence"]),
                detected_at=detected_at,
                dwell_seconds=float(event["dwell"]),
                clip_path=clip_rel,
                thumbnail_path=thumb_rel,
                bbox=event["detection"].as_list(),
                zone_id=event["zone_id"],
                metadata=metadata,
            )
        except Exception:
            logger.exception("Failed to persist visit for camera %s", self.camera_id)
            return

        # Log de anomalias: espécie que não aparecia há meses reapareceu.
        if tem_especie:
            anomalia = registrar_retorno_especie(
                species=especie_evento,
                scientific_name=nome_cientifico,
                visit_id=visit_id,
                exclude_visit_id=visit_id,
            )
            if anomalia:
                self._pensar(
                    f"Anomalia: {especie_evento} não era registrada há "
                    f"{anomalia.get('days_absent')} dias!",
                    nivel=NIVEL_ALERTA,
                    species=especie_evento,
                    days_absent=anomalia.get("days_absent"),
                )

        visit_out = self.visit_repo.to_out(visit)

        if self.on_visit and self._notify_enabled():
            if visit_out.confidence >= self._min_confidence_notify():
                try:
                    self.on_visit(visit_out)
                except Exception:
                    logger.exception("on_visit callback failed")

    @staticmethod
    def _nome_cientifico(event: dict[str, Any], especie: str) -> str | None:
        """Nome científico da espécie (extras do classificador ou base regional)."""
        extras = event.get("species_extras") or {}
        for chave in ("scientific_name", "scientificName", "scientific"):
            valor = extras.get(chave)
            if valor:
                return str(valor)
        if especie and especie.lower() != "bird":
            info = info_especie(common_name=especie)
            if info is not None:
                return info.scientific_name
        return None

    @staticmethod
    def _clima_para_anotacao() -> tuple[float | None, str | None]:
        """Temperatura e categoria de clima atuais (cache do serviço de clima)."""
        try:
            from app.services.weather_service import get_weather_service

            snap = get_weather_service().current()
            if snap is not None and getattr(snap, "available", False):
                return snap.temperature, snap.category
        except Exception:
            logger.debug("Clima indisponível para a anotação da IA", exc_info=True)
        return None, None

    def _anunciar_analise(
        self,
        *,
        species: str,
        scientific_name: str | None,
        ecological: dict[str, Any] | None,
        behavior_label: str | None,
        individuals_peak: int | None,
        sharpness: float | None,
        clip_seconds: Any,
    ) -> None:
        """Emite os "pensamentos" finais da IA sobre o melhor quadro da janela."""
        # 1) Nitidez do quadro escolhido (qualidade do Laplacian).
        if sharpness is not None:
            if sharpness >= 300:
                qualidade = "Excelente"
            elif sharpness >= 120:
                qualidade = "Boa"
            elif sharpness >= 40:
                qualidade = "Aceitável"
            else:
                qualidade = "Baixa"
            self._pensar(
                f"Analisando nitidez do frame (Laplacian: {sharpness:.1f} — {qualidade}).",
                nivel=NIVEL_ANALISE,
                sharpness=sharpness,
            )

        # 2) Identificação da espécie + status ecológico + comportamento.
        eco = ecological or {}
        rotulo = eco.get("label")
        if species and species.lower() != "bird":
            partes = [valor for valor in (rotulo, behavior_label) if valor]
            sufixo = f" ({' / '.join(partes)})" if partes else ""
            mensagem_id = f"Espécie identificada com sucesso: {species}{sufixo}."
            # Combina nitidez validada quando o quadro é nítido (cena ideal).
            if sharpness is not None and sharpness >= 120:
                mensagem_id += " | Nitidez ideal de frame validada"
            self._pensar(
                mensagem_id,
                nivel=NIVEL_SUCESSO,
                species=species,
                scientific_name=scientific_name,
                ecological_status=eco.get("status"),
            )
        else:
            self._pensar(
                "Detecção genérica de ave — aguardando identificação da espécie.",
                nivel=NIVEL_INFO,
            )

        # 3) Contagem de bando (pico simultâneo no comedouro).
        if individuals_peak is not None and int(individuals_peak) > 1:
            self._pensar(
                f"Bando detectado: pico de {int(individuals_peak)} indivíduos simultâneos.",
                nivel=NIVEL_ANALISE,
                individuals_peak=int(individuals_peak),
            )

        # 4) Buffer temporal + thumbnail de alta definição.
        if clip_seconds:
            self._pensar(
                f"Buffer temporal de {float(clip_seconds):.0f}s salvo e thumbnail "
                "de alta definição gerada.",
                nivel=NIVEL_INFO,
                clip_seconds=float(clip_seconds),
            )

    def run(self) -> None:
        logger.info("Pipeline started for camera %s", self.camera_id)
        if not self.detector.load():
            logger.error(
                "Detector unavailable for camera %s: %s",
                self.camera_id,
                self.detector.load_error,
            )
            self._pensar(
                f"Modelo de IA indisponível: {self.detector.load_error}",
                nivel=NIVEL_ATENCAO,
            )
        else:
            self._pensar(
                f"Alaris Core pronto ({self.detector.backend or 'pytorch'}) — "
                "monitorando o stream em tempo real.",
                nivel=NIVEL_SUCESSO,
                backend=self.detector.backend,
            )

        self._load_zones()
        infer_every_n = 4
        frame_idx = 0
        last_zone_reload = 0.0
        detections: list[Detection] = []
        # Rastreio com persistência: mantém aves imóveis na mesma visita mesmo
        # que o YOLO perca a detecção por alguns instantes.
        tracker = BoxTracker(retention_seconds=self.settings.object_persistence_time)
        # Aplica a calibração assim que o pipeline inicia.
        self._apply_calibration(tracker)
        # Contador de ciclos de inferência pulados por ausência de movimento.
        idle_inference_skips = 0

        while not self._stop.is_set():
            try:
                # Recarrega zonas/ROI quando solicitado (ex.: salvou no painel)
                # ou a cada 15s como rede de segurança.
                if self._zones_reload.is_set():
                    self._load_zones()
                    self._zones_reload.clear()
                    last_zone_reload = time.time()
                elif time.time() - last_zone_reload > 15:
                    self._load_zones()
                    last_zone_reload = time.time()

                streamer = self._ensure_stream()
                if streamer is None:
                    time.sleep(1.0)
                    continue

                ok, raw_frame = streamer.read()
                if not ok or raw_frame is None:
                    streamer.reconnect()
                    continue

                # Visão noturna: realça o contraste em quadros escuros/IR antes
                # de qualquer uso (buffer, detecção, anotação e clipes). Em cenas
                # claras (modo auto) o quadro original é devolvido sem custo.
                night = self.night_vision.process(raw_frame)
                frame = night.frame
                self._night_active = night.applied
                streamer.set_night_mode(night.applied)
                # Escala de cinza do quadro atual (energia de movimento do
                # comportamento); reaproveitada no fim do ciclo como "anterior".
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                fps = streamer.fps
                pre_seconds = float(
                    self.settings_repo.get("pre_record_seconds")
                    or self.settings.pre_record_seconds
                )
                self.buffer.configure(seconds=pre_seconds, fps=fps)
                self.buffer.push(frame)
                frame_idx += 1

                if frame_idx % infer_every_n == 0:
                    # Relê a calibração do painel (em memória) a cada ciclo de
                    # inferência, para refletir ajustes quase em tempo real.
                    self._apply_calibration(tracker)
                    # Contexto sistêmico: ajusta a sensibilidade ao clima/à luz.
                    calibracao = get_calibration_service().current()
                    ajuste = ajustar_sensibilidade(
                        calibracao.yolo_confidence,
                        categoria_clima=self._categoria_clima(),
                        noite=self._night_active,
                    )
                    self._ultimo_ajuste = ajuste
                    # Telemetria do motor (AI Core): FPS e estado "pensando".
                    try:
                        telemetria = get_ai_telemetry()
                        telemetria.definir_fps(fps)
                        telemetria.definir_estado(ESTADO_ANALISANDO)
                    except Exception:
                        pass
                    # Auto-calibração: anuncia no log cognitivo só quando muda.
                    chave_ajuste = (
                        round(float(ajuste.confianca_efetiva), 4),
                        bool(ajuste.tta),
                        bool(ajuste.contraste_adaptativo),
                        tuple(ajuste.motivos),
                    )
                    if chave_ajuste != self._ultimo_ajuste_chave:
                        self._ultimo_ajuste_chave = chave_ajuste
                        self._anunciar_ajuste(ajuste, calibracao.yolo_confidence)
                    # Portão de movimento: roda o YOLO quando há movimento, quando
                    # já existe uma ave rastreada (não perdê-la se ficar imóvel) ou,
                    # por segurança, a cada `IDLE_INFER_MAX_SKIPS` ciclos parados.
                    # O movimento é medido no quadro cru: o realce noturno amplia
                    # o ruído e poderia gerar falsos positivos no portão.
                    has_motion = self.motion.detect(raw_frame)
                    if (
                        has_motion
                        or tracker.has_tracks()
                        or idle_inference_skips >= IDLE_INFER_MAX_SKIPS
                    ):
                        # Sincroniza as âncoras do YOLO; se vier vazio, o rastreio
                        # retém as caixas conhecidas pela janela de persistência.
                        detections = tracker.sync(
                            frame,
                            self._detect_in_zones(
                                frame,
                                tta=ajuste.tta,
                                contraste=ajuste.contraste_adaptativo,
                                confianca_base=ajuste.confianca_efetiva,
                            ),
                        )
                        self._inferencias += 1
                        idle_inference_skips = 0
                    else:
                        idle_inference_skips += 1
                        detections = tracker.update(frame)
                else:
                    detections = tracker.update(frame)

                h, w = frame.shape[:2]
                detections = [
                    detection
                    for detection in detections
                    if self._is_detection_allowed(detection, w, h)
                ]
                # Espécies por indivíduo (cache por track_id): alimenta os selos
                # do Alaris no stream ao vivo e os cards de status do painel.
                if detections:
                    self._especies_dos_tracks(frame, detections)
                species_by_track = self._especies_por_track
                self._reportar_stream(streamer, detections, species_by_track)
                centers = [d.normalized_center(w, h) for d in detections]
                triggers = self.zone_validator.update(centers)
                if triggers and detections and self._pending_event is None:
                    trigger = triggers[0]
                    trigger_zone = next(
                        (
                            zone
                            for zone in self.zone_validator.zones
                            if zone.id == trigger.zone_id
                        ),
                        None,
                    )
                    eligible = [
                        detection
                        for detection in detections
                        if trigger_zone is None
                        or point_in_polygon(
                            *detection.normalized_center(w, h),
                            [(point.x, point.y) for point in trigger_zone.points],
                        )
                    ]
                    if eligible:
                        best = max(eligible, key=lambda d: d.confidence)
                        pre = self.buffer.snapshot(
                            include_seconds=pre_seconds,
                            exclude_latest=True,
                        )
                        self._handle_trigger(
                            frame=frame,
                            detection=best,
                            trigger_zone_id=trigger.zone_id,
                            dwell=trigger.dwell_seconds,
                            pre_frames=pre,
                            fps=self.buffer.estimated_fps(),
                            pre_seconds=pre_seconds,
                        )
                elif (
                    detections
                    and self._pending_event is None
                    and self.zone_validator.has_active_presence()
                ):
                    # A mesma ave continua no comedouro: mantém o rastreio e o
                    # buffer ativos, mas SEM novo alerta/registro (anti-spam).
                    self._log_supressao()

                # Janela pós-evento: coleta os quadros para o clipe de ~6 s e
                # avalia o melhor quadro (nitidez + confiança + enquadramento).
                # Fica após a detecção para reaproveitar as caixas rastreadas.
                if self._pending_event is not None:
                    if self._best_selector is not None:
                        self._best_selector.considerar(frame, detections)
                    # Contagem de bandos e análise de comportamento da janela.
                    self._observar_janela(frame, gray_frame, detections)
                    if self._post_frames_remaining > 0:
                        self._post_collected.append(frame.copy())
                        self._post_frames_remaining -= 1
                        if self._post_frames_remaining <= 0:
                            self._finalize_visit()

                streamer.set_annotated_frame(
                    draw_bird_detections(
                        frame,
                        detections,
                        min_confidence=self.detector.confidence,
                        species_by_track=species_by_track,
                    )
                )
                # Guarda o cinza atual como referência do próximo quadro.
                self._prev_gray = gray_frame

            except Exception:
                logger.exception("Pipeline loop error camera=%s", self.camera_id)
                time.sleep(0.5)

        if self._pending_event is not None:
            try:
                self._finalize_visit()
            except Exception:
                logger.exception("Failed to finalize pending visit on stop")

        # Aguarda o término do pós-processamento pendente (clipe + foto tratada)
        # e libera o executor do pipeline.
        self._finalizer_closed = True
        try:
            self._finalizer.shutdown(wait=True)
        except Exception:
            logger.exception("Falha ao encerrar o executor de pós-processamento")

        logger.info("Pipeline stopped for camera %s", self.camera_id)


class PipelineSupervisor:
    """Starts/stops per-camera pipelines."""

    def __init__(self) -> None:
        self._pipelines: dict[str, CameraPipeline] = {}
        self._lock = threading.RLock()
        self._on_visit: VisitHandler | None = None

    def set_visit_handler(self, handler: VisitHandler) -> None:
        self._on_visit = handler

    def start_camera(self, camera_id: str) -> None:
        with self._lock:
            existing = self._pipelines.get(camera_id)
            if existing and existing.is_alive():
                return
            pipeline = CameraPipeline(camera_id, on_visit=self._on_visit)
            self._pipelines[camera_id] = pipeline
            pipeline.start()

    def stop_camera(self, camera_id: str) -> None:
        with self._lock:
            pipeline = self._pipelines.pop(camera_id, None)
        if pipeline is not None:
            pipeline.stop()
            pipeline.join(timeout=5.0)
        get_camera_manager().remove_streamer(camera_id)
        # Limpa o estado do Alaris Core deste stream no registro por câmera.
        get_stream_registry().remove(camera_id)

    def restart_camera(self, camera_id: str) -> None:
        self.stop_camera(camera_id)
        row = CameraRepository(get_settings().db_path).get(camera_id)
        if row and row["is_active"]:
            self.start_camera(camera_id)

    def reload_zones(self, camera_id: str | None = None) -> None:
        """Pede a recarga de zonas/ROI sem reiniciar os pipelines.

        Se ``camera_id`` for informado, recarrega apenas aquela câmera; caso
        contrário, recarrega todos os pipelines em execução.
        """
        with self._lock:
            if camera_id is None:
                pipelines = list(self._pipelines.values())
            else:
                pipeline = self._pipelines.get(camera_id)
                pipelines = [pipeline] if pipeline is not None else []
        for pipeline in pipelines:
            pipeline.request_zones_reload()

    def sync_from_db(self) -> None:
        settings = get_settings()
        repo = CameraRepository(settings.db_path)
        enabled_ids = {row["id"] for row in repo.list_all() if row["is_active"]}
        with self._lock:
            running = set(self._pipelines.keys())
        for camera_id in running - enabled_ids:
            self.stop_camera(camera_id)
        for camera_id in enabled_ids:
            with self._lock:
                pipeline = self._pipelines.get(camera_id)
                alive = pipeline is not None and pipeline.is_alive()
            if not alive:
                self.start_camera(camera_id)

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._pipelines.keys())
        for camera_id in ids:
            self.stop_camera(camera_id)


_supervisor: PipelineSupervisor | None = None
_supervisor_lock = threading.Lock()


def get_pipeline_supervisor() -> PipelineSupervisor:
    global _supervisor
    with _supervisor_lock:
        if _supervisor is None:
            _supervisor = PipelineSupervisor()
        return _supervisor
