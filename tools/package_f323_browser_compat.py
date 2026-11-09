"""Immutable F323 presentation package over F321's existing split-bundle API."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import lyoko_web_rootfs_worker as web
from package_lyoko_web_next import validate_dist

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "outputs/frontend/lyoko-browser-compat-20260911T095313Z/dist"
VERIFICATION = DIST.parent / "verification.json"
VERIFICATION_SHA = "c45e059a78ff5cdc4ae2c31fb7633e2560dd2f3d02d3616627b55520b69b4fb7"
BASE = ROOT / "outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9"
BASE_MANIFEST_SHA = "4c2a8b9536e28a55fc051a66f7a98df85b0417b90a3274d9f9d3c0c040a8626e"
SCHEMA = "openmitrastar.f323-browser-compat-overlay/v1"
UI_VERSION = "0.3.1-classic-compat"
BRANDS = {"movistar-logo.svg", "telefonica-logo.svg", "movistar-m.png"}
DASHBOARD = "usr/share/openmitrastar/web/dashboard.html"
INTEGRATION = {"base_api": "F321 split-v1 unchanged; no frontend retransform", "same_origin": True,
               "authenticated_entry": "/dashboard.cgi", "original_styles_and_brands": True,
               "config_store_fix": "separate F323 API transform, not in this UI overlay"}
SAFETY = {"hardware_actions": False, "flash": False, "radio_mutation": False, "persistent_writes_enabled": False}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_identity(data: bytes) -> dict[str, str]:
    rows = [line.split("=", 1) for line in data.decode("ascii").splitlines()]
    if any(len(row) != 2 for row in rows) or len(dict(rows)) != len(rows):
        raise ValueError("invalid or duplicate frontend identity")
    return dict(rows)


def verified_inputs() -> dict:
    if web.sha256(VERIFICATION) != VERIFICATION_SHA:
        raise ValueError("F323 browser-fix verification record drift")
    return json.loads(VERIFICATION.read_text(encoding="ascii"))


def package_identity(verified: dict) -> str:
    return digest(json.dumps({"schema": SCHEMA, "version": UI_VERSION,
        "verification_sha256": VERIFICATION_SHA, "base": BASE_MANIFEST_SHA,
        "assets": verified["build"]["assets"], "index": verified["build"]["index_sha256"]},
        sort_keys=True, separators=(",", ":")).encode("ascii"))[:16]


def source_metadata(verified: dict) -> dict:
    return {"base_f321_manifest_sha256": BASE_MANIFEST_SHA, "verification_sha256": VERIFICATION_SHA,
            "verified_inputs": verified["source_files"], "dist_assets": verified["build"]["assets"],
            "dist_index_sha256": verified["build"]["index_sha256"]}


def verified_dashboard(verified: dict) -> bytes:
    index = DIST / "index.html"
    if web.sha256(index) != verified["build"]["index_sha256"]:
        raise ValueError("F323 verified HTML source drift")
    html = index.read_text(encoding="utf-8")
    for row in verified["build"]["assets"]:
        name = Path(row["file"]).name
        relative = ("assets/" if name in BRANDS else "assets/lyoko-next/") + name
        html = html.replace("./assets/" + name, "/" + relative)
    return html.encode("utf-8")


def base_payload() -> tuple[dict, dict[str, bytes]]:
    if web.sha256(BASE / "manifest.json") != BASE_MANIFEST_SHA:
        raise ValueError("F321 UI base manifest drift")
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="ascii"))
    rows = web.validate_overlay(BASE / "overlay", manifest)
    return manifest, {path: (BASE / "overlay" / path).read_bytes() for path in rows}


def validate_package(overlay: Path, manifest: dict) -> dict:
    """File-only validation; safe in the Linux worker without Node or host home."""
    if manifest.get("schema") != SCHEMA or manifest.get("transforms") != []:
        raise ValueError("F323 uses an already integrated F321 API; no frontend transform is allowed")
    if any(manifest.get(key) is not False for key in ("release_eligible", "flash_supported", "firmware_generated")):
        raise ValueError("F323 UI package cannot grant release/flash authority")
    verified = verified_inputs()
    if (manifest.get("ui_version") != UI_VERSION or manifest.get("safety") != SAFETY
        or manifest.get("integration") != INTEGRATION or manifest.get("source") != source_metadata(verified)
        or manifest.get("build_id") != package_identity(verified)):
        raise ValueError("F323 manifest provenance, identity or safety contract drift")
    if (any(manifest["safety"].get(key) is not False for key in SAFETY)
        or manifest["integration"].get("same_origin") is not True
        or manifest["integration"].get("original_styles_and_brands") is not True):
        raise ValueError("F323 safety metadata requires strict booleans")
    if manifest.get("budgets") != {"js_brotli": verified["build"]["js_brotli_bytes"], "css_brotli": verified["build"]["css_brotli_bytes"]}:
        raise ValueError("F323 measured asset budget drift")
    expected = web.validate_overlay(overlay, manifest)
    if manifest.get("total_bytes") != sum(row["bytes"] for row in expected.values()):
        raise ValueError("F323 package byte count mismatch")
    if not (web.IDENTITY_PATHS | web.BRAND_PATHS).issubset(expected):
        raise ValueError("F323 identity or original brand is missing")
    _, original = base_payload()
    for path in web.BRAND_PATHS:
        if (overlay / path).read_bytes() != original[path]:
            raise ValueError("F323 original branding changed")
    css = [p for p in expected if p.endswith(".css")]
    if len(css) != 1 or css[0] not in original or (overlay / css[0]).read_bytes() != original[css[0]]:
        raise ValueError("F323 must preserve the exact F321 presentation stylesheet")
    bundle = json.loads((overlay / "etc/lyoko/web-next.json").read_text(encoding="ascii"))
    identity = read_identity((overlay / "etc/lyoko/frontend.env").read_bytes())
    next_identity = read_identity((overlay / "etc/lyoko/web-next.env").read_bytes())
    build_id = manifest.get("build_id")
    if not isinstance(build_id, str) or len(build_id) != 16 or any(c not in "0123456789abcdef" for c in build_id):
        raise ValueError("invalid F323 package build ID")
    source_name = "lyoko-classic-compat-" + build_id
    if (bundle.get("schema") != "lyoko.frontend.bundle/v1" or bundle.get("build_id") != build_id
        or bundle.get("ui_version") != UI_VERSION or bundle.get("source") != source_name
        or bundle.get("entry") != "/dashboard.cgi" or bundle.get("legacy_assets_retained") is not True):
        raise ValueError("F323 bundle identity mismatch")
    allowed_identity = {"LYOKO_UI_VERSION": UI_VERSION, "LYOKO_UI_BUILD_ID": build_id, "LYOKO_UI_SOURCE": source_name,
        "LYOKO_UI_DASHBOARD_HTML_SHA256": expected[DASHBOARD]["sha256"]}
    old_identity = read_identity(original["etc/lyoko/frontend.env"])
    allowed_identity["LYOKO_UI_ASSET_BYTES"] = str(int(old_identity["LYOKO_UI_ASSET_BYTES"])
        - len(original[DASHBOARD]) + expected[DASHBOARD]["bytes"])
    if identity != {**old_identity, **allowed_identity}:
        raise ValueError("F323 legacy frontend identity drift")
    old_next = read_identity(original["etc/lyoko/web-next.env"])
    if next_identity != {**old_next, "LYOKO_WEB_NEXT_VERSION": UI_VERSION, "LYOKO_WEB_NEXT_BUILD_ID": build_id}:
        raise ValueError("F323 session/mutation/entry metadata changed")
    assets = bundle.get("assets", [])
    active = {path for path in expected if path.startswith(("www/", "usr/share/"))}
    rows = {row["path"]: row for row in assets}
    if len(rows) != len(assets) or set(rows) != active:
        raise ValueError("F323 active asset catalogue mismatch")
    verified_assets = {}
    for row in verified["build"]["assets"]:
        name = Path(row["file"]).name
        path = "www/" + ("assets/" if name in BRANDS else "assets/lyoko-next/") + name
        verified_assets[path] = row
    if active != set(verified_assets) | {DASHBOARD}:
        raise ValueError("F323 active assets differ from the verified build")
    for path, row in verified_assets.items():
        if any(expected[path][key] != row[key] for key in ("bytes", "sha256")):
            raise ValueError("F323 asset is self-consistent but not the verified build")
    if (overlay / DASHBOARD).read_bytes() != verified_dashboard(verified):
        raise ValueError("F323 dashboard is not the verified authenticated entry")
    for path, row in rows.items():
        if any(row[key] != expected[path][key] for key in ("bytes", "sha256")):
            raise ValueError("F323 active asset identity drift")
        url = "/dashboard.cgi" if path == DASHBOARD else "/" + path.removeprefix("www/")
        if row.get("url") != url:
            raise ValueError("F323 active asset URL mismatch")
    if bundle.get("asset_bytes") != sum(row["bytes"] for row in rows.values()):
        raise ValueError("F323 active asset byte count mismatch")
    return expected


def prepare_payload(dist: Path = DIST) -> tuple[dict[str, bytes], dict]:
    verified = verified_inputs()
    _, original = base_payload()
    index, assets, _ = validate_dist(dist)
    rows = verified["build"]["assets"]
    if {a.name for a in assets} != {Path(r["file"]).name for r in rows}:
        raise ValueError("F323 compiled asset list drift")
    for row in rows:
        path = dist / row["file"]
        if web.sha256(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            raise ValueError("F323 compiled asset bytes changed")
    if web.sha256(index) != verified["build"]["index_sha256"]:
        raise ValueError("F323 HTML build input drift")
    # These compression measurements are bound to the exact verified bytes,
    # not inferred from a different dist or claimed as runtime HTTP compression.
    budgets = {key: verified["build"][key + "_brotli_bytes"] for key in ("js", "css")}
    if budgets["js"] > 48 * 1024 or budgets["css"] > 16 * 1024:
        raise ValueError("F323 static asset budget exceeded")
    for source in verified["source_files"]:
        if web.sha256(ROOT / source["path"]) != source["sha256"]:
            raise ValueError("F323 browser-fix sources changed since verified build")
    build_id = package_identity(verified)
    html, payload = index.read_text(encoding="utf-8"), {}
    for asset in assets:
        relative = ("assets/" if asset.name in BRANDS else "assets/lyoko-next/") + asset.name
        payload["www/" + relative] = asset.read_bytes()
        html = html.replace("./assets/" + asset.name, "/" + relative)
    payload[DASHBOARD] = html.encode("utf-8")
    active = [{"path": path, "url": "/dashboard.cgi" if path == DASHBOARD else "/" + path.removeprefix("www/"),
               "bytes": len(data), "sha256": digest(data)} for path, data in sorted(payload.items())]
    source_name = "lyoko-classic-compat-" + build_id
    bundle = {"schema": "lyoko.frontend.bundle/v1", "ui_version": UI_VERSION, "build_id": build_id,
              "source": source_name, "entry": "/dashboard.cgi", "assets": active,
              "asset_bytes": sum(row["bytes"] for row in active), "legacy_assets_retained": True}
    payload["etc/lyoko/web-next.json"] = (json.dumps(bundle, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    identity = read_identity(original["etc/lyoko/frontend.env"])
    identity.update(LYOKO_UI_VERSION=UI_VERSION, LYOKO_UI_BUILD_ID=build_id, LYOKO_UI_SOURCE=source_name,
        LYOKO_UI_DASHBOARD_HTML_SHA256=digest(payload[DASHBOARD]),
        LYOKO_UI_ASSET_BYTES=str(int(identity["LYOKO_UI_ASSET_BYTES"]) - len(original[DASHBOARD]) + len(payload[DASHBOARD])))
    payload["etc/lyoko/frontend.env"] = ("\n".join(f"{k}={v}" for k, v in identity.items()) + "\n").encode("ascii")
    next_identity = read_identity(original["etc/lyoko/web-next.env"])
    next_identity.update(LYOKO_WEB_NEXT_VERSION=UI_VERSION, LYOKO_WEB_NEXT_BUILD_ID=build_id)
    payload["etc/lyoko/web-next.env"] = ("\n".join(f"{k}={v}" for k, v in next_identity.items()) + "\n").encode("ascii")
    manifest = {"schema": SCHEMA, "build_id": build_id, "ui_version": UI_VERSION, "transforms": [],
        "release_eligible": False, "flash_supported": False, "firmware_generated": False,
        "source": source_metadata(verified),
        "budgets": {"js_brotli": budgets["js"], "css_brotli": budgets["css"]},
        "integration": dict(INTEGRATION),
        "safety": dict(SAFETY),
        "files": [{"path": path, "bytes": len(data), "sha256": digest(data), "mode": "0644"} for path, data in sorted(payload.items())],
        "total_bytes": sum(map(len, payload.values()))}
    return payload, manifest


def package() -> tuple[Path, dict, bool]:
    payload, manifest = prepare_payload()
    output = ROOT / "outputs/frontend" / ("lyoko-classic-compat-" + manifest["build_id"])
    if output.exists():
        existing = json.loads((output / "manifest.json").read_text(encoding="ascii"))
        if existing != manifest:
            raise ValueError("refusing to overwrite a different F323 package")
        validate_package(output / "overlay", existing)
        return output, manifest, True
    with tempfile.TemporaryDirectory(prefix=".f323-package-", dir=output.parent) as directory:
        staging = Path(directory) / "package"
        for path, data in payload.items():
            target = staging / "overlay" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
        validate_package(staging / "overlay", manifest)
        staging.rename(output)
    return output, manifest, False


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    output, manifest, reused = package()
    print(json.dumps({"status": "PASS_OFFLINE_UI_PACKAGE", "output": str(output), "manifest_sha256": web.sha256(output / "manifest.json"),
        "build_id": manifest["build_id"], "reused": reused, "bytes": manifest["total_bytes"], "hardware_actions": False}, indent=2))


if __name__ == "__main__":
    main()
