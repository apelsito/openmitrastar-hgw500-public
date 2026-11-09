#!/usr/bin/env python3
"""Unpack a checksum-pinned Linux CMake wheel into the project, without pip."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "4.4.3"
SHA256 = "bae3c4954623ec4d62e62c70443f0da7988b733111c2871fcc6a31ead5137e20"
URL = "https://files.pythonhosted.org/packages/0b/d0/18fe62f0bddc8b9bb71ba55762ee48a224f8344101c34350d969f6e0d327/cmake-4.4.3-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"
ARCHIVE = ROOT / "work/sources/build-tools/cmake-4.4.3-linux-x86_64.whl"
TARGET = ROOT / "tools/external/cmake-4.4.3-linux"


def main():
    if ARCHIVE.exists(): data = ARCHIVE.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=30) as response: data = response.read(40 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != SHA256: raise ValueError("CMake wheel checksum mismatch")
    if not ARCHIVE.exists():
        ARCHIVE.parent.mkdir(parents=True, exist_ok=True); ARCHIVE.write_bytes(data)
    if not TARGET.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".cmake-", dir=TARGET.parent) as temporary:
            stage = Path(temporary) / "payload"; stage.mkdir()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    path = PurePosixPath(member.filename)
                    if path.is_absolute() or ".." in path.parts or "\\" in member.filename: raise ValueError("unsafe wheel path")
                    if member.filename.startswith("cmake/data/"): archive.extract(member, stage)
            stage.rename(TARGET)
    binary = TARGET / "cmake/data/bin/cmake"
    if not binary.is_file(): raise ValueError("local CMake executable missing")
    manifest = {"version": VERSION, "archive_sha256": SHA256, "checksum_source": "PyPI release metadata", "source_url": URL,
                "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "binary": str(binary), "global_install": False}
    metadata = TARGET / "provenance.json"
    if metadata.exists() and json.loads(metadata.read_text()) != manifest: raise ValueError("local CMake provenance differs")
    if not metadata.exists(): metadata.write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__": main()
