"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_FILE)
DEFAULT_APP_DATA_DIR = BASE_DIR / "app-data"


class Settings(BaseModel):
    app_name: str = "Bem-Te-Vi"
    port: int = Field(default=8000)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    ai_external_api_key: str = ""
    ai_external_model: str = "gpt-4o-mini"
    # URL base do provedor de IA compatível com a API da OpenAI. Serve para
    # OpenRouter, Groq, Ollama etc. O chat é chamado em "{base}/chat/completions".
    # Para o Google Gemini esta URL é IGNORADA (usa-se o endpoint oficial).
    ai_external_base_url: str = "https://api.openai.com/v1"
    # Provedor efetivo da IA externa: "google" (Gemini oficial) ou "openai"
    # (qualquer endpoint compatível com a OpenAI). Vazio → detecta pela URL base.
    ai_external_provider: str = ""
    app_data_dir: Path = DEFAULT_APP_DATA_DIR
    # Chave mestra (Fernet) para criptografar as credenciais das câmeras em
    # repouso. Recomendado definir via ENCRYPTION_KEY no .env (base64-url de 32
    # bytes). Vazio → usa/gera a chave em secrets/camera_key.fernet.
    encryption_key: str = ""
    # --- Multi-Câmera (Central de Câmeras / Alaris Core distribuído) ---
    # Acesso remoto: por padrão a API aceita SOMENTE conexões locais (loopback).
    # Defina ALLOW_REMOTE_ACCESS=true apenas se for expor a API na rede de forma
    # consciente (e idealmente atrás de um proxy reverso com autenticação).
    allow_remote_access: bool = False
    # Hosts aceitos no cabeçalho Host (proteção contra Host Header Injection).
    # Separados por vírgula; o padrão cobre apenas o uso local.
    allowed_hosts: str = "127.0.0.1,localhost"
    yolo_model: str = "yolov8n.pt"
    # Sensibilidade da detecção: quanto menor o limiar, mais aves são detectadas
    # (inclusive à distância, pequenas, camufladas ou com pouca luz), ao custo de
    # mais falsos positivos. 0.22 é o padrão de ALTA SENSIBILIDADE do Alaris Core
    # para câmeras de comedouro/ninho (aves pequenas e paradas ao pousar).
    yolo_confidence: float = Field(default=0.22, ge=0.05, le=1.0)
    # Tempo de permanência imóvel (segundos): por quanto tempo o rastreio mantém
    # a visita ativa mesmo se a ave ficar totalmente imóvel se alimentando (o
    # YOLO costuma perder aves paradas; a retenção evita reiniciar a visita).
    object_persistence_time: float = Field(default=10.0, ge=0.0, le=30.0)
    # Sensibilidade de detecção de movimento inicial (0 a 1). Valores maiores
    # detectam movimentos mais sutis (ave chegando ao comedouro).
    motion_sensitivity: float = Field(default=0.80, ge=0.0, le=1.0)
    # Classe do dataset COCO para "bird". Mantida em 14 como padrão.
    yolo_bird_class_id: int = Field(default=14, ge=0)
    # --- Edge AI: aceleração da inferência ---
    # Backend preferido: "auto" (TensorRT > ONNX > PyTorch), "engine"/"tensorrt",
    # "onnx" ou "pt". Em "auto", usa o artefato otimizado se existir ao lado do
    # .pt; senão, cai no PyTorch (FP16 em GPU CUDA).
    yolo_acceleration: str = "auto"
    # Dispositivo de inferência: "auto" (GPU se houver, senão CPU), "cpu" ou
    # "0"/"1"... (índice da GPU CUDA).
    yolo_device: str = "auto"
    # Usa FP16 no PyTorch quando houver GPU CUDA (quase 2x mais rápido, mínima
    # perda de precisão). Ignorado em CPU e nos backends TRT/ONNX.
    yolo_half: bool = False
    # Tamanho de entrada da inferência (px). Menor = mais rápido; 640 é o padrão
    # do YOLOv8. Para aves pequenas, 960/1280 aumentam o recall ao custo de tempo.
    yolo_imgsz: int = Field(default=640, ge=160, le=1920)
    # Test-Time Augmentation global (reforço de recall). Mais lento; o contexto
    # sistêmico já o liga automaticamente em clima adverso.
    yolo_tta: bool = False
    # Filtro de contraste adaptativo (CLAHE) antes da inferência: revela aves
    # pequenas/camufladas contra o fundo do comedouro. Não afeta a imagem gravada
    # nem o clipe. Já vem LIGADO por padrão.
    roi_adaptive_contrast: bool = True
    # --- Supressão de spam: mesma ave = mesmo evento ---
    # Tempo (s) de ausência necessário para ENCERRAR a presença de uma ave numa
    # zona. Enquanto a ave permanecer (mesmo que o YOLO a perca por instantes),
    # não há novo alerta/registro. Um valor alto evita alertas repetidos da mesma
    # visita; só depois desse tempo uma nova ave pode disparar um novo evento.
    presence_grace_seconds: float = Field(default=30.0, ge=0.0, le=600.0)
    # Cooldown mínimo (s) entre alertas na MESMA zona (piso). Rede de segurança
    # extra: mesmo que a presença se encerre, um novo alerta só ocorre após este
    # intervalo. Combina com o cooldown por zona configurado no painel.
    alert_cooldown_seconds: float = Field(default=30.0, ge=0.0, le=600.0)
    pre_record_seconds: float = Field(default=3.0, ge=3.0, le=30.0)
    post_record_seconds: float = 3.0
    camera_reconnect_delay_sec: float = 3.0
    # Teto de workers simultâneos do pool multi-câmera (1 por câmera ativa).
    camera_max_workers: int = Field(default=8, ge=1, le=16)
    # Backoff exponencial de reconexão: base e teto (segundos).
    camera_backoff_base_sec: float = Field(default=1.0, ge=0.5, le=30.0)
    camera_backoff_max_sec: float = Field(default=30.0, ge=1.0, le=300.0)
    # Quadros/segundo entregues pelo proxy MJPEG seguro.
    camera_proxy_fps: int = Field(default=15, ge=5, le=30)
    # --- YouTube Live (tradutor de links → stream direto via yt-dlp) ---
    # Quando ligado, links do YouTube (youtube.com/youtu.be) cadastrados como
    # câmera são traduzidos para o stream HLS direto antes do OpenCV abrir.
    youtube_resolver_enabled: bool = True
    # Tempo (s) de cache do link direto extraído (lives renovam o token com o
    # tempo; a reconexão força uma re-extração quando o stream cai).
    youtube_resolver_cache_sec: float = Field(default=90.0, ge=0.0, le=3600.0)
    # Arquivo de cookies do YouTube (formato Netscape) para lives que exigem
    # login/verificação anti-bot. Opcional.
    youtube_cookies_file: str | None = None
    media_retention_days: int = Field(default=30, ge=1)
    # Localização do alimentador (latitude/longitude), usada pela integração
    # meteorológica com a Open-Meteo. Padrão: São Paulo/SP.
    latitude: float = Field(default=-23.5505, ge=-90.0, le=90.0)
    longitude: float = Field(default=-46.6333, ge=-180.0, le=180.0)
    # Intervalo (minutos) de atualização do cache local de clima. Evita
    # requisições excessivas à API pública da Open-Meteo.
    weather_cache_minutes: int = Field(default=30, ge=5, le=1440)
    # Geração automática do time-lapse diário (resumo acelerado do dia).
    # `timelapse_enabled` liga/desliga o agendador em segundo plano.
    timelapse_enabled: bool = True
    # Fator de aceleração aplicado aos clipes do dia (8 = 8x mais rápido).
    timelapse_speed: float = Field(default=8.0, ge=1.0, le=60.0)
    # Horário local (0-23h) em que o resumo do dia é gerado automaticamente.
    timelapse_hour: int = Field(default=23, ge=0, le=23)
    timelapse_minute: int = Field(default=55, ge=0, le=59)
    # Quantos dias anteriores sem resumo são reprocessados ao iniciar o app.
    timelapse_backfill_days: int = Field(default=7, ge=0, le=90)
    # Visão noturna (infravermelho / baixa luz): realce de contraste (CLAHE) e
    # redução de ruído antes da inferência, ajudando o YOLOv8 a identificar
    # formas mesmo no escuro. Modo: "auto" (só quando o quadro está escuro),
    # "on" (sempre) ou "off". Também aceita true/false no .env.
    night_vision_mode: str = "auto"
    # Luminância média (0-255) abaixo da qual o modo "auto" considera baixa luz.
    night_vision_threshold: float = Field(default=60.0, ge=0.0, le=255.0)
    # Intensidade do realce de contraste local (CLAHE).
    night_vision_clahe_clip: float = Field(default=2.5, ge=1.0, le=8.0)
    # Tamanho da grade do CLAHE (número de blocos por lado).
    night_vision_clahe_grid: int = Field(default=8, ge=2, le=16)
    # Redução de ruído leve (median blur) antes do realce.
    night_vision_denoise: bool = True
    # Expansão opcional das classes detectadas para além de aves (fauna noturna
    # comum em quintais, como gatos e cachorros — classes do COCO).
    night_fauna_enabled: bool = False
    # Classes extras do COCO (ids separados por vírgula) quando a fauna noturna
    # está ligada. Padrão: 15 (cat) e 16 (dog).
    night_fauna_class_ids: str = "15,16"
    # --- Análise offline de vídeos (cartão de memória) ---
    # Limiar de confiança dedicado à análise offline: mais sensível que o da
    # captura ao vivo (0.25) para encontrar aves distantes ou paradas.
    offline_yolo_confidence: float = Field(default=0.25, ge=0.05, le=1.0)
    # Passo de amostragem de quadros (1 = todos; 2 = um a cada dois). Valores
    # maiores aceleram a análise em vídeos longos.
    offline_frame_stride: int = Field(default=2, ge=1, le=10)
    # Número máximo de clipes curtos gerados (um por ave distinta) para o botão
    # "assistir ao trecho" na Galeria. Limita o custo de CPU/tempo.
    offline_max_clips: int = Field(default=12, ge=0, le=100)
    # Duração (segundos) do trecho salvo ao redor da melhor captura de cada ave.
    offline_clip_seconds: float = Field(default=4.0, ge=1.0, le=20.0)
    # --- Gravação inteligente: melhor quadro + melhoria da imagem ---
    # Liga/desliga a escolha automática do quadro mais nítido da janela de
    # gravação (3 s antes + 3 s depois). Quando desligado, a foto oficial volta
    # a ser o quadro do instante do gatilho.
    best_frame_enabled: bool = True
    # Proporção ideal da tela (0-1) que a ave deve ocupar no melhor quadro.
    best_frame_ideal_area_ratio: float = Field(default=0.08, ge=0.001, le=1.0)
    # Escala usada para normalizar a variância do Laplaciano (nitidez) em (0, 1).
    best_frame_sharpness_scale: float = Field(default=120.0, gt=0.0)
    # Nitidez mínima (variância do Laplaciano) para aceitar o quadro. Abaixo
    # disto o quadro é descartado como desfoque de movimento; se nenhum passar,
    # usa-se o melhor disponível (fallback).
    best_frame_min_sharpness: float = Field(default=20.0, ge=0.0)
    # Melhoria automática (CLAHE + redução de ruído) do quadro escolhido.
    enhancement_enabled: bool = True
    enhancement_clahe_clip: float = Field(default=2.0, ge=1.0, le=8.0)
    enhancement_clahe_grid: int = Field(default=8, ge=2, le=16)
    enhancement_denoise: bool = True
    enhancement_denoise_strength: float = Field(default=5.0, ge=0.0, le=20.0)
    # Faixa de largura (px) da foto tratada: limita o custo do denoise acima do
    # máximo e garante "alta definição" abaixo do mínimo.
    enhancement_max_width: int = Field(default=1280, ge=320, le=4096)
    enhancement_min_width: int = Field(default=720, ge=0, le=4096)
    # Qualidade JPEG da foto tratada (thumbnail oficial e recorte).
    enhancement_jpeg_quality: int = Field(default=95, ge=50, le=100)
    # --- Overlays visuais do Alaris Core (clipes gravados) ---
    # Grava a tarja de identificação (marca Alaris + espécie + confiança) nos
    # clipes salvos, para que o vídeo já mostre qual ave aparece mesmo fora do
    # painel. Não afeta o stream ao vivo (que desenha as caixas em tempo real).
    clip_overlay_enabled: bool = True
    # --- Crop inteligente do recorte da ave ---
    # Margem (fração do tamanho da caixa) adicionada ao redor da ave, para dar
    # contexto sem cortar as pontas (penas, bico, patas).
    smart_crop_margin: float = Field(default=0.25, ge=0.0, le=2.0)
    # Dimensões (px) do recorte final: amplia abaixo do mínimo (alta definição)
    # e reduz acima do máximo (economia de disco).
    smart_crop_min_dimension: int = Field(default=640, ge=0, le=4096)
    smart_crop_max_dimension: int = Field(default=1024, ge=64, le=4096)
    # --- IA ciente do contexto (clima/horário) ---
    # Ajusta automaticamente a sensibilidade conforme o clima (chuva/nublado) e a
    # baixa luz, sempre de forma conservadora (só torna mais permissivo).
    adaptive_context_enabled: bool = True
    # --- Análise de comportamento ---
    # Quando ligado, só registra a visita se a ave estiver efetivamente se
    # alimentando (bico no comedouro). Desligado por padrão para não perder
    # visitas de aves que apenas pousam.
    behavior_require_feeding: bool = False
    # --- Log de anomalias acústico-visuais ---
    anomaly_log_enabled: bool = True
    # Intervalo (dias) sem registro a partir do qual o reaparecimento é anomalia.
    # 180 dias = ~6 meses.
    anomaly_species_gap_days: int = Field(default=180, ge=1, le=3650)
    # Janela (dias) para não repetir a mesma anomalia de espécie (evita spam).
    anomaly_cooldown_days: int = Field(default=30, ge=1, le=3650)
    # --- AI Core (IA visível/transparente) ---
    # Habilita os "pensamentos" da IA (log cognitivo em memória) e a anotação
    # ornitológica automática nos metadados da visita.
    ai_insights_enabled: bool = True
    # Capacidade do buffer circular do log cognitivo (últimos eventos em memória).
    ai_cognitive_log_capacity: int = Field(default=400, ge=50, le=5000)
    # --- Momentos Raros / Fotos de Postal ---
    # Curadoria automática: calcula a nitidez (variância do Laplaciano) das
    # capturas e destaca as melhores da semana + espécies raras/incomuns.
    rare_moments_enabled: bool = True
    # Intervalo (horas) entre varreduras automáticas das capturas novas.
    rare_moments_scan_hours: float = Field(default=6.0, ge=1.0, le=48.0)
    # Janela (dias) padrão da galeria "Momentos Raros".
    rare_moments_days: int = Field(default=7, ge=1, le=90)

    @property
    def db_path(self) -> Path:
        return self.app_data_dir / "bem-te-vi.db"

    @property
    def captures_dir(self) -> Path:
        return self.app_data_dir / "captures"

    @property
    def clips_dir(self) -> Path:
        return self.captures_dir / "clips"

    @property
    def thumbs_dir(self) -> Path:
        return self.captures_dir / "thumbs"

    @property
    def crops_dir(self) -> Path:
        return self.app_data_dir / "crops"

    @property
    def audio_dir(self) -> Path:
        """Pasta dos clipes de áudio das detecções sonoras (BirdNET)."""
        return self.captures_dir / "audio"

    @property
    def timelapses_dir(self) -> Path:
        """Pasta dos resumos do dia (time-lapses) em MP4."""
        return self.captures_dir / "timelapses"

    @property
    def reference_birds_dir(self) -> Path:
        return self.app_data_dir / "reference_birds"

    @property
    def secrets_dir(self) -> Path:
        return self.app_data_dir / "secrets"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_webhook_url)

    def allowed_hosts_list(self) -> list[str]:
        """Hosts aceitos no cabeçalho Host, a partir de ``ALLOWED_HOSTS``.

        Ignora entradas vazias. Nunca retorna lista vazia: cai no padrão local.
        """
        hosts = [
            part.strip()
            for part in str(self.allowed_hosts).split(",")
            if part.strip()
        ]
        return hosts or ["127.0.0.1", "localhost"]

    def night_fauna_class_id_list(self) -> list[int]:
        """Devolve os ids de classe extras (fauna noturna) como lista de inteiros.

        Ignora entradas vazias ou inválidas; a lista pode vir vazia.
        """
        ids: list[int] = []
        for part in str(self.night_fauna_class_ids).split(","):
            cleaned = part.strip()
            if not cleaned:
                continue
            try:
                ids.append(int(cleaned))
            except ValueError:
                continue
        return ids

    def ensure_directories(self) -> None:
        for path in (
            self.app_data_dir,
            self.captures_dir,
            self.clips_dir,
            self.thumbs_dir,
            self.crops_dir,
            self.audio_dir,
            self.timelapses_dir,
            self.reference_birds_dir,
            self.secrets_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Settings":
        app_data = os.getenv("APP_DATA_DIR")
        return cls(
            port=int(os.getenv("PORT", "8000")),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
            ai_external_api_key=os.getenv("AI_EXTERNAL_API_KEY", ""),
            ai_external_model=os.getenv("AI_EXTERNAL_MODEL", "gpt-4o-mini"),
            ai_external_base_url=os.getenv(
                "AI_EXTERNAL_BASE_URL", "https://api.openai.com/v1"
            ),
            ai_external_provider=os.getenv("AI_EXTERNAL_PROVIDER", "").strip().lower(),
            app_data_dir=Path(app_data) if app_data else DEFAULT_APP_DATA_DIR,
            encryption_key=os.getenv("ENCRYPTION_KEY", "").strip(),
            allow_remote_access=os.getenv("ALLOW_REMOTE_ACCESS", "false")
            .strip()
            .lower()
            in {"1", "true", "yes", "on", "sim"},
            allowed_hosts=os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost"),
            yolo_model=os.getenv("YOLO_MODEL", "yolov8n.pt"),
            yolo_confidence=min(
                1.0,
                max(0.05, float(os.getenv("YOLO_CONFIDENCE", "0.22"))),
            ),
            object_persistence_time=min(
                30.0,
                max(
                    0.0,
                    float(
                        os.getenv(
                            "OBJECT_PERSISTENCE_TIME",
                            os.getenv("YOLO_TRACK_RETENTION_SECONDS", "10.0"),
                        )
                    ),
                ),
            ),
            motion_sensitivity=min(
                1.0,
                max(0.0, float(os.getenv("MOTION_SENSITIVITY", "0.80"))),
            ),
            yolo_bird_class_id=max(0, int(os.getenv("YOLO_BIRD_CLASS_ID", "14"))),
            yolo_acceleration=os.getenv("YOLO_ACCELERATION", "auto"),
            yolo_device=os.getenv("YOLO_DEVICE", "auto"),
            yolo_half=os.getenv("YOLO_HALF", "false")
            .strip()
            .lower()
            in {"1", "true", "yes", "on", "sim"},
            yolo_imgsz=min(1920, max(160, int(os.getenv("YOLO_IMGSZ", "640")))),
            yolo_tta=os.getenv("YOLO_TTA", "false")
            .strip()
            .lower()
            in {"1", "true", "yes", "on", "sim"},
            roi_adaptive_contrast=os.getenv("ROI_ADAPTIVE_CONTRAST", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            presence_grace_seconds=min(
                600.0,
                max(0.0, float(os.getenv("PRESENCE_GRACE_SECONDS", "30"))),
            ),
            alert_cooldown_seconds=min(
                600.0,
                max(0.0, float(os.getenv("ALERT_COOLDOWN_SECONDS", "30"))),
            ),
            pre_record_seconds=max(
                3.0,
                float(os.getenv("PRE_RECORD_SECONDS", "3.0")),
            ),
            post_record_seconds=float(os.getenv("POST_RECORD_SECONDS", "3.0")),
            camera_reconnect_delay_sec=float(
                os.getenv("CAMERA_RECONNECT_DELAY_SEC", "3.0")
            ),
            camera_max_workers=min(
                16, max(1, int(os.getenv("CAMERA_MAX_WORKERS", "8")))
            ),
            camera_backoff_base_sec=min(
                30.0,
                max(0.5, float(os.getenv("CAMERA_BACKOFF_BASE_SEC", "1.0"))),
            ),
            camera_backoff_max_sec=min(
                300.0, max(1.0, float(os.getenv("CAMERA_BACKOFF_MAX_SEC", "30.0")))
            ),
            camera_proxy_fps=min(
                30, max(5, int(os.getenv("CAMERA_PROXY_FPS", "15")))
            ),
            youtube_resolver_enabled=os.getenv(
                "YOUTUBE_RESOLVER_ENABLED", "true"
            )
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            youtube_resolver_cache_sec=min(
                3600.0,
                max(0.0, float(os.getenv("YOUTUBE_RESOLVER_CACHE_SEC", "90"))),
            ),
            youtube_cookies_file=(os.getenv("YOUTUBE_COOKIES_FILE") or "").strip()
            or None,
            media_retention_days=int(os.getenv("MEDIA_RETENTION_DAYS", "30")),
            latitude=min(
                90.0, max(-90.0, float(os.getenv("LATITUDE", "-23.5505")))
            ),
            longitude=min(
                180.0, max(-180.0, float(os.getenv("LONGITUDE", "-46.6333")))
            ),
            weather_cache_minutes=max(
                5, int(os.getenv("WEATHER_CACHE_MINUTES", "30"))
            ),
            timelapse_enabled=os.getenv("TIMELAPSE_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            timelapse_speed=min(
                60.0, max(1.0, float(os.getenv("TIMELAPSE_SPEED", "8.0")))
            ),
            timelapse_hour=min(23, max(0, int(os.getenv("TIMELAPSE_HOUR", "23")))),
            timelapse_minute=min(
                59, max(0, int(os.getenv("TIMELAPSE_MINUTE", "55")))
            ),
            timelapse_backfill_days=min(
                90, max(0, int(os.getenv("TIMELAPSE_BACKFILL_DAYS", "7")))
            ),
            night_vision_mode=os.getenv("NIGHT_VISION_MODE", "auto"),
            night_vision_threshold=min(
                255.0, max(0.0, float(os.getenv("NIGHT_VISION_THRESHOLD", "60")))
            ),
            night_vision_clahe_clip=min(
                8.0, max(1.0, float(os.getenv("NIGHT_VISION_CLAHE_CLIP", "2.5")))
            ),
            night_vision_clahe_grid=min(
                16, max(2, int(os.getenv("NIGHT_VISION_CLAHE_GRID", "8")))
            ),
            night_vision_denoise=os.getenv("NIGHT_VISION_DENOISE", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off"},
            night_fauna_enabled=os.getenv("NIGHT_FAUNA_ENABLED", "false")
            .strip()
            .lower()
            in {"1", "true", "yes", "on", "sim"},
            night_fauna_class_ids=os.getenv("NIGHT_FAUNA_CLASS_IDS", "15,16"),
            offline_yolo_confidence=min(
                1.0,
                max(0.05, float(os.getenv("OFFLINE_YOLO_CONFIDENCE", "0.25"))),
            ),
            offline_frame_stride=min(
                10, max(1, int(os.getenv("OFFLINE_FRAME_STRIDE", "2")))
            ),
            offline_max_clips=min(
                100, max(0, int(os.getenv("OFFLINE_MAX_CLIPS", "12")))
            ),
            offline_clip_seconds=min(
                20.0, max(1.0, float(os.getenv("OFFLINE_CLIP_SECONDS", "4.0")))
            ),
            best_frame_enabled=os.getenv("BEST_FRAME_ENABLED", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            best_frame_ideal_area_ratio=min(
                1.0,
                max(
                    0.001,
                    float(os.getenv("BEST_FRAME_IDEAL_AREA_RATIO", "0.08")),
                ),
            ),
            best_frame_sharpness_scale=max(
                1.0, float(os.getenv("BEST_FRAME_SHARPNESS_SCALE", "120"))
            ),
            best_frame_min_sharpness=max(
                0.0, float(os.getenv("BEST_FRAME_MIN_SHARPNESS", "20"))
            ),
            enhancement_enabled=os.getenv("ENHANCEMENT_ENABLED", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            clip_overlay_enabled=os.getenv("CLIP_OVERLAY_ENABLED", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            enhancement_clahe_clip=min(
                8.0, max(1.0, float(os.getenv("ENHANCEMENT_CLAHE_CLIP", "2.0")))
            ),
            enhancement_clahe_grid=min(
                16, max(2, int(os.getenv("ENHANCEMENT_CLAHE_GRID", "8")))
            ),
            enhancement_denoise=os.getenv("ENHANCEMENT_DENOISE", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            enhancement_denoise_strength=min(
                20.0,
                max(
                    0.0,
                    float(os.getenv("ENHANCEMENT_DENOISE_STRENGTH", "5.0")),
                ),
            ),
            enhancement_max_width=min(
                4096, max(320, int(os.getenv("ENHANCEMENT_MAX_WIDTH", "1280")))
            ),
            enhancement_min_width=min(
                4096, max(0, int(os.getenv("ENHANCEMENT_MIN_WIDTH", "720")))
            ),
            enhancement_jpeg_quality=min(
                100, max(50, int(os.getenv("ENHANCEMENT_JPEG_QUALITY", "95")))
            ),
            smart_crop_margin=min(
                2.0, max(0.0, float(os.getenv("SMART_CROP_MARGIN", "0.25")))
            ),
            smart_crop_min_dimension=min(
                4096,
                max(0, int(os.getenv("SMART_CROP_MIN_DIMENSION", "640"))),
            ),
            smart_crop_max_dimension=min(
                4096,
                max(64, int(os.getenv("SMART_CROP_MAX_DIMENSION", "1024"))),
            ),
            adaptive_context_enabled=os.getenv("ADAPTIVE_CONTEXT_ENABLED", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            behavior_require_feeding=os.getenv("BEHAVIOR_REQUIRE_FEEDING", "false")
            .strip()
            .lower()
            in {"1", "true", "yes", "on", "sim"},
            anomaly_log_enabled=os.getenv("ANOMALY_LOG_ENABLED", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            anomaly_species_gap_days=min(
                3650, max(1, int(os.getenv("ANOMALY_SPECIES_GAP_DAYS", "180")))
            ),
            anomaly_cooldown_days=min(
                3650, max(1, int(os.getenv("ANOMALY_COOLDOWN_DAYS", "30")))
            ),
            ai_insights_enabled=os.getenv("AI_INSIGHTS_ENABLED", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            ai_cognitive_log_capacity=min(
                5000, max(50, int(os.getenv("AI_COGNITIVE_LOG_CAPACITY", "400")))
            ),
            rare_moments_enabled=os.getenv("RARE_MOMENTS_ENABLED", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            rare_moments_scan_hours=min(
                48.0,
                max(1.0, float(os.getenv("RARE_MOMENTS_SCAN_HOURS", "6"))),
            ),
            rare_moments_days=min(
                90, max(1, int(os.getenv("RARE_MOMENTS_DAYS", "7")))
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.ensure_directories()
    return settings
