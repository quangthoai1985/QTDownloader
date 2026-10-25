"""Số phiên bản phải đồng bộ: qtdownloader.__version__ là nguồn duy nhất."""

import json
import os
import re

from qtdownloader import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_extension_manifest_matches():
    with open(os.path.join(ROOT, "extension", "manifest.json"), encoding="utf-8") as f:
        assert json.load(f)["version"] == __version__


def test_changelog_has_entry():
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        assert f"## [{__version__}]" in f.read()
