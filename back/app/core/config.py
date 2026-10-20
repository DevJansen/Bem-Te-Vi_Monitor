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
    # --- Inteligência Artificial Externa: Google Gemini (provedor único) ---
    # Chave da API do Google Gemini (AI Studio). O único provedor suportado.
    ai_external_api_key: str = ""
    # Modelo Gemini em uso. Valores aceitos: gemini-3.5-flash (padrão),
    # gemini-3.7-flash, gemini-3.8-flash e gemini-3.1-pro-preview. O prefixo
    # "models/" é removido automaticamente (sanitize_model_name) para evitar
    # HTTP 404, e modelos descontinuados pelo Google são substituídos
    # automaticamente pela cadeia de fallback do serviço de IA.
    ai_external_model: str = "gemini-3.5-flash"
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
    smart_crop_margin: float = Field(default=0.10, ge=0.0, le=2.0)
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
    # --- Aprendizado ativo / fine-tuning incremental do Bem-Ti-Vi Core ---
    # Quando ligado, correções manuais de espécie e confirmações de detecção
    # alimentam a fila de treinamento (recortes tratados por espécie).
    active_learning_enabled: bool = True
    # Quantidade mínima de amostras por espécie para a espécie entrar no
    # treinamento incremental (classes com menos amostras são ignoradas).
    active_learning_min_samples: int = Field(default=8, ge=2, le=500)
    # Modelo base de classificação do Ultralytics usado no fine-tuning.
    fine_tune_base_model: str = "yolov8n-cls.pt"
    # Épocas reduzidas: o objetivo é um ajuste leve, não um treino do zero.
    fine_tune_epochs: int = Field(default=8, ge=1, le=200)
    fine_tune_batch: int = Field(default=8, ge=1, le=128)
    fine_tune_imgsz: int = Field(default=224, ge=64, le=640)
    # Confiança mínima da classificação fina para substituir o rótulo genérico
    # "bird" no pipeline ao vivo.
    fine_tune_min_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    # --- Memória comportamental preditiva ---
    # Mantém perfis por espécie (horário, clima, umidade e sazonalidade) em
    # segundo plano. A previsão nunca bloqueia o painel: usa o último perfil.
    behavioral_memory_enabled: bool = True
    behavioral_refresh_minutes: int = Field(default=60, ge=5, le=1440)
    behavioral_history_days: int = Field(default=120, ge=7, le=3650)
    behavioral_prediction_hours: int = Field(default=2, ge=1, le=12)
    # --- Reidentificação individual (assinaturas visuais) ---
    # Extrai embeddings de recortes nítidos e compara com a galeria "Minhas
    # Aves" para reconhecer indivíduos recorrentes (Conhecido do Jardim).
    visual_embeddings_enabled: bool = True
    # Similaridade de cosseno mínima para considerar que é o mesmo indivíduo.
    individual_match_threshold: float = Field(default=0.86, ge=0.0, le=1.0)
    # Nitidez mínima (variância do Laplaciano) para gerar a assinatura visual.
    # Fotos desfocadas são ignoradas: gerariam assinaturas instáveis.
    individual_min_sharpness: float = Field(default=25.0, ge=0.0)
    # Quantidade máxima de indivíduos (centroides) comparados por espécie.
    individual_max_candidates: int = Field(default=250, ge=10, le=5000)
    # --- Resumo Matinal Automatizado (Morning Briefing) ---
    morning_briefing_enabled: bool = True
    morning_briefing_hour: int = Field(default=7, ge=0, le=23)
    morning_briefing_minute: int = Field(default=0, ge=0, le=59)
    # --- Rede global Bem-Ti-Vi (jardins conectados) ---
    # O feed local funciona mesmo sem pares: ele reúne os avistamentos raros das
    # câmeras deste jardim. Para receber avistamentos de outras instâncias, é
    # obrigatório definir um token compartilhado e liberar a rota de webhook.
    global_network_enabled: bool = True
    # Nome exibido como origem dos eventos locais no feed global.
    global_network_instance_name: str = "Meu Jardim"
    # Segredo compartilhado enviado no cabeçalho X-Bem-Te-Vi-Token. Vazio
    # desabilita o recebimento de webhooks (a rota responde 503).
    global_network_token: str = ""
    # Instâncias parceiras (URLs base separadas por vírgula). O envio é feito
    # para "{url}/api/network/webhook" em segundo plano, sem bloquear a captura.
    global_network_peers: str = ""
    # Quando verdadeiro, compartilha também avistamentos comuns. O padrão é
    # compartilhar apenas destaques (raros/incomuns) para evitar ruído.
    global_network_share_all: bool = False
    # Janela (dias) e limite do feed exibido no painel.
    global_network_feed_days: int = Field(default=7, ge=1, le=90)
    global_network_feed_limit: int = Field(default=20, ge=1, le=100)
    # Tempo máximo (segundos) de espera ao publicar em um par. Nunca bloqueia
    # a captura: a publicação roda em thread separada.
    global_network_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    # --- Escuta Noturna de Migração (NFC: Nocturnal Flight Calls) ---
    # Liga o modo de escuta noturna: durante o período configurado o limiar de
    # confiança do BirdNET é reduzido para captar os chamados curtos (*flight
    # calls*) de aves que cruzam o céu acima do jardim.
    nfc_monitor_enabled: bool = True
    # Início/fim da janela noturna em horário local.
    nfc_night_start_hour: int = Field(default=22, ge=0, le=23)
    nfc_night_end_hour: int = Field(default=5, ge=0, le=23)
    # Limiar reduzido aplicado dentro da janela noturna. Menor que o padrão para
    # captar chamados fracos; alto o bastante para evitar ruído como "ave".
    nfc_confidence_threshold: float = Field(default=0.45, ge=0.20, le=0.69)
    # Nota curta exibida no feed da aba de áudio para registros noturnos.
    nfc_note: str = "Chamado de voo (NFC)"

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
    def spectrograms_dir(self) -> Path:
        """Espectrogramas visuais dos cantos identificados pelo BirdNET.

        O PNG é gerado uma única vez por detecção e servido pela rota
        ``/api/audio-detections/{id}/spectrogram``. Fica fora de ``captures``
        para não ser confundido com a mídia original da visita.
        """
        return self.app_data_dir / "spectrograms"

    @property
    def reels_dir(self) -> Path:
        """Reels verticais (9:16) gerados para redes sociais.

        O MP4 é gerado uma única vez por visita e servido pela rota
        ``/api/media/reel/{visit_id}``.
        """
        return self.captures_dir / "reels"

    @property
    def reference_birds_dir(self) -> Path:
        return self.app_data_dir / "reference_birds"

    @property
    def secrets_dir(self) -> Path:
        return self.app_data_dir / "secrets"

    @property
    def training_queue_dir(self) -> Path:
        """Fila de amostras rotuladas para o fine-tuning incremental.

        Cada subpasta é uma espécie (nome seguro para o sistema de arquivos) e
        contém os recortes tratados confirmados pelo observador.
        """
        return self.app_data_dir / "training_queue"

    @property
    def fine_tune_dataset_dir(self) -> Path:
        """Dataset temporário (train/val) montado a partir da fila."""
        return self.app_data_dir / "fine_tune_dataset"

    @property
    def ai_models_dir(self) -> Path:
        """Modelos treinados localmente (ex.: classificação de espécies)."""
        return self.app_data_dir / "models"

    @property
    def fine_tuned_model_path(self) -> Path:
        """``best.pt`` do último fine-tuning concluído com sucesso."""
        return self.ai_models_dir / "bem_te_vi_core.pt"

    @property
    def fine_tuned_labels_path(self) -> Path:
        """Mapa ``classe do modelo`` → nome original da espécie (JSON)."""
        return self.ai_models_dir / "bem_te_vi_core.labels.json"

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
            self.reels_dir,
            self.spectrograms_dir,
            self.reference_birds_dir,
            self.secrets_dir,
            self.training_queue_dir,
            self.ai_models_dir,
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
            ai_external_api_key=(
                os.getenv("GEMINI_API_KEY", "")
                or os.getenv("AI_EXTERNAL_API_KEY", "")
            ).strip(),
            ai_external_model=os.getenv(
                "AI_EXTERNAL_MODEL", "gemini-3.5-flash"
            ).strip()
            or "gemini-3.5-flash",
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
                2.0, max(0.0, float(os.getenv("SMART_CROP_MARGIN", "0.10")))
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
            active_learning_enabled=os.getenv("ACTIVE_LEARNING_ENABLED", "true")
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            active_learning_min_samples=min(
                500, max(2, int(os.getenv("ACTIVE_LEARNING_MIN_SAMPLES", "8")))
            ),
            fine_tune_base_model=os.getenv(
                "FINE_TUNE_BASE_MODEL", "yolov8n-cls.pt"
            ).strip()
            or "yolov8n-cls.pt",
            fine_tune_epochs=min(
                200, max(1, int(os.getenv("FINE_TUNE_EPOCHS", "8")))
            ),
            fine_tune_batch=min(
                128, max(1, int(os.getenv("FINE_TUNE_BATCH", "8")))
            ),
            fine_tune_imgsz=min(
                640, max(64, int(os.getenv("FINE_TUNE_IMGSZ", "224")))
            ),
            fine_tune_min_confidence=min(
                1.0, max(0.0, float(os.getenv("FINE_TUNE_MIN_CONFIDENCE", "0.35")))
            ),
            behavioral_memory_enabled=os.getenv(
                "BEHAVIORAL_MEMORY_ENABLED", "true"
            )
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            behavioral_refresh_minutes=min(
                1440,
                max(5, int(os.getenv("BEHAVIORAL_REFRESH_MINUTES", "60"))),
            ),
            behavioral_history_days=min(
                3650, max(7, int(os.getenv("BEHAVIORAL_HISTORY_DAYS", "120")))
            ),
            behavioral_prediction_hours=min(
                12, max(1, int(os.getenv("BEHAVIORAL_PREDICTION_HOURS", "2")))
            ),
            visual_embeddings_enabled=os.getenv(
                "VISUAL_EMBEDDINGS_ENABLED", "true"
            )
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            individual_match_threshold=min(
                1.0,
                max(
                    0.0,
                    float(os.getenv("INDIVIDUAL_MATCH_THRESHOLD", "0.86")),
                ),
            ),
            individual_min_sharpness=max(
                0.0, float(os.getenv("INDIVIDUAL_MIN_SHARPNESS", "25"))
            ),
            individual_max_candidates=min(
                5000,
                max(10, int(os.getenv("INDIVIDUAL_MAX_CANDIDATES", "250"))),
            ),
            morning_briefing_enabled=os.getenv(
                "MORNING_BRIEFING_ENABLED", "true"
            )
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            morning_briefing_hour=min(
                23, max(0, int(os.getenv("MORNING_BRIEFING_HOUR", "7")))
            ),
            morning_briefing_minute=min(
                59, max(0, int(os.getenv("MORNING_BRIEFING_MINUTE", "0")))
            ),
            global_network_enabled=os.getenv(
                "GLOBAL_NETWORK_ENABLED", "true"
            )
            .strip()
            .lower()
            not in {"0", "false", "no", "off", "não", "nao"},
            global_network_instance_name=(
                os.getenv("GLOBAL_NETWORK_INSTANCE_NAME", "Meu Jardim").strip()
                or "Meu Jardim"
            )[:120],
            global_network_token=(os.getenv("GLOBAL_NETWORK_TOKEN", "") or "").strip(),
            global_network_peers=(os.getenv("GLOBAL_NETWORK_PEERS", "") or "").strip(),
            global_network_share_all=os.getenv(
                "GLOBAL_NETWORK_SHARE_ALL", "false"
            )
            .strip()
            .lower()
            in {"1", "true", "yes", "on", "sim"},
            global_network_feed_days=min(
                90, max(1, int(os.getenv("GLOBAL_NETWORK_FEED_DAYS", "7")))
            ),
            global_network_feed_limit=min(
                100, max(1, int(os.getenv("GLOBAL_NETWORK_FEED_LIMIT", "20")))
            ),
            global_network_timeout_seconds=min(
                30.0,
                max(
                    1.0,
                    float(os.getenv("GLOBAL_NETWORK_TIMEOUT_SECONDS", "5.0")),
                ),
            ),
            # --- Escuta Noturna de Migração (NFC: Nocturnal Flight Calls) ---
            # Liga o modo de escuta noturna: durante o período configurado o
            # limiar de confiança do BirdNET é reduzido para captar os chamados
            # curtos (*flight calls*) de aves que cruzam o céu acima do jardim.
            nfc_monitor_enabled=os.getenv("NFC_MONITOR_ENABLED", "true")
            .strip()
            .lower()
            in {"1", "true", "yes", "on", "sim"},
            # Início/fim da janela noturna em horário local. Aceita também a
            # notação de 24 h (ex.: 22 e 5 para 22:00-05:00).
            nfc_night_start_hour=min(23, max(0, int(os.getenv("NFC_NIGHT_START_HOUR", "22")))),
            nfc_night_end_hour=min(23, max(0, int(os.getenv("NFC_NIGHT_END_HOUR", "5")))),
            # Limiar reduzido aplicado dentro da janela noturna. Deve ser menor
            # que o limiar padrão para captar chamados fracos.
            nfc_confidence_threshold=min(
                0.69, max(0.20, float(os.getenv("NFC_CONFIDENCE_THRESHOLD", "0.45")))
            ),
            # Nota exibida no feed da aba de áudio para registros noturnos.
            nfc_note=os.getenv("NFC_NOTE", "Chamado de voo (NFC)").strip()[:160],
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.ensure_directories()
    return settings
