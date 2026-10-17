"""Tradutor inteligente de links de stream (YouTube Live → stream direto).

O OpenCV/FFmpeg **não** consegue abrir a página web do YouTube. Este módulo usa o
``yt-dlp`` para extrair a URL de mídia direta (preferindo o manifesto **HLS/m3u8**)
de uma live, que então é entregue ao ``cv2.VideoCapture``.

Recursos:

- **Cache curto** do link direto (evita re-extrair a cada tentativa de reconexão).
- **Re-extração forçada** quando o stream cai — o YouTube renova o token de acesso
  com o tempo e o link antigo deixa de valer.
- **Tolerância a falhas**: nunca levanta exceção para o worker; em caso de erro
  devolve o último link conhecido ou a própria URL original.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from urllib.parse import urlparse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Domínios reconhecidos como YouTube (inclui subdomínios e o encurtador youtu.be).
_YOUTUBE_HOSTS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
)

# Cache em memória: {url_original: (url_direta, expira_em_epoch)}.
_cache: dict[str, tuple[str, float]] = {}
_cache_lock = threading.Lock()

# Opções do yt-dlp otimizadas para LIVE (sem download, junta no "ao vivo").
#
# ATENÇÃO ao seletor de formato: uma live do YouTube normalmente **não** expõe
# um formato combinado (áudio+vídeo) — só renditions separadas em HLS (m3u8).
# Por isso ``best[...]`` sozinho falha com "Requested format is not available".
# A cadeia abaixo prefere, nesta ordem:
#   1. formato combinado em HLS (tem áudio);
#   2. a melhor faixa de VÍDEO em HLS — caso típico de live (basta para o
#      Alaris Core, que analisa imagem);
#   3. a melhor faixa de vídeo disponível (fallback para vídeos comuns).
_YDL_BASE_OPTS: dict = {
    "format": "best[protocol^=m3u8]/bestvideo[protocol^=m3u8]/bestvideo/best",
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "retries": 3,
    "fragment_retries": 3,
    "socket_timeout": 15,
}

# Clientes alternativos do YouTube. O cliente "android" costuma escapar do
# bloqueio anti-bot ("Sign in to confirm you're not a bot") que atinge alguns
# vídeos/lives. Usado apenas como segunda tentativa (fallback).
_YDL_FALLBACK_CLIENTS = ["android"]


def _montar_opts(player_client: list[str] | None = None) -> dict:
    """Monta as opções do yt-dlp, incluindo cookies e o cliente de player.

    - Se ``YOUTUBE_COOKIES_FILE`` apontar para um arquivo existente, ele é usado
      para autenticar (útil em lives restritas/age-restricted).
    - ``player_client`` permite trocar o cliente do YouTube (fallback anti-bot).
    """
    opts = dict(_YDL_BASE_OPTS)
    cookies = getattr(get_settings(), "youtube_cookies_file", None)
    if cookies and os.path.isfile(cookies):
        opts["cookiefile"] = cookies
    if player_client:
        opts["extractor_args"] = {"youtube": {"player_client": list(player_client)}}
    return opts


def is_youtube_url(url: str | None) -> bool:
    """Informa se a URL é de uma live/vídeo do YouTube."""
    if not url:
        return False
    try:
        host = (urlparse(str(url).strip()).hostname or "").lower()
    except Exception:
        return False
    return any(host == base or host.endswith("." + base) for base in _YOUTUBE_HOSTS)


def _extrair_url_da_info(info: dict) -> str | None:
    """Extrai a melhor URL de mídia de um dicionário de formato do yt-dlp.

    - Seleção com vídeo+áudio separados → usa a faixa de **vídeo** (é o que o
      OpenCV precisa; ``info['url']`` fica ``None`` nesse caso).
    - Caso contrário → usa ``url`` (mídia direta) ou ``manifest_url`` (HLS).
    """
    formatos = info.get("requested_formats")
    if formatos:
        com_video = [
            f for f in formatos if f and f.get("vcodec") not in (None, "none")
        ]
        escolhido = (com_video or [f for f in formatos if f])[0]
        return escolhido.get("url") or escolhido.get("manifest_url")
    return info.get("url") or info.get("manifest_url")


def get_direct_youtube_stream(youtube_url: str) -> str | None:
    """Extrai o link de stream direto (m3u8/URL de mídia crua) de uma live.

    Tenta primeiro os clientes padrão do yt-dlp e, se falhar (ex.: bloqueio
    anti-bot), repete com o cliente ``android``. Retorna ``None`` em caso de
    falha definitiva (link inválido, sem rede, ``yt-dlp`` ausente, transmissão
    encerrada etc.). **Nunca** levanta exceção.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error(
            "yt-dlp não está instalado — links do YouTube não podem ser resolvidos. "
            "Instale com: pip install yt-dlp"
        )
        return None

    # Passada 1: clientes padrão. Passada 2: cliente "android" (contorna o
    # bloqueio anti-bot que atinge alguns vídeos/lives).
    for player_client in (None, _YDL_FALLBACK_CLIENTS):
        try:
            with yt_dlp.YoutubeDL(_montar_opts(player_client)) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
        except Exception as exc:
            logger.debug(
                "yt-dlp falhou (player_client=%s): %s", player_client, exc
            )
            continue

        if not info:
            continue

        # Playlists/canais: usa o primeiro item disponível.
        if "entries" in info:
            itens = [item for item in (info.get("entries") or []) if item]
            if not itens:
                continue
            info = itens[0]

        url_direta = _extrair_url_da_info(info)
        if url_direta:
            if player_client:
                logger.info(
                    "YouTube resolvido com player_client=%s (fallback anti-bot).",
                    player_client,
                )
            return url_direta

    logger.warning("Falha ao extrair o stream do YouTube: %s", youtube_url)
    return None


def resolver_url_direta(url: str, *, forcar: bool = False) -> str:
    """Devolve uma URL pronta para o ``cv2.VideoCapture``.

    - Links do **YouTube** são traduzidos para o stream direto (com cache curto).
    - Qualquer outra URL (RTSP/HTTP/HLS) é devolvida exatamente como veio.

    ``forcar=True`` ignora o cache — usado na **reconexão**, quando o token da
    live pode ter expirado e é preciso re-extrair um link novo.
    """
    if not is_youtube_url(url):
        return url

    settings = get_settings()
    if not settings.youtube_resolver_enabled:
        return url

    agora = time.time()
    if not forcar:
        with _cache_lock:
            cacheado = _cache.get(url)
            if cacheado and cacheado[1] > agora:
                return cacheado[0]

    direta = get_direct_youtube_stream(url)
    if not direta:
        # Falhou: reaproveita o último link conhecido (se houver) para não
        # derrubar o worker imediatamente; senão devolve a URL original.
        with _cache_lock:
            cacheado = _cache.get(url)
        if cacheado:
            return cacheado[0]
        return url

    ttl = float(settings.youtube_resolver_cache_sec)
    with _cache_lock:
        _cache[url] = (direta, agora + ttl)
    logger.info("YouTube Live traduzido para stream direto (cache %.0fs).", ttl)
    return direta


def limpar_cache() -> None:
    """Limpa o cache de links diretos (útil em testes/rotação de token)."""
    with _cache_lock:
        _cache.clear()
