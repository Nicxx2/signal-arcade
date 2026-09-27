"""Short-lived, origin-bound credentials for browser notification handshakes only."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit

SESSION_SECONDS = 300


def _audience(url: str) -> str | None:
    """Normalize the effective request origin, never untrusted forwarding headers."""
    try:
        parsed = urlsplit(url)
        scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
        host = parsed.hostname
        if (
            scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        port = parsed.port if parsed.port is not None else (443 if scheme == "https" else 80)
    except ValueError:
        return None
    if ":" in host:
        host = f"[{host}]"
    return f"{scheme}://{host}:{port}"


class DashboardSessions:
    """No database/session registry; a restart invalidates all pending handshakes.

    The cookie is NOT an alternative to HTTP Basic auth for API requests. The
    notification endpoint must also require an explicit matching browser Origin.
    Expiry controls new handshakes; accepted sockets retain their existing lifetime.
    """

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)

    def cookie_name(self, target: str) -> str | None:
        audience = _audience(target)
        if audience is None:
            return None
        # Cookies have no port isolation. Separate names avoid tabs on different
        # app ports overwriting one another; the signature also binds the origin.
        suffix = hashlib.sha256(audience.encode()).hexdigest()[:16]
        return f"signal_arcade_ws_{suffix}"

    def issue(self, target: str) -> str | None:
        audience = _audience(target)
        if audience is None:
            return None
        expires = str(int(time.time()) + SESSION_SECONDS)
        signature = self._sign(audience, expires)
        return f"v1.{expires}.{signature}"

    def valid(self, token: str | None, target: str) -> bool:
        audience = _audience(target)
        if audience is None or not token or len(token) > 128 or not token.isascii():
            return False
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "v1":
            return False
        expires, signature = parts[1:]
        if not expires.isdecimal() or len(expires) > 12 or len(signature) != 64:
            return False
        deadline = int(expires)
        now = int(time.time())
        if str(deadline) != expires or not now < deadline <= now + SESSION_SECONDS:
            return False
        return hmac.compare_digest(signature, self._sign(audience, expires))

    def _sign(self, audience: str, expires: str) -> str:
        message = f"dashboard-notifications-v1\n{audience}\n{expires}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()
