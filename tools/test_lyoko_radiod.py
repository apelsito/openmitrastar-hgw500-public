#!/usr/bin/env python3
"""Host build and behavioral tests for the standalone lyoko-radiod core."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work" / "userland" / "lyoko-radiod"


def compiler() -> list[str]:
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return [found]
    zig = ROOT / "tools" / "zig" / "zig-x86_64-windows-0.15.1" / "zig.exe"
    if zig.exists():
        return [str(zig), "cc"]
    raise RuntimeError("no host C compiler found")


def compile_binary(output: Path, extra_source: Path, backend_source: Path | None = None) -> None:
    sources = [
        SOURCE / "src" / "core.c",
        SOURCE / "src" / "journal.c",
        SOURCE / "src" / "profile.c",
        extra_source,
    ]
    if backend_source is not None:
        sources.insert(3, backend_source)
    command = compiler() + [
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        f"-I{SOURCE / 'include'}",
        *map(str, sources),
        "-o",
        str(output),
    ]
    subprocess.run(command, check=True, cwd=ROOT)


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-radiod-") as directory:
        temp = Path(directory)
        suffix = ".exe" if os.name == "nt" else ""
        core_test = temp / f"test-core{suffix}"
        daemon = temp / f"lyoko-radiod{suffix}"
        compile_binary(core_test, SOURCE / "tests" / "test_core.c")
        backend_source = SOURCE / "src" / "file_backend.c"
        if os.name == "nt":
            backend_source = temp / "file-backend-stub.c"
            backend_source.write_text(
                '#include "lyoko_file_backend.h"\n'
                '#include <errno.h>\n'
                'int lyoko_file_backend_open(lyoko_file_backend *b,const char *p)'
                '{(void)b;(void)p;errno=ENOTSUP;return -1;}\n'
                'void lyoko_file_backend_close(lyoko_file_backend *b){(void)b;}\n'
                'lyoko_persistence_backend lyoko_file_backend_interface(lyoko_file_backend *b)'
                '{lyoko_persistence_backend i={0};i.context=b;return i;}\n',
                encoding="ascii",
            )
        compile_binary(daemon, SOURCE / "src" / "main.c", backend_source)

        result = subprocess.run(
            [str(core_test)], check=True, capture_output=True, text=True
        )
        assert "PASS" in result.stdout

        profile = temp / "board.profile"
        profile.write_text(
            "\n".join(
                (
                    "version=1",
                    "board_id=portable-host-test",
                    "hysteresis_percent=15",
                    "stability_seconds=1800",
                    "active_window=04:00",
                    "band_limits=2g,5,20,40",
                    "band_limits=5g,5,23,80",
                    "candidate=2g,1,20,5,0",
                    "candidate=2g,6,20,5,0",
                    "candidate=5g,36,20,5,0",
                    "candidate=5g,44,40,5,0",
                    "",
                )
            ),
            encoding="ascii",
        )
        commands = "\n".join(
            (
                "FRAME 1000 20260905 3 59 0 0",
                "CURRENT 2g 1 20 5 0",
                "CURRENT 5g 36 20 5 0",
                "CANDIDATE 2g 1 20 5 0 800 -95 200 80 8000 34000 -55 80 0",
                "CANDIDATE 2g 6 20 5 0 80 -95 20 8 800 48400 -55 8 0",
                "CANDIDATE 5g 36 20 5 0 700 -95 175 70 7000 36000 -55 70 0",
                "CANDIDATE 5g 44 40 5 0 70 -95 17 7 700 48600 -55 7 0",
                "EVALUATE",
                "FRAME 2800 20260905 4 0 0 0",
                "CURRENT 2g 1 20 5 0",
                "CURRENT 5g 36 20 5 0",
                "CANDIDATE 2g 1 20 5 0 800 -95 200 80 8000 34000 -55 80 0",
                "CANDIDATE 2g 6 20 5 0 80 -95 20 8 800 48400 -55 8 0",
                "CANDIDATE 5g 36 20 5 0 700 -95 175 70 7000 36000 -55 70 0",
                "CANDIDATE 5g 44 40 5 0 70 -95 17 7 700 48600 -55 7 0",
                "EVALUATE",
                "QUIT",
                "",
            )
        )
        daemon_result = subprocess.run(
            [str(daemon), "--profile", str(profile)],
            input=commands,
            check=True,
            capture_output=True,
            text=True,
        )
        lines = daemon_result.stdout.splitlines()
        assert lines[0] == "READY board=portable-host-test persistence=fake generation=0"
        assert lines[1].startswith("DECISION wait_stability 3")
        assert lines[2].startswith("DECISION apply 3")

        observed = subprocess.run(
            [str(daemon), "--profile", str(profile), "--observe-only"],
            input=commands,
            check=True,
            capture_output=True,
            text=True,
        )
        assert observed.stdout.splitlines()[-1].startswith("DECISION propose 3")

        if os.name != "nt":
            state_dir = temp / "state"
            state_dir.mkdir()
            persistent_first = subprocess.run(
                [str(daemon), "--profile", str(profile), "--state-dir", str(state_dir)],
                input=commands,
                check=True,
                capture_output=True,
                text=True,
            )
            assert persistent_first.stdout.splitlines()[0] == (
                "READY board=portable-host-test persistence=file generation=0"
            )
            assert (state_dir / "journal-b.bin").is_file()
            persistent_second = subprocess.run(
                [str(daemon), "--profile", str(profile), "--state-dir", str(state_dir)],
                input=commands,
                check=True,
                capture_output=True,
                text=True,
            )
            second_lines = persistent_second.stdout.splitlines()
            assert second_lines[0] == "READY board=portable-host-test persistence=file generation=1"
            assert second_lines[-1].startswith("DECISION wait_window 3")

    if os.name == "nt":
        source = str(SOURCE).replace("\\", "/").replace("C:/", "/mnt/c/")
        shell = (
            f'set -eu; cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic '
            f'-I"{source}/include" "{source}/src/journal.c" '
            f'"{source}/src/file_backend.c" "{source}/tests/test_file_backend.c" '
            f'-o /tmp/test_lyoko_file_backend; /tmp/test_lyoko_file_backend'
        )
        subprocess.run(
            ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", shell],
            cwd=ROOT,
            check=True,
        )

    print("lyoko-radiod host build/tests: PASS")


if __name__ == "__main__":
    run()
