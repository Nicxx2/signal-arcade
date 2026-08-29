from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from signal_arcade import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_versions_stay_aligned() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    web_package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    versions = {
        __version__,
        pyproject["project"]["version"],
        root_package["version"],
        web_package["version"],
    }
    assert versions == {__version__}
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert f"ARG SIGNAL_ARCADE_VERSION={__version__}" in dockerfile
    assert f"nicxx2/signal-arcade:{__version__}" in readme
    assert re.search(
        rf"^## {re.escape(__version__)} - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.MULTILINE
    )
