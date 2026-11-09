from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/build_museum_index.py"
SPEC = importlib.util.spec_from_file_location("build_museum_index", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_museum_index_is_complete_and_current() -> None:
    entries = MODULE.read_entries()
    assert len(entries) >= 39
    assert len({entry.filename for entry in entries}) == len(entries)
    rendered = MODULE.render(entries)
    assert rendered == MODULE.OUTPUT.read_text(encoding="utf-8")
    assert MODULE.render_manifest(entries) == MODULE.MANIFEST.read_text(encoding="utf-8")
    for entry in entries:
        assert f"]({entry.filename})" in rendered


def test_recent_linux510_and_dual_radio_milestones_are_indexed() -> None:
    rendered = MODULE.render(MODULE.read_entries())
    assert "lyoko-first-native-linux510-squashfs.md" in rendered
    assert "lyoko-first-f276-dual-radio-physical-visibility.md" in rendered
    assert "lyoko-plans-before-touching-sector-5.md" in rendered
