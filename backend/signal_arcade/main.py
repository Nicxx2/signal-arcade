from __future__ import annotations

import logging

import uvicorn

from .api import create_app
from .config import load_settings
from .redaction import redact_secrets


class _SecretRedactionFilter(logging.Filter):
    """Last-resort protection for credentials embedded in provider request URLs."""

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        redacted = redact_secrets(rendered)
        if redacted != rendered:
            record.msg = redacted
            record.args = ()
        return True


def run() -> None:
    settings = load_settings()
    handler = logging.StreamHandler()
    handler.addFilter(_SecretRedactionFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        handlers=[handler],
        force=True,
    )
    # HTTP clients include full request URLs in INFO logs. Provider URLs can contain API keys,
    # so keep routine transport messages below the configured application log threshold.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    uvicorn.run(
        create_app(settings),
        host=settings.bind,
        port=settings.port,
        access_log=settings.log_level == "DEBUG",
        # Keep the redaction filter and transport log levels above. Uvicorn's default
        # logging dictionary otherwise replaces application logging during startup.
        log_config=None,
    )


if __name__ == "__main__":
    run()
