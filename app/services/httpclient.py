# app/services/httpclient.py
import ipaddress
import socket
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx


def _host_resolves_to_private(host: str) -> bool:
    """
    Resolve host and deny private/loopback/link-local/reserved IPs (SSRF guard).
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        ips = {info[4][0] for info in infos}
        for addr in ips:
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        return False
    except Exception:
        # On resolution failure, deny
        return True


class SafeHttpService:
    """
    Minimal but safe HTTP client for MCP tools:
    - Allowlist of domains (exact or subdomain).
    - Deny private/loopback/meta addresses.
    - Enforce timeouts and response size caps.
    """

    def __init__(self, allowlist_domains: set[str], timeout_sec: float = 10.0, 
                 max_bytes: int = 2_000_000):
        self.allowlist = {d.lower() for d in allowlist_domains}
        self.timeout = timeout_sec
        self.max_bytes = max_bytes

    def _check_url(self, url: str):
        u = urlparse(url)
        if u.scheme not in ("http", "https"):
            raise ValueError("Only http/https allowed")
        host = (u.hostname or "").lower()
        if not host:
            raise ValueError("URL missing host")

        # Allow exact or subdomain match
        if not any(host == d or host.endswith("." + d) for d in self.allowlist):
            raise PermissionError("Domain not allowlisted")

        # DNS to private networks not allowed
        if _host_resolves_to_private(host):
            raise PermissionError("Private/loopback addresses not allowed")

    def fetch(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, 
              body: Optional[str] = None):
        self._check_url(url)
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.request(method.upper(), url, headers=headers, content=body)
            # Cap size to protect memory; decode as UTF-8 replacement
            content = resp.content[: self.max_bytes]
            return {
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "body": content.decode("utf-8", "replace"),
            }
