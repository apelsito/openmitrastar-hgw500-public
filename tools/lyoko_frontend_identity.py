"""One hash-pinned additive transform of the authenticated frontend API."""
from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess

API_PATH = "usr/libexec/openmitrastar/om-api-v1"
TRANSFORM_ID = "frontend-split-bundle/v1"
BASE_API_HASHES = {
    "f314": "f0f4d60afe0761f0087b58b77a6f318b5e13a6189d22cc45e11ef47e02dae778",
    "f317": "bed3a115e7001f2016a08a27dc62409ac3524da3b0734902dedc517c7da8375f",
}
BASE_FRONTEND_HASH = "f5aef3c28446b255a2715f80f280b0adc5b1ce8fbdf2e0be79f6c3dd1cf39ade"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_api(source: bytes) -> bytes:
    if digest(source) not in BASE_API_HASHES.values(): raise ValueError("API base is not pinned F314/F317")
    start = source.index(b"\nfrontend)\n")
    end = source.index(b"\n\t;;", start)
    branch = source[start:end]
    old = b'''jstr "$(frontend_value LYOKO_UI_LOGIN_CSS_SHA256)"; printf '}}\\n' '''.rstrip()
    new = b'''jstr "$(frontend_value LYOKO_UI_LOGIN_CSS_SHA256)"
\tprintf '},"asset_layout":"split-v1","bundle":'
\tif [ -r /etc/lyoko/web-next.json ]; then
\t\tcat /etc/lyoko/web-next.json
\telse
\t\tprintf 'null'
\tfi
\tprintf '}\\n' '''.rstrip()
    if branch.count(old) != 1 or b"\trequire_read\n" not in branch: raise ValueError("frontend branch contract changed")
    return source[:start] + branch.replace(old, new) + source[end:]


@lru_cache(maxsize=1)
def transform_spec() -> dict:
    inputs = []
    for base, expected in BASE_API_HASHES.items():
        image = Path.home() / f".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/{base}-device-bound/openmitrastar-linux510-{base}-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.rootfs.squashfs"
        image_linux = "/mnt/" + image.drive[0].lower() + "/" + image.as_posix()[3:]
        result = subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "unsquashfs", "-cat", image_linux, API_PATH], capture_output=True, check=True)
        if digest(result.stdout) != expected: raise ValueError(f"{base} API hash changed")
        after = patch_api(result.stdout)
        inputs.append({"base": base, "before_sha256": expected, "after_sha256": digest(after), "after_bytes": len(after)})
    return {"id": TRANSFORM_ID, "path": API_PATH, "mode": "0755", "inputs": inputs}


def check_transform_spec(spec: dict) -> None:
    if spec.get("id") != TRANSFORM_ID or spec.get("path") != API_PATH or spec.get("mode") != "0755":
        raise ValueError("unsupported API transform")
    inputs = spec.get("inputs", [])
    if len(inputs) != len(BASE_API_HASHES): raise ValueError("incomplete API transform pins")
    seen = set()
    for item in inputs:
        base = item.get("base")
        if base in seen or base not in BASE_API_HASHES or item.get("before_sha256") != BASE_API_HASHES[base]:
            raise ValueError("unrecognized API transform base")
        seen.add(base)


def transform_bytes(source: bytes, spec: dict) -> tuple[bytes, dict]:
    check_transform_spec(spec)
    before = digest(source)
    entry = next((item for item in spec["inputs"] if item["before_sha256"] == before), None)
    if entry is None: raise ValueError("source API does not match the transform")
    after = patch_api(source)
    if digest(after) != entry["after_sha256"] or len(after) != entry["after_bytes"]:
        raise ValueError("API transform output differs from package manifest")
    return after, {"id": TRANSFORM_ID, "path": API_PATH, **entry}
