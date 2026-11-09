from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest

import lyoko_ipk


def recipe(root: Path) -> Path:
    package = root / "lyoko-test"
    files = package / "files"
    files.mkdir(parents=True)
    (files / "lyoko-test").write_text("#!/bin/sh\necho test\n", encoding="ascii", newline="\n")
    (package / "package.json").write_text(json.dumps({
        "package": "lyoko-test",
        "version": "1.0.0-1",
        "architecture": lyoko_ipk.ARCH,
        "description": "test package",
        "kernel_abi": lyoko_ipk.KERNEL_ABI,
        "libc_abi": "uclibc",
        "platform": lyoko_ipk.PLATFORM,
        "files": [{"source": "files/lyoko-test", "target": "/usr/bin/lyoko-test", "mode": "0755"}],
    }) + "\n", encoding="ascii", newline="\n")
    return package


def test_builder_rejects_maintainer_scripts() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-script-") as directory:
        root = Path(directory)
        package = recipe(root)
        control = package / "control"
        control.mkdir()
        (control / "postinst").write_text("#!/bin/sh\nexit 0\n", encoding="ascii", newline="\n")
        with pytest.raises(ValueError, match="maintainer scripts"):
            lyoko_ipk.build_package(package, root / "out")


def test_reader_rejects_external_ipk_with_maintainer_script() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-script-") as directory:
        root = Path(directory)
        fields = lyoko_ipk.control_fields(json.loads((recipe(root) / "package.json").read_text(encoding="ascii")))
        fields["Installed-Size"] = "1"
        target = root / "malicious.ipk"
        lyoko_ipk.write_ar(target, [
            ("debian-binary", b"2.0\n"),
            ("control.tar.gz", lyoko_ipk.deterministic_tar_gz([
                ("control", lyoko_ipk.render_control(fields), 0o644),
                ("postinst", b"#!/bin/sh\nexit 0\n", 0o755),
            ])),
            ("data.tar.gz", lyoko_ipk.deterministic_tar_gz([("usr/bin/lyoko-test", b"test\n", 0o755)])),
        ])
        with pytest.raises(ValueError, match="maintainer scripts"):
            lyoko_ipk.read_control(target)
