from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-6.6.0-f298-capability-truth"
OVERLAY = FOUNDATION / "overlay"


def test_capability_registry_uses_current_evidence_and_one_mode() -> None:
    registry = json.loads((OVERLAY / "etc/lyoko/capabilities.json").read_text(encoding="utf-8"))
    items = {item["id"]: item for item in registry["items"]}
    assert registry["source"] == "lyoko-f298-evidence-registry"
    assert all(item["mode"] == "developer" for item in items.values())
    assert all(item.get("title") and item.get("description") for item in items.values())
    assert "F290/F292" in items["wifi.2g.ap"]["evidence"]
    assert "F290/F292" in items["wifi.5g.ap"]["evidence"]
    assert "F292 físico" in items["packages.volatile_install"]["evidence"]
    assert items["packages.volatile_install"]["state"] == "available"
    assert items["network.vlan"]["state"] == "blocked"
    assert "F297" in items["network.igmp"]["evidence"]
    assert "F295" in items["storage.protection"]["evidence"]
    assert items["recovery.linux5"]["state"] == "certification_required"


def test_capability_ui_prefers_human_labels_and_keeps_ids() -> None:
    js = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    css = (OVERLAY / "www/capabilities.css").read_text(encoding="utf-8")
    assert "item.title || item.id" in js
    assert "item.description" in js
    assert "capability-id" in js
    assert "capability-evidence" in js
    assert ".capability-id" in css
    assert ".capability-evidence" in css
    syntax = subprocess.run(
        ["node", "--check", str(OVERLAY / "www/app.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr
