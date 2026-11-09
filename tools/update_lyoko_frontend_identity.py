#!/usr/bin/env python3
"""Generate deterministic, path-free identity metadata for a Lyoko frontend."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ASSETS = (
    "www/dashboard.html",
    "www/app.js",
    "www/app.css",
    "www/layout-fixes.css",
    "www/capabilities.css",
    "www/assets/logo.svg",
)
OPTIONAL_ASSETS = (
    "www/login.html",
    "www/login.css",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(foundation: Path, version: str, source: str) -> str:
    overlay = foundation / "overlay"
    assets = ASSETS + tuple(name for name in OPTIONAL_ASSETS if (overlay / name).is_file())
    hashes = {name: sha256(overlay / name) for name in assets}
    material = "".join(f"{name}\0{hashes[name]}\n" for name in assets).encode("ascii")
    build_id = hashlib.sha256(material).hexdigest()[:16]
    total_bytes = sum((overlay / name).stat().st_size for name in assets)
    lines = [
        f"LYOKO_UI_VERSION={version}",
        f"LYOKO_UI_BUILD_ID={build_id}",
        f"LYOKO_UI_SOURCE={source}",
        f"LYOKO_UI_ASSET_BYTES={total_bytes}",
        f"LYOKO_UI_HTML_SHA256={hashes['www/dashboard.html']}",
        f"LYOKO_UI_JS_SHA256={hashes['www/app.js']}",
        f"LYOKO_UI_CSS_SHA256={hashes['www/app.css']}",
    ]
    if "www/login.html" in hashes:
        lines.append(f"LYOKO_UI_LOGIN_HTML_SHA256={hashes['www/login.html']}")
    if "www/login.css" in hashes:
        lines.append(f"LYOKO_UI_LOGIN_CSS_SHA256={hashes['www/login.css']}")
    return "\n".join((*lines, ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("foundation", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = args.foundation / "overlay/etc/lyoko/frontend.env"
    expected = render(args.foundation, args.version, args.source)
    if args.check:
        if not destination.is_file() or destination.read_text(encoding="ascii") != expected:
            raise SystemExit("frontend identity is stale")
        print(f"LYOKO_FRONTEND_IDENTITY_CHECK_PASS={destination}")
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(expected, encoding="ascii")
    print(f"LYOKO_FRONTEND_IDENTITY_UPDATED={destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
