"""Optional ONVIF helpers to resolve an RTSP URL from a device."""

from __future__ import annotations

import logging
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)


def build_rtsp_url(
    host_or_url: str,
    username: str | None = None,
    password: str | None = None,
    path: str = "/Streaming/Channels/101",
) -> str:
    """Build an RTSP URL, injecting credentials when provided."""
    raw = host_or_url.strip()
    if raw.lower().startswith("rtsp://"):
        parsed = urlparse(raw)
        if username and not parsed.username:
            user = quote(username, safe="")
            pwd = quote(password or "", safe="")
            netloc = f"{user}:{pwd}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return parsed._replace(netloc=netloc).geturl()
        return raw

    host = raw
    port = 554
    if "://" in host:
        host = host.split("://", 1)[1]
    if "/" in host:
        host, extra_path = host.split("/", 1)
        path = "/" + extra_path
    if ":" in host:
        host_part, port_part = host.rsplit(":", 1)
        if port_part.isdigit():
            host = host_part
            port = int(port_part)

    auth = ""
    if username:
        auth = f"{quote(username, safe='')}:{quote(password or '', safe='')}@"
    return f"rtsp://{auth}{host}:{port}{path}"


def resolve_onvif_rtsp(
    host: str,
    username: str | None,
    password: str | None,
    port: int = 80,
) -> str | None:
    """
    Try to discover the RTSP stream via ONVIF.
    Returns None if onvif-zeep is unavailable or discovery fails.
    Falls back is handled by the caller (build_rtsp_url).
    """
    try:
        from onvif import ONVIFCamera  # type: ignore
    except Exception:
        logger.info(
            "onvif-zeep not installed — using RTSP URL heuristic for %s", host
        )
        return None

    try:
        clean_host = host.strip()
        if "://" in clean_host:
            clean_host = clean_host.split("://", 1)[1]
        if "/" in clean_host:
            clean_host = clean_host.split("/", 1)[0]
        onvif_port = port
        if ":" in clean_host:
            h, p = clean_host.rsplit(":", 1)
            if p.isdigit():
                clean_host, onvif_port = h, int(p)

        camera = ONVIFCamera(
            clean_host,
            onvif_port,
            username or "",
            password or "",
        )
        media = camera.create_media_service()
        profiles = media.GetProfiles()
        if not profiles:
            return None
        token = profiles[0].token
        stream = media.GetStreamUri(
            {
                "StreamSetup": {
                    "Stream": "RTP-Unicast",
                    "Transport": {"Protocol": "RTSP"},
                },
                "ProfileToken": token,
            }
        )
        uri = getattr(stream, "Uri", None) or stream.get("Uri")
        if not uri:
            return None
        return build_rtsp_url(uri, username, password)
    except Exception:
        logger.exception("ONVIF discovery failed for host=%s", host)
        return None
