#!/usr/bin/env python3
"""Package the restored classic TSX presentation, never a flashable firmware."""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import tempfile
from lyoko_frontend_identity import BASE_FRONTEND_HASH, transform_spec

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/lyoko-web-next"
DIST = SOURCE / "dist"
CLASSIC = ROOT / "versions/lyoko-foundation-6.8.2-f314-qtn-nondfs-guard/overlay/usr/share/openmitrastar/web/dashboard.html"
CLASSIC_ENV = ROOT / "versions/lyoko-foundation-6.8.2-f314-qtn-nondfs-guard/overlay/etc/lyoko/frontend.env"
PROVENANCE = SOURCE / "reference/classic-provenance.json"
HASHED_ASSET = re.compile(r"^[A-Za-z0-9_-]+-[A-Za-z0-9_-]+\.(?:js|css)$")
BRANDING = {"movistar-logo.svg", "telefonica-logo.svg", "movistar-m.png"}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class EntryReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.inline_script = False
        self.script_open = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if any(key.startswith("on") for key in attrs): raise ValueError("inline event handlers are not permitted")
        if tag == "script":
            self.script_open = True
            if not attrs.get("src"): self.inline_script = True
        if tag in {"script", "link", "img"}:
            self.references.extend(value for key, value in attributes if key in {"src", "href"} and value)

    def handle_endtag(self, tag):
        if tag == "script": self.script_open = False

    def handle_data(self, data):
        if self.script_open and data.strip(): self.inline_script = True


def validate_dist(dist: Path = DIST) -> tuple[Path, list[Path], dict]:
    index = dist / "index.html"
    assets_dir = dist / "assets"
    if not index.is_file() or index.is_symlink() or not assets_dir.is_dir() or assets_dir.is_symlink():
        raise ValueError("build the classic TSX application before packaging")
    assets = sorted(assets_dir.iterdir())
    if any(not item.is_file() or item.is_symlink() for item in assets): raise ValueError("dist assets must be flat regular files")
    if {item.relative_to(dist).as_posix() for item in dist.rglob("*") if item.is_file()} != {"index.html", *("assets/" + item.name for item in assets)}:
        raise ValueError("unexpected dist files outside the asset catalogue")
    compiled = [item for item in assets if HASHED_ASSET.fullmatch(item.name)]
    media = [item for item in assets if item.name in BRANDING]
    if len(compiled) + len(media) != len(assets) or {item.name for item in media} != BRANDING:
        raise ValueError("unrecognized asset or missing original brand")
    if {item.suffix for item in compiled} != {".js", ".css"}: raise ValueError("missing JS/CSS bundle")

    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    if provenance["source_rootfs_sha256"] != "ee2c7a63ee738382ba8eaf813cfd725e64e52ce0686bfbf83129a78dcf323cce":
        raise ValueError("unrecognized classic rootfs provenance")
    if sha256(CLASSIC) != provenance["source_dashboard_sha256"]: raise ValueError("classic HTML source changed")
    sources = {row["path"]: row for row in provenance["files"]}
    for asset in media:
        expected = sources.get("public/assets/" + asset.name)
        if not expected or sha256(asset) != expected["sha256"] or asset.stat().st_size != expected["bytes"]:
            raise ValueError(f"original branding changed: {asset.name}")

    text = index.read_text(encoding="utf-8")
    parser = EntryReferences(); parser.feed(text)
    if parser.inline_script: raise ValueError("inline script in application entry")
    available = {item.name for item in assets}
    for reference in parser.references:
        if not reference.startswith("./assets/") or reference.removeprefix("./assets/") not in available:
            raise ValueError(f"entry references a missing or external asset: {reference}")
    if not any(reference.endswith(".js") for reference in parser.references) or not any(reference.endswith(".css") for reference in parser.references):
        raise ValueError("entry is missing its JS/CSS links")
    # The generated TSX must still contain both original brand references.
    for name in ("movistar-logo.svg", "telefonica-logo.svg"):
        if not any(name.encode() in item.read_bytes() for item in compiled if item.suffix == ".js"):
            raise ValueError(f"the active bundle does not render {name}")
    return index, assets, provenance


def bundle_identity(index: Path, assets: list[Path]) -> str:
    inputs = {"index": sha256(index), "assets": {item.name: sha256(item) for item in assets},
              "lock": sha256(SOURCE / "package-lock.json"), "layout": "classic-tsx-overlay-v4-dfs",
              "identity_transform": transform_spec(), "base_frontend_sha256": BASE_FRONTEND_HASH}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def default_package_dir() -> Path:
    index, assets, _ = validate_dist()
    return ROOT / "outputs/frontend" / ("lyoko-classic-tsx-" + bundle_identity(index, assets))


def prepare_payload() -> tuple[dict[str, bytes], dict]:
    index, assets, provenance = validate_dist()
    build_id = bundle_identity(index, assets)
    # Only build-time compression measurement; no network or device operation.
    check = subprocess.run(["node", "scripts/check-budgets.mjs"], cwd=SOURCE, capture_output=True, text=True, check=True)
    budget = json.loads(check.stdout)
    payload = {}
    html = index.read_text(encoding="utf-8")
    for asset in assets:
        public_path = ("assets/" if asset.name in BRANDING else "assets/lyoko-next/") + asset.name
        payload["www/" + public_path] = asset.read_bytes()
        html = html.replace("./assets/" + asset.name, "/" + public_path)
    payload["usr/share/openmitrastar/web/dashboard.html"] = html.encode("utf-8")
    active_assets = [{"path": path, "url": "/dashboard.cgi" if path.startswith("usr/") else "/" + path.removeprefix("www/"),
                      "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                     for path, data in sorted(payload.items())]
    bundle = {"schema": "lyoko.frontend.bundle/v1", "ui_version": "0.3.0-classic-dfs", "build_id": build_id,
              "source": "lyoko-classic-tsx-" + build_id, "entry": "/dashboard.cgi", "assets": active_assets,
              "asset_bytes": sum(row["bytes"] for row in active_assets), "legacy_assets_retained": True}
    payload["etc/lyoko/web-next.json"] = (json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if sha256(CLASSIC_ENV) != BASE_FRONTEND_HASH: raise ValueError("classic frontend identity source changed")
    identity = dict(line.split("=", 1) for line in CLASSIC_ENV.read_text(encoding="ascii").splitlines() if "=" in line)
    identity.update(LYOKO_UI_VERSION=bundle["ui_version"], LYOKO_UI_BUILD_ID=build_id, LYOKO_UI_SOURCE=bundle["source"],
                    LYOKO_UI_DASHBOARD_HTML_SHA256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                    LYOKO_UI_ASSET_BYTES=str(int(identity["LYOKO_UI_ASSET_BYTES"]) - CLASSIC.stat().st_size + len(html.encode("utf-8"))))
    payload["etc/lyoko/frontend.env"] = ("\n".join(f"{key}={value}" for key, value in identity.items()) + "\n").encode("ascii")
    payload["etc/lyoko/web-next.env"] = ("\n".join([
        "LYOKO_WEB_NEXT_VERSION=0.3.0-classic-dfs", f"LYOKO_WEB_NEXT_BUILD_ID={build_id}",
        "LYOKO_WEB_NEXT_ENTRY=/usr/share/openmitrastar/web/dashboard.html",
        "LYOKO_WEB_NEXT_ASSET_ROOT=/www/assets/lyoko-next", "LYOKO_WEB_NEXT_DEFAULT_THEME=classic",
        "LYOKO_WEB_NEXT_AUTH=existing-omsession-cgi", "LYOKO_WEB_NEXT_MUTATION_MODE=backend-gated-transactions",
        "LYOKO_WEB_NEXT_RELEASE_ELIGIBLE=0"]) + "\n").encode("ascii")
    records = [{"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "mode": "0644"}
               for path, data in sorted(payload.items())]
    manifest = {
        "schema": "openmitrastar.lyoko-web-next-overlay/v3", "build_id": build_id,
        "target": "HGW-500BNA-QCv2 A2 and board-profile adapters", "base_runtime": "F314 authenticated CGI and /api/v1 contract",
        "release_eligible": False, "flash_supported": False,
        "source": {"package_lock_sha256": sha256(SOURCE / "package-lock.json"), "classic_dashboard_sha256": sha256(CLASSIC),
                   "classic_provenance_sha256": sha256(PROVENANCE), "classic_dom_ids": len(provenance["dom_ids"]),
                   "base_frontend_sha256": BASE_FRONTEND_HASH},
        "integration": {"authenticated_entry_replaced": "/usr/share/openmitrastar/web/dashboard.html",
            "public_executable_cgi_added": False, "existing_session_cookie_reused": "OMSESSION", "api_origin": "same-origin /api/v1",
            "required_api": ["status", "firmware", "radios/2g", "radios/5g"], "optional_api": ["hardware", "optimization", "capabilities", "radios/5g/dfs"],
            "presentation": "original F314 Movistar/Telefonica", "controller": "legacy F314 plus incremental typed adapters",
            "branding_paths_preserved": True, "emulator_backend_packaged": False,
            "frontend_identity_sync": "frontend.env identifies active UI; authenticated API adds exact split bundle manifest",
            "legacy_asset_hashes": "retained fixed-path assets; bundle.assets identifies the active split assets"},
        "transforms": [transform_spec()],
        "deployment_blockers": ["this bundle's HTTP/TLS/browser session integration", "physical platform/radio regression", "DFS remains gated by independently accepted native radar firmware"],
        "safety": {"hardware_actions": False, "firmware_generated": False, "flash": False, "mtd_writes": False, "radio_mutation": False},
        "budgets": budget["budgets"], "files": records, "total_bytes": sum(row["bytes"] for row in records),
    }
    return payload, manifest


def package(output: Path | None = None) -> tuple[Path, dict, bool]:
    payload, manifest = prepare_payload()
    output = (output or ROOT / "outputs/frontend" / ("lyoko-classic-tsx-" + manifest["build_id"])).resolve()
    if output.exists():
        existing = json.loads((output / "manifest.json").read_text(encoding="ascii"))
        from lyoko_web_rootfs_worker import validate_overlay
        if existing != manifest: raise ValueError(f"refusing to overwrite a different package: {output}")
        validate_overlay(output / "overlay", existing)
        return output, manifest, True
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never remove a pre-existing sibling staging directory.
    with tempfile.TemporaryDirectory(prefix=".lyoko-package-", dir=output.parent) as temporary:
        stage = Path(temporary) / "package"
        for relative, data in payload.items():
            path = stage / "overlay" / relative
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
        stage.rename(output)
    return output, manifest, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output, manifest, reused = package(args.output)
    print(json.dumps({"status": "PASS", "output": str(output), "reused": reused, **manifest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
