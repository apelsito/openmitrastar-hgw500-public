from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_master_web_deliverables_exist() -> None:
    for name in (
        "LYOKO_INFORMATION_ARCHITECTURE.md",
        "LYOKO_OEM_FEATURE_MAP.json",
        "LYOKO_DESIGN_SYSTEM.md",
        "LYOKO_API_GAP.md",
    ):
        assert (DOCS / name).is_file()


def test_oem_feature_map_is_complete_and_closed() -> None:
    payload = json.loads((DOCS / "LYOKO_OEM_FEATURE_MAP.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "lyoko.oem-feature-map/v1"
    assert [item["id"] for item in payload["items"]] == [f"OEM-{index:02d}" for index in range(1, 19)]
    assert {item["status"] for item in payload["items"]} <= set(payload["status_vocabulary"])
    assert all(item["endpoint"] and item["gate"] and item["risk"] for item in payload["items"])


def test_docs_preserve_security_boundaries() -> None:
    combined = "\n".join(
        (DOCS / name).read_text(encoding="utf-8")
        for name in ("LYOKO_INFORMATION_ARCHITECTURE.md", "LYOKO_DESIGN_SYSTEM.md", "LYOKO_API_GAP.md")
    )
    for marker in ("PSK", "mtd3", "mtd5", "rollback", "/api/v1/frontend"):
        assert marker in combined
