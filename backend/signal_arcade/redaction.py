from __future__ import annotations

import re

_SECRET_QUERY = re.compile(r"(?i)(api[-_]?key|access[-_]?token|token|secret)=([^&\s\"']+)")
_BEARER = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,;]+)")
_KEYED_PROVIDER_PATH = re.compile(
    r"(?i)((?:https?|wss?)://[^/\s]+/(?:v1|v2|v3)/)([A-Za-z0-9._~-]{16,})"
)


def redact_secrets(value: object) -> str:
    """Remove common provider credentials before text reaches logs or incident history."""

    redacted = _SECRET_QUERY.sub(r"\1=<redacted>", str(value))
    redacted = _BEARER.sub(r"\1<redacted>", redacted)
    return _KEYED_PROVIDER_PATH.sub(r"\1<redacted>", redacted)
