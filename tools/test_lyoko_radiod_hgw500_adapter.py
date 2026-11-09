#!/usr/bin/env python3
"""Offline tests for the HGW-500BNA-QCv2 lyoko-radiod adapter."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RADIOD = ROOT / "work" / "userland" / "lyoko-radiod"
ADAPTER = RADIOD / "adapters" / "hgw500bna-qcv2"
SOURCE = ADAPTER / "hgw500_adapter.c"
PROFILE = RADIOD / "profiles" / "hgw500bna-qcv2.profile"
MAC_RE = re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
SECRETS = (
    "PRIVATE-LYOKO-2G",
    "PRIVATE-LYOKO-5G",
    "NEVER-EMIT-THIS-PSK",
    "ALSO-PRIVATE",
    "SECRET-2G",
    "SECRET-5G",
)


def compiler() -> list[str]:
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return [found]
    zig = ROOT / "tools" / "zig" / "zig-x86_64-windows-0.15.1" / "zig.exe"
    if zig.exists():
        return [str(zig), "cc"]
    raise RuntimeError("no host C compiler found")


def compile_c(output: Path, sources: list[Path], include: Path | None = None) -> None:
    command = compiler() + [
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
    ]
    if include is not None:
        command.append(f"-I{include}")
    command.extend(str(path) for path in sources)
    command.extend(("-o", str(output)))
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)


def run_adapter(binary: Path, fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(binary),
            "--snapshot",
            str(ADAPTER / "fixtures" / fixture),
            "--profile",
            str(PROFILE),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def assert_redacted(result: subprocess.CompletedProcess[str]) -> None:
    combined = result.stdout + result.stderr
    assert MAC_RE.search(combined) is None, combined
    for secret in SECRETS:
        assert secret not in combined, secret


def assert_protocol(stdout: str) -> list[str]:
    lines = stdout.splitlines()
    assert lines and lines[0].startswith("FRAME ")
    assert lines[-1] == "EVALUATE"
    assert sum(line.startswith("CURRENT 2g ") for line in lines) == 1
    assert sum(line.startswith("CURRENT 5g ") for line in lines) == 1
    for line in lines:
        assert line.startswith(("FRAME ", "CURRENT ", "CANDIDATE ", "EVALUATE"))
        if line.startswith("CANDIDATE "):
            assert len(line.split()) == 15, line
    return lines


def assert_read_only_source() -> None:
    text = SOURCE.read_text(encoding="ascii")
    forbidden = (
        "system(",
        "popen(",
        "execve(",
        "execl(",
        "socket(",
        "ioctl(",
        "O_WRONLY",
        "O_RDWR",
        "fwrite(",
        "remove(",
        "rename(",
    )
    for token in forbidden:
        assert token not in text, token
    modes = re.findall(r'fopen\([^,]+,\s*"([^"]+)"\)', text)
    assert modes == ["rb", "rb"], modes


def assert_ascii_tree() -> None:
    for path in ADAPTER.rglob("*"):
        if path.is_file():
            path.read_text(encoding="ascii")


def run() -> None:
    assert_read_only_source()
    assert_ascii_tree()

    with tempfile.TemporaryDirectory(prefix="lyoko-hgw500-adapter-") as directory:
        temp = Path(directory)
        suffix = ".exe" if os.name == "nt" else ""
        adapter_binary = temp / f"hgw500-adapter{suffix}"
        daemon_binary = temp / f"lyoko-radiod{suffix}"
        backend_stub = temp / "file-backend-stub.c"
        backend_stub.write_text(
            '#include "lyoko_file_backend.h"\n'
            '#include <errno.h>\n'
            'int lyoko_file_backend_open(lyoko_file_backend *b,const char *p)'
            '{(void)b;(void)p;errno=ENOTSUP;return -1;}\n'
            'void lyoko_file_backend_close(lyoko_file_backend *b){(void)b;}\n'
            'lyoko_persistence_backend lyoko_file_backend_interface(lyoko_file_backend *b)'
            '{lyoko_persistence_backend i={0};i.context=b;return i;}\n',
            encoding="ascii",
        )

        compile_c(adapter_binary, [SOURCE])
        compile_c(
            daemon_binary,
            [
                RADIOD / "src" / "core.c",
                RADIOD / "src" / "journal.c",
                RADIOD / "src" / "profile.c",
                backend_stub,
                RADIOD / "src" / "main.c",
            ],
            RADIOD / "include",
        )

        complete = run_adapter(adapter_binary, "complete")
        complete_lines = assert_protocol(complete.stdout)
        assert_redacted(complete)
        assert complete_lines[0] == "FRAME 1788595200 20260905 4 1 3 0"
        assert "CURRENT 2g 6 20 18 0" in complete_lines
        assert "CURRENT 5g 36 80 21 0" in complete_lines
        assert (
            "CANDIDATE 2g 6 20 20 0 180 -95 50 5 2500 12000 -55 180 0"
            in complete_lines
        )
        assert (
            "CANDIDATE 5g 36 80 21 0 120 -98 20 2 1400 24000 -42 120 0"
            in complete_lines
        )
        assert "status=unavailable" not in complete.stderr

        daemon = subprocess.run(
            [str(daemon_binary), "--profile", str(PROFILE)],
            cwd=ROOT,
            input=complete.stdout + "QUIT\n",
            check=True,
            capture_output=True,
            text=True,
        )
        assert daemon.stdout.startswith(
            "READY board=mitrastar-hgw-500bna-qcv2 persistence=fake generation=0\nDECISION "
        )

        partial = run_adapter(adapter_binary, "partial")
        partial_lines = assert_protocol(partial.stdout)
        assert_redacted(partial)
        assert partial_lines[0] == "FRAME 1788595260 20260905 4 2 1 1"
        assert any(line.startswith("CANDIDATE 2g 1 ") for line in partial_lines)
        assert not any(line.startswith("CANDIDATE 5g ") for line in partial_lines)
        assert "METRIC band=5g name=throughput status=unavailable" in partial.stderr
        assert "METRIC band=5g name=latency status=unavailable" in partial.stderr
        assert "METRIC band=5g name=survey status=unavailable" in partial.stderr

        inconsistent_fixture = temp / "inconsistent"
        shutil.copytree(ADAPTER / "fixtures" / "complete", inconsistent_fixture)
        status = inconsistent_fixture / "hostapd" / "wifi0_status"
        status.write_text(
            status.read_text(encoding="ascii").replace("channel=36", "channel=44"),
            encoding="ascii",
        )
        inconsistent = subprocess.run(
            [
                str(adapter_binary),
                "--snapshot",
                str(inconsistent_fixture),
                "--profile",
                str(PROFILE),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert inconsistent.returncode == 3
        assert inconsistent.stdout == ""
        assert inconsistent.stderr == "ERROR current_radio=status_inconsistent\n"
        assert_redacted(inconsistent)

        missing = subprocess.run(
            [
                str(adapter_binary),
                "--snapshot",
                str(temp / "missing"),
                "--profile",
                str(PROFILE),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert missing.returncode == 3
        assert missing.stdout == ""
        assert missing.stderr == "ERROR snapshot=meta status=unavailable\n"

    print("lyoko-radiod HGW-500BNA-QCv2 adapter: PASS")


if __name__ == "__main__":
    run()
