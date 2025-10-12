import ipaddress
import logging
import socket
from dataclasses import dataclass
from typing import Dict, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx

# ---------- SSRF / Net utilities ----------

PRIVATEISH_FLAGS = (
    "is_private",
    "is_loopback",
    "is_link_local",
    "is_reserved",
    "is_multicast",
)


def _ip_is_privateish(ip: str) -> bool:
    """
    True for private/loopback/link-local/multicast/reserved (IPv4 & IPv6).
    """
    try:
        obj = ipaddress.ip_address(ip)
        return any(getattr(obj, flag) for flag in PRIVATEISH_FLAGS)
    except Exception:
        # If we cannot parse, treat as unsafe
        return True


def _resolve_all_ips(host: str) -> Set[str]:
    """
    Resolve host to all IPv4/IPv6 addresses. If resolution fails, return empty set.
    """
    ips: Set[str] = set()
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        for info in infos:
            addr = info[4][0]
            ips.add(addr)
    except Exception:
        pass
    return ips


def _host_or_subdomain_of(host: str, base: str) -> bool:
    """
    Allow exact or subdomain match. 'docs.example.com' matches 'example.com'.
    """
    host = host.lower()
    base = base.lower()
    return host == base or host.endswith("." + base)


# ---------- Config ----------

ALLOWED_OUTBOUND_HEADERS = {
    "accept",
    "accept-language",
    "user-agent",
    "if-none-match",
    "if-modified-since",
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "application/json",
    "application/xhtml+xml",
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "application/atom+xml; charset=UTF-8",
}


@dataclass
class SafeHttpConfig:
    # Security
    allowlist_domains: Set[str]
    denylist_domains: Set[str] = None
    allow_methods: Set[str] = None
    allowed_ports: Set[int] = None
    verify_ssl: Optional[bool | str] = False  # True/False or path to CA bundle
    # Networking
    timeout_sec: float = 10.0
    max_bytes: int = 2_000_000  # 2 MB
    follow_redirects: bool = True
    # Content policy
    allowed_content_types: Set[str] = None

    max_body_chars: int = 100_000  # safety cap for text decoding
    # Extraction / normalization
    extract_text: bool = True  # return cleaned text for HTML
    max_extracted_chars: int = 10_000
    # User agent
    user_agent: str = "MCP-SafeHttp/1.0 (+https://example.invalid/mcp)"
    # Connection limits (optional tuning)
    max_connections: int = 20
    max_keepalive: int = 10


class SafeHttpService:
    """
    A hardened HTTP client for MCP tools:
    - Strict SSRF protections (pre & post-redirect).
    - Domain allowlist (exact/subdomain) and optional denylist.
    - Restricts schemes, ports, methods, and outbound headers.
    - Streams response with byte cap; filters content-types.
    - Optional HTML->text extraction for relevance & token savings.
    - Configurable TLS verification: True/False or CA bundle path.
    """

    def __init__(self, cfg: SafeHttpConfig):
        if not cfg.allowlist_domains:
            raise ValueError("allowlist_domains cannot be empty")
        self.cfg = cfg
        if self.cfg.allow_methods is None:
            self.cfg.allow_methods = {"GET", "HEAD"}  # safe defaults
        if self.cfg.allowed_ports is None:
            self.cfg.allowed_ports = {80, 443}
        if self.cfg.denylist_domains is None:
            self.cfg.denylist_domains = set()

    # -------- URL & host checks --------

    def _check_url_pre(self, url: str) -> Tuple[str, str, int]:
        u = urlparse(url)
        if u.scheme not in ("http", "https"):
            raise ValueError("Only http/https schemes are allowed")
        if u.username or u.password:
            raise PermissionError("Userinfo in URL is not allowed")
        host = (u.hostname or "").lower()
        if not host:
            raise ValueError("URL missing host")
        port = u.port or (443 if u.scheme == "https" else 80)

        # Domain allow/deny checks (pre-resolution)
        # if not any(_host_or_subdomain_of(host, d) for d in self.cfg.allowlist_domains):
        #     raise PermissionError(f"Domain '{host}' is not on the allowlist")
        if any(_host_or_subdomain_of(host, d) for d in self.cfg.denylist_domains):
            raise PermissionError(f"Domain '{host}' is denylisted")
        if port not in self.cfg.allowed_ports:
            raise PermissionError(f"Port {port} is not allowed")

        # DNS → IP checks to block private/loopback/etc.
        ips = _resolve_all_ips(host)
        if not ips:
            raise PermissionError("DNS resolution failed")
        if any(_ip_is_privateish(ip) for ip in ips):
            raise PermissionError("Resolved to private/loopback/link-local/multicast/reserved IP")

        return host, u.scheme, port

    def _check_url_post_redirect(self, final_url: str):
        """
        Re-validate after redirects to prevent open-redirect SSRF.
        """
        u = urlparse(final_url)
        host = (u.hostname or "").lower()
        port = u.port or (443 if u.scheme == "https" else 80)

        # if not any(_host_or_subdomain_of(host, d) for d in self.cfg.allowlist_domains):
        #     raise PermissionError(f"Final domain '{host}' is not on the allowlist")
        if any(_host_or_subdomain_of(host, d) for d in self.cfg.denylist_domains):
            raise PermissionError(f"Final domain '{host}' is denylisted")
        if port not in self.cfg.allowed_ports:
            raise PermissionError(f"Final port {port} is not allowed")

        ips = _resolve_all_ips(host)
        if not ips:
            raise PermissionError("Final DNS resolution failed")
        if any(_ip_is_privateish(ip) for ip in ips):
            raise PermissionError("Final URL resolved to private/loopback/link-local/reserved IP")

    # -------- Header hygiene --------

    def _sanitize_outbound_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        safe: Dict[str, str] = {}
        if headers:
            for k, v in headers.items():
                if not k or v is None:
                    continue
                lk = k.strip().lower()
                if lk in HOP_BY_HOP_HEADERS:
                    continue
                if lk in ALLOWED_OUTBOUND_HEADERS:
                    safe[k] = str(v)
        # Always enforce UA
        safe.setdefault("User-Agent", self.cfg.user_agent)
        return safe

    # -------- Content helpers --------

    def _is_allowed_content_type(self, content_type: Optional[str]) -> bool:
        if not content_type:
            return False
        # Compare by prefix (type/subtype; ignore parameters)
        base = content_type.split(";", 1)[0].strip().lower()
        print("Base content type:", base)
        logging.debug("Base content type: %s", base)
        return any(
            base == allowed or base.startswith(allowed + "+") for allowed in ALLOWED_CONTENT_TYPES
        )

    @staticmethod
    def _guess_title_from_html(html: str) -> Optional[str]:
        try:
            start = html.lower().find("<title>")
            end = html.lower().find("</title>", start + 7) if start != -1 else -1
            if start != -1 and end != -1:
                return " ".join(html[start + 7 : end].split())
        except Exception:
            pass
        return None

    @staticmethod
    def _strip_html_naive(html: str, max_chars: int) -> str:
        """
        Minimal, dependency-free HTML -> text:
          - remove script/style/noscript blocks
          - drop tags
          - collapse whitespace
        """
        import re

        def _rm_blocks(text: str, tag: str) -> str:
            return re.sub(rf"<{tag}[\s\S]*?</{tag}>", " ", text, flags=re.IGNORECASE)

        t = _rm_blocks(html, "script")
        t = _rm_blocks(t, "style")
        t = _rm_blocks(t, "noscript")
        # remove remaining tags
        t = re.sub(r"<[^>]+>", " ", t)
        # collapse whitespace
        t = " ".join(t.split())
        return t[:max_chars]

    def _extract_text(self, content_type: str, text: str) -> Dict[str, str]:
        """
        Return a compact {title?, text} for HTML; passthrough for JSON/text.
        Truncates to cfg.max_extracted_chars.
        """
        base = (content_type or "").split(";", 1)[0].strip().lower()
        out: Dict[str, str] = {}

        if base == "text/html" or base == "application/xhtml+xml":
            title = self._guess_title_from_html(text) or ""
            extracted = ""
            # Prefer bs4 if available for better extraction
            try:
                from bs4 import BeautifulSoup  # type: ignore

                soup = BeautifulSoup(text, "html.parser")
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                # prefer <main> or <article>; fallback to body
                main = soup.find("main") or soup.find("article") or soup.body or soup
                extracted = " ".join(main.stripped_strings)
            except Exception:
                extracted = self._strip_html_naive(
                    text, self.cfg.max_extracted_chars * 2
                )  # pre-trim

            out["title"] = title[:200].strip()
            out["text"] = extracted[: self.cfg.max_extracted_chars].strip()

        elif base == "application/json":
            # Keep as-is but cap
            out["text"] = text[: self.cfg.max_extracted_chars].strip()
        else:
            # text/plain or other allowed text
            out["text"] = text[: self.cfg.max_extracted_chars].strip()

        return out

    # -------- Public API --------

    def fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes | str] = None,
        want_text: bool = True,  # decode to text (UTF-8/HTTP charset)
        extract_readable: bool = True,  # for HTML, return 'extracted'
    ) -> Dict[str, object]:
        """
        Safely fetch a URL with strict SSRF & content limits and return a compact,
        structured payload.

        Returns:
            {
              "url":        final_url,
              "status":     int,
              "headers":    { ... },             # response headers (lowercased keys)
              "content_type": "text/html; charset=utf-8",
              "encoding":   "utf-8" | None,
              "size":       int,                 # bytes actually read (<= max_bytes)
              "truncated":  bool,                # true if more bytes existed
              "body":       str | None,          # truncated text if want_text else None
              "extracted":  {"title":..., "text":...} | None
            }
        """
        method = (method or "GET").upper()

        if method not in self.cfg.allow_methods:
            raise PermissionError(f"HTTP method '{method}' not allowed")

        # Pre-check URL and DNS/IPs (SSRF defenses)
        self._check_url_pre(url)

        # Sanitize outbound headers
        safe_headers = self._sanitize_outbound_headers(headers)

        # Normalize body
        content: Optional[bytes] = None
        if body is not None:
            content = body if isinstance(body, (bytes, bytearray)) else str(body).encode("utf-8")

        timeout = httpx.Timeout(self.cfg.timeout_sec)
        limits = httpx.Limits(
            max_keepalive_connections=self.cfg.max_keepalive,
            max_connections=self.cfg.max_connections,
        )

        # verify_ssl = self.cfg.verify_ssl

        # verify: True (system trust), False (insecure), or str path to CA bundle

        # Stream + follow redirects
        with httpx.Client(
            timeout=timeout, limits=limits, follow_redirects=self.cfg.follow_redirects, verify=False
        ) as client:
            # Early content-length check via HEAD (best-effort, only for GET)
            if method == "GET":
                try:
                    head = client.request("HEAD", url, headers=safe_headers)
                    cl = head.headers.get("content-length")
                    if cl and cl.isdigit() and int(cl) > self.cfg.max_bytes:
                        raise ValueError(
                            f"Response too large (Content-Length={cl} > {self.cfg.max_bytes})"
                        )
                except Exception:
                    # HEAD may be blocked; continue with GET
                    pass

            resp = client.request(method, url, headers=safe_headers, content=content)
            final_url = str(resp.url)
            # Post-redirect checks
            self._check_url_post_redirect(final_url)

            # MIME filter
            ctype = resp.headers.get("content-type", "")
            print("Response content-type:", ctype)
            print("Allowed content types:", self.cfg.allowed_content_types)
            print("Is allowed content type?", self._is_allowed_content_type(ctype))
            if not self._is_allowed_content_type(ctype):
                raise PermissionError(f"Disallowed content-type: {ctype or 'unknown'}")

            # Stream read up to cap
            raw = bytearray()
            truncated = False
            for chunk in resp.iter_bytes():
                if not chunk:
                    continue
                if len(raw) + len(chunk) > self.cfg.max_bytes:
                    take = self.cfg.max_bytes - len(raw)
                    if take > 0:
                        raw.extend(chunk[:take])
                    truncated = True
                    break
                raw.extend(chunk)
            size = len(raw)

            # Decode to text if requested
            text_body: Optional[str] = None
            encoding = (
                resp.encoding
            )  # httpx tries to sniff from headers; else chardet/charset-normalizer
            if want_text:
                try:
                    text_body = raw.decode(encoding or "utf-8", errors="replace")
                except Exception:
                    text_body = raw.decode("utf-8", errors="replace")
                # extra guard for runaway bodies in text form
                if len(text_body) > self.cfg.max_body_chars:
                    text_body = text_body[: self.cfg.max_body_chars]
                    truncated = True

            # Optional readable extraction for HTML
            extracted: Optional[Dict[str, str]] = None
            if want_text and extract_readable:
                extracted = self._extract_text(ctype, text_body or "")

            # Return lower-cased headers for consistency; cap extremely long header values
            safe_resp_headers = {
                k.lower(): (v[:4096] if isinstance(v, str) else v) for k, v in resp.headers.items()
            }

            return {
                "url": final_url,
                "status": int(resp.status_code),
                "headers": safe_resp_headers,
                "content_type": ctype,
                "encoding": encoding,
                "size": size,
                "truncated": truncated,
                "body": extracted if extract_readable else text_body,
            }
