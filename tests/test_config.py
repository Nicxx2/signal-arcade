from __future__ import annotations

import pytest
from pydantic import ValidationError
from signal_arcade.config import Settings


def test_localhost_is_safe_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.bind == "127.0.0.1"
    assert settings.admin_password is None


def test_non_loopback_requires_password() -> None:
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        Settings(bind="0.0.0.0", _env_file=None)


def test_non_loopback_with_password_is_allowed() -> None:
    settings = Settings(bind="0.0.0.0", admin_password="test-only", _env_file=None)
    assert settings.bind == "0.0.0.0"
