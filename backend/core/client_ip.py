"""The client's IP address, for per-IP throttling.

Checked in this order:
1. CF-Connecting-IP, then True-Client-IP: set by Cloudflare, which Render
   runs behind. Cloudflare overwrites these, so they can be trusted there; but
   anywhere else a client can send them itself, so they're only read when
   TRUST_CDN_IP_HEADERS is on.
2. X-Forwarded-For, counting NUM_PROXIES entries from the right: each proxy
   appends the address it received from, so the entries a client adds itself
   sit further left and are ignored.
3. REMOTE_ADDR (the socket peer): local development, NUM_PROXIES = 0.
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Mapping
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

CDN_HEADERS = (("HTTP_CF_CONNECTING_IP", "cf-connecting-ip"), ("HTTP_TRUE_CLIENT_IP", "true-client-ip"))


def _valid(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return None
    return value


def client_ip(meta: Mapping[str, Any]) -> tuple[str, str]:
    """(ip, source) for a request's META. Source names the header used."""
    if settings.TRUST_CDN_IP_HEADERS:
        for key, source in CDN_HEADERS:
            ip = _valid(meta.get(key))
            if ip:
                return ip, source

    num_proxies = settings.REST_FRAMEWORK.get("NUM_PROXIES") or 0
    xff = meta.get("HTTP_X_FORWARDED_FOR")
    if num_proxies > 0 and xff:
        entries = [e.strip() for e in xff.split(",") if e.strip()]
        if entries:
            ip = _valid(entries[-min(num_proxies, len(entries))])
            if ip:
                return ip, "x-forwarded-for"

    return str(meta.get("REMOTE_ADDR") or ""), "remote-addr"


def client_ip_for(request) -> str:
    ip, source = client_ip(request.META)
    logger.debug("Client IP %s (from %s)", ip, source)
    return ip
