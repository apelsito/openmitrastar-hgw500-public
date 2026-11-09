#!/usr/bin/env python3
"""Offline, non-deployable wolfSSL library trial for the proven ARC700 ABI."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "f1e121e2cb56aa40f85eb0995116c9858d2d8f184c08428e6a2db66b97e2c903"
SOURCE_COMMIT = "ac01707f552c611fbd135cc723b2682b3e7f80f2"
CMAKE_SHA = "84962dbf5de6a863507ae89347aa9414d978c0c610055b16c7c8f4233d8a339c"
OPTIONS = {
    "BUILD_SHARED_LIBS": "OFF", "WOLFSSL_ASM": "no", "WOLFSSL_SINGLE_THREADED": "yes",
    "WOLFSSL_OPENSSLEXTRA": "yes", "WOLFSSL_OPENSSLALL": "no", "WOLFSSL_TLS13": "yes", "WOLFSSL_TLSV12": "yes",
    "WOLFSSL_OLD_TLS": "no", "WOLFSSL_EXAMPLES": "no", "WOLFSSL_CRYPT_TESTS": "no", "WOLFSSL_MLKEM": "no",
    "WOLFSSL_DH": "const",
}


def sha256(path):
    with path.open("rb") as stream: return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, *, env=None, timeout=600):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(map(str, command[:5]))}\n" + (result.stdout + result.stderr)[-6500:])
    return result.stdout


def patch_options_template(data: bytes) -> bytes:
    # CMake sets SINGLE_THREADED for the library, but the 5.9.2 public options
    # template omits it. Consumers must see the identical configuration.
    additions = b""
    if b"#cmakedefine SINGLE_THREADED" not in data:
        additions += b"#undef SINGLE_THREADED\n#cmakedefine SINGLE_THREADED\n\n"
    if b"#cmakedefine HAVE_SERVER_RENEGOTIATION_INFO" not in data:
        additions += b"#undef HAVE_SERVER_RENEGOTIATION_INFO\n#cmakedefine HAVE_SERVER_RENEGOTIATION_INFO\n\n"
    if not additions: return data
    anchor = b"#undef HAVE_PTHREAD\n#cmakedefine HAVE_PTHREAD 1"
    if data.count(anchor) != 1: raise ValueError("unexpected wolfSSL options template")
    return data.replace(anchor, additions + anchor)


def patch_cmake_profile(data: bytes) -> bytes:
    anchor = b"set(WOLFSSL_DEFINITIONS)"
    if data.count(anchor) != 1: raise ValueError("unexpected CMake definitions anchor")
    return data.replace(anchor, b'set(WOLFSSL_DEFINITIONS "-DHAVE_SERVER_RENEGOTIATION_INFO")')


def linux_worker(args):
    if sha256(args.archive) != SOURCE_SHA: raise ValueError("wolfSSL archive hash mismatch")
    if sha256(args.cmake) != CMAKE_SHA: raise ValueError("local CMake binary hash mismatch")
    if args.output.exists(): raise ValueError("refusing to overwrite TLS trial output")
    compiler = args.toolchain / "arc-linux-gcc"
    if not compiler.is_file() or not args.sysroot.is_dir(): raise ValueError("exact ARC toolchain/sysroot unavailable")
    environment = {**os.environ, "SOURCE_DATE_EPOCH": "1788566400", "LC_ALL": "C"}
    with tempfile.TemporaryDirectory(prefix="lyoko-wolfssl-arc700-", dir="/tmp") as directory:
        scratch = Path(directory)
        with tarfile.open(args.archive, "r:gz") as source:
            source.extractall(scratch, filter="data")
        tree = scratch / ("wolfssl-" + SOURCE_COMMIT)
        template = tree / "cmake/options.h.in"
        template_before = template.read_bytes()
        template_after = patch_options_template(template_before)
        template.write_bytes(template_after)
        cmake_list = tree / "CMakeLists.txt"
        cmake_before = cmake_list.read_bytes()
        cmake_after = patch_cmake_profile(cmake_before)
        cmake_list.write_bytes(cmake_after)
        build = scratch / "build"
        prefix = scratch / "install"
        toolchain = scratch / "arc700-toolchain.cmake"
        flags = f"-Os -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -ffile-prefix-map={scratch}=/usr/src/wolfssl-trial"
        toolchain.write_text("\n".join([
            'set(CMAKE_SYSTEM_NAME Linux)', 'set(CMAKE_SYSTEM_PROCESSOR arc)',
            f'set(CMAKE_C_COMPILER "{compiler}")', f'set(CMAKE_ASM_COMPILER "{compiler}")',
            f'set(CMAKE_SYSROOT "{args.sysroot}")', f'set(CMAKE_C_FLAGS_INIT "{flags}")',
            'set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)',
            'set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)', 'set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)',
            'set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)', 'set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)',
        ]) + "\n", encoding="ascii")
        configure = [str(args.cmake), "-S", str(tree), "-B", str(build), "-G", "Unix Makefiles",
                     f"-DCMAKE_TOOLCHAIN_FILE={toolchain}", "-DCMAKE_BUILD_TYPE=MinSizeRel", f"-DCMAKE_INSTALL_PREFIX={prefix}"]
        configure += [f"-D{key}={value}" for key, value in OPTIONS.items()]
        configure_log = run(configure, env=environment)
        generated_options = [path for path in (build / "wolfssl/options.h", tree / "wolfssl/options.h") if path.is_file()]
        if len(generated_options) != 1: raise ValueError("cannot identify generated options.h")
        if not re.search(r"^\s*#\s*define\s+SINGLE_THREADED\b", generated_options[0].read_text(), re.MULTILINE):
            raise ValueError("single-thread configuration missing before compilation")
        run([str(args.cmake), "--build", str(build), "--parallel", "2"], env=environment)
        run([str(args.cmake), "--install", str(build)], env=environment)
        libraries = list(prefix.rglob("libwolfssl.a"))
        if len(libraries) != 1: raise ValueError("expected one static wolfSSL library")
        library = libraries[0]
        options = prefix / "include/wolfssl/options.h"
        if not options.is_file(): raise ValueError("generated options.h was not installed")
        definitions = set(re.findall(r"^\s*#\s*define\s+(\w+)", options.read_text(), re.MULTILINE))
        required = {"WOLFSSL_TLS13", "NO_OLD_TLS", "SINGLE_THREADED", "WOLFSSL_NO_ASM", "WOLFSSL_DH_CONST", "HAVE_SERVER_RENEGOTIATION_INFO"}
        if not required.issubset(definitions): raise ValueError(f"missing TLS build options: {required-definitions}")
        if "WOLFSSL_NO_TLS12" in definitions: raise ValueError("TLS 1.2 was unexpectedly disabled")
        elf = run([str(args.toolchain / "arc-linux-readelf"), "-h", str(library)])
        machines = re.findall(r"Machine:\s*(.+)", elf)
        if not machines or any("ARCompact" not in machine for machine in machines): raise ValueError("library contains non-ARC objects")
        flags_seen = re.findall(r"Flags:\s*(.+)", elf)
        if len(flags_seen) != len(machines) or any("ARC700" not in flags or "v4 ABI" not in flags for flags in flags_seen):
            raise ValueError("library ABI differs from ARC700 v4")
        disassembly = run([str(args.toolchain / "arc-linux-objdump"), "-d", str(library)])
        if re.search(r"\s(?:llock|scond)(?:[.\s])", disassembly): raise ValueError("unsupported ARC atomic instruction")
        undefined = run([str(args.toolchain / "arc-linux-nm"), "-u", str(library)])
        if re.search(r"\b(?:__atomic_|__sync_|pthread_)", undefined): raise ValueError("unexpected atomic/thread runtime dependency")
        if re.search(r"\bU\s+(?:pow|log)\b", undefined): raise ValueError("unexpected floating-point DH dependency")
        manifest = {"schema": "lyoko.wolfssl-arc700-trial/v1", "status": "OFFLINE_BUILD_PASS", "version": "5.9.2",
                    "source_commit": SOURCE_COMMIT, "source_archive_sha256": SOURCE_SHA,
                    "compiler": run([str(compiler), "--version"]).splitlines()[0], "cmake": run([str(args.cmake), "--version"]).splitlines()[0],
                    "options": OPTIONS, "required_definitions": sorted(required), "object_count": len(machines),
                    "cmake_template_patch": {"purpose": "export single-thread and TLS 1.2 indication configuration to consumers", "crypto_source_changed": False,
                        "before_sha256": hashlib.sha256(template_before).hexdigest(), "after_sha256": hashlib.sha256(template_after).hexdigest()},
                    "cmake_profile_patch": {"purpose": "RFC5746 server indication without enabling renegotiation", "before_sha256": hashlib.sha256(cmake_before).hexdigest(), "after_sha256": hashlib.sha256(cmake_after).hexdigest()},
                    "library_bytes": library.stat().st_size, "library_sha256": sha256(library), "options_sha256": sha256(options),
                    "unsupported_atomics": False, "thread_runtime_dependency": False,
                    "dh_profile": "upstream constant-size DH calculation; no pow/log dependency",
                    "not_proven": ["mini_httpd compatibility/linking", "TLS handshake", "final executable size", "peak RAM", "hardware runtime"],
                    "hardware_actions": False, "firmware_generated": False, "release_eligible": False}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".wolfssl-", dir=args.output.parent) as stage_dir:
            stage = Path(stage_dir) / "payload"; stage.mkdir()
            shutil.copy2(library, stage / "libwolfssl.a")
            shutil.copytree(prefix / "include", stage / "include")
            (stage / "configure.log").write_text(configure_log.replace(str(scratch), "BUILD_ROOT"), encoding="utf-8")
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
            stage.rename(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--linux-worker", action="store_true", help=argparse.SUPPRESS)
    for name in ("archive", "cmake", "toolchain", "sysroot"): parser.add_argument("--" + name, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.linux_worker: linux_worker(args)
    else:
        import shlex
        from build_f306_unified_product_from_f305 import run_wsl, wsl_path
        output = (args.output or ROOT / "outputs/userland/wolfssl-5.9.2-arc700-tlscompat-trial").resolve()
        command = ["python3", wsl_path(Path(__file__).resolve()), "--linux-worker", "--output", wsl_path(output),
                   "--archive", wsl_path(ROOT / "work/sources/wolfssl-5.9.2-ac01707f.tar.gz"),
                   "--cmake", wsl_path(ROOT / "tools/external/cmake-4.4.3-linux/cmake/data/bin/cmake"),
                   "--toolchain", wsl_path(ROOT / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin"),
                   "--sysroot", "/home/user/openmitrastar-uclibc-noatomic-sysroot"]
        print(run_wsl(shlex.join(command), args.distro, timeout=900))


if __name__ == "__main__": main()
