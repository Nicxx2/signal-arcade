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
    entry = re.search(
        rf"^## {re.escape(__version__)} - (Unreleased|\d{{4}}-\d{{2}}-\d{{2}})$",
        changelog,
        re.MULTILINE,
    )
    assert entry is not None
    if entry[1] == "Unreleased":
        # Development checkouts must not advertise an unpublished installation image.
        assert f"v{__version__} — development candidate" in readme
        published = re.search(r"^## (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}$", changelog, re.MULTILINE)
        assert published is not None and published[1] != __version__
        install_version = published[1]
    else:
        install_version = __version__
    assert f"image: nicxx2/signal-arcade:{install_version}" in readme
