#!/usr/bin/env python3
"""Fetch one immutable upstream source commit for the isolated TLS port trial."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TAG = "v5.9.2-stable"
COMMIT = "ac01707f552c611fbd135cc723b2682b3e7f80f2"
URL = f"https://codeload.github.com/wolfSSL/wolfssl/tar.gz/{COMMIT}"
ARCHIVE = ROOT / f"work/sources/wolfssl-5.9.2-{COMMIT[:8]}.tar.gz"
MANIFEST = ARCHIVE.with_suffix(ARCHIVE.suffix + ".json")


def main():
    if ARCHIVE.exists():
        data = ARCHIVE.read_bytes()
        previous = json.loads(MANIFEST.read_text())
        if previous["commit"] != COMMIT or previous["sha256"] != hashlib.sha256(data).hexdigest():
            raise ValueError("existing source archive differs; no overwrite permitted")
    else:
        with urllib.request.urlopen(URL, timeout=30) as response:
            data = response.read(60 * 1024 * 1024 + 1)
        if len(data) > 60 * 1024 * 1024: raise ValueError("source archive exceeds download bound")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getnames()
        expected_prefix = "wolfssl-" + COMMIT + "/"
        if any(name != expected_prefix[:-1] and (not name.startswith(expected_prefix) or ".." in Path(name).parts) for name in members):
            raise ValueError("unexpected source archive paths")
        relative = [name.removeprefix(expected_prefix) for name in members]
    report = {"schema": "openmitrastar.tls-source/v1", "project": "wolfSSL", "version": "5.9.2", "tag": TAG,
              "commit": COMMIT, "source_url": URL, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
              "upstream_signature_verified": False, "provenance": "official GitHub repository over HTTPS pinned to resolved release commit",
              "configure_present": "configure" in relative, "cmake_present": "CMakeLists.txt" in relative,
              "build_entrypoints": [name for name in relative if name in {"configure", "configure.ac", "autogen.sh", "CMakeLists.txt", "Makefile.am"}],
              "hardware_actions": False, "runtime_installed": False}
    if not ARCHIVE.exists():
        ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVE.write_bytes(data)
        MANIFEST.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__": main()
