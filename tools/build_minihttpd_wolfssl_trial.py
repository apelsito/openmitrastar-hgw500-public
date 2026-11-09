#!/usr/bin/env python3
"""Link a modern TLS mini_httpd trial for ARC700; never install or flash it."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = "2cb631c81a383b32d4cb4553dfb88f87e8d2593e743f5a1887ed210d4d747440"
TLS_PATCH_SHA = "d0f644a42238638eaf6bca0600b175824faee7518aaec75615844a6e2f4702b9"
WOLF_LIBRARY_SHA = "bcc4b08148e11f9ea1f8c3515f6e98437b12d41c9807248d8c5b5341a95afb46"
WOLF_OPTIONS_SHA = "eb71ee9870f90dd4cc9bc19dc763b2e50b264fa5a8105f719a5ec89b8c842a97"
QUALIFIED_SOURCE_SHA = "7846d659529961d1ef6e03f7e3d3bfe27e43ca53e81569278473c641b50198e7"
HOST_REPORT_SHA = "fb59edf2a00b99622ea6d75174fd0a0931a4ac23c7a1d68620b348f34fdb2fbb"
LEGACY_IMAGE_SHA = "ee2c7a63ee738382ba8eaf813cfd725e64e52ce0686bfbf83129a78dcf323cce"
LEGACY_BINARY_SHA = "2a366556ee9ff59b590efc685fcfd5232e64845f2a3ce84244ec4b42b0433d9f"


def digest(data): return hashlib.sha256(data).hexdigest()


def run(argv, *, cwd=None):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=120)
    if result.returncode: raise RuntimeError(f"TLS link trial failed: {' '.join(map(str, argv[:4]))}\n" + (result.stdout + result.stderr)[-5000:])
    return result.stdout


def adapt_source(source: bytes) -> bytes:
    header = b"#include <openssl/ssl.h>\n#include <openssl/err.h>"
    context = b"ssl_ctx = SSL_CTX_new( SSLv23_server_method() );"
    accept = b"if ( SSL_accept( ssl ) == 0 )"
    attach = b"SSL_set_fd( ssl, conn_fd );"
    for marker in (header, context, accept, attach):
        if source.count(marker) != 1: raise ValueError("mini_httpd TLS adaptation anchor changed")
    source = source.replace(header, b"#include <wolfssl/options.h>\n#include <wolfssl/openssl/ssl.h>\n#include <wolfssl/openssl/err.h>")
    source = source.replace(context, context + b"\n\tif ( ssl_ctx == (SSL_CTX*) 0 ) { ERR_print_errors_fp( stderr ); exit( 1 ); }")
    source = source.replace(attach, b"if ( ssl == (SSL*) 0 || SSL_set_fd( ssl, conn_fd ) != 1 ) { ERR_print_errors_fp( stderr ); exit( 1 ); }")
    return patch_tls_environment(source.replace(accept, b"if ( SSL_accept( ssl ) <= 0 )"))


def patch_tls_environment(source: bytes) -> bytes:
    marker = b'    envp[envn++] = "SERVER_PROTOCOL=HTTP/1.0";'
    if source.count(marker) != 1 or b'"HTTPS=on"' in source: raise ValueError("unexpected CGI transport environment")
    addition = b'''
#ifdef USE_SSL
    if ( do_ssl
#ifdef SUPPORT_DATA_MODEL
         && doing_ssl
#endif
       )
        envp[envn++] = "HTTPS=on";
#endif /* USE_SSL */'''
    return source.replace(marker, marker + addition)


def linux_worker(args):
    source_c = (args.source / "mini_httpd.c").read_bytes()
    if digest(source_c) != SOURCE_SHA or digest(args.tls_patch.read_bytes()) != TLS_PATCH_SHA:
        raise ValueError("original mini_httpd/TLS patch provenance mismatch")
    library = args.wolfssl / "libwolfssl.a"
    if digest(library.read_bytes()) != WOLF_LIBRARY_SHA: raise ValueError("wolfSSL library hash mismatch")
    wolf = json.loads((args.wolfssl / "manifest.json").read_text())
    options = args.wolfssl / "include/wolfssl/options.h"
    if digest(options.read_bytes()) != WOLF_OPTIONS_SHA or wolf["options_sha256"] != WOLF_OPTIONS_SHA:
        raise ValueError("wolfSSL public options changed")
    if "HAVE_SERVER_RENEGOTIATION_INFO" not in wolf["required_definitions"]:
        raise ValueError("TLS 1.2 compatibility profile missing")
    report_bytes = args.host_report.read_bytes()
    if digest(report_bytes) != HOST_REPORT_SHA: raise ValueError("host qualification changed")
    report = json.loads(report_bytes)
    if report["status"] != "PASS" or report["fixed_source_sha256"] != QUALIFIED_SOURCE_SHA:
        raise ValueError("host source qualification missing")
    if wolf["options"] != report["requested_options"] or wolf["source_commit"] != report["source_commit"]:
        raise ValueError("host and ARC TLS profiles differ")
    if digest(args.legacy_image.read_bytes()) != LEGACY_IMAGE_SHA:
        raise ValueError("legacy F314 image changed")
    if args.output.exists(): raise ValueError("refusing to overwrite HTTPS trial")
    compiler = args.toolchain / "arc-linux-gcc"
    with tempfile.TemporaryDirectory(prefix="lyoko-mini-wolfssl-", dir="/tmp") as directory:
        build = Path(directory)
        for name in ("mini_httpd.c", "match.c", "tdate_parse.c", "version.h", "port.h", "match.h", "tdate_parse.h", "mime_encodings.txt", "mime_types.txt", "Makefile"):
            shutil.copyfile(args.source / name, build / name)
        run(["patch", "-s", "-p0", "-i", str(args.tls_patch)], cwd=build)
        patched = adapt_source((build / "mini_httpd.c").read_bytes())
        if digest(patched) != QUALIFIED_SOURCE_SHA:
            raise ValueError("ARC server source differs from qualified host source")
        (build / "mini_httpd.c").write_bytes(patched)
        run(["make", "-s", "mime_encodings.h", "mime_types.h"], cwd=build)
        flags = [f"--sysroot={args.sysroot}", "-Os", "-mno-atomic", "-fno-stack-protector", "-ffunction-sections", "-fdata-sections", "-DUSE_SSL", "-DNO_IPV6",
                 "-I" + str(args.wolfssl / "include"), f"-ffile-prefix-map={build}=/usr/src/mini-httpd-wolfssl"]
        for unit in ("mini_httpd", "match", "tdate_parse"):
            run([str(compiler), *flags, "-c", str(build / f"{unit}.c"), "-o", str(build / f"{unit}.o")])
        binary = build / "mini_httpd-wolfssl"
        run([str(compiler), f"--sysroot={args.sysroot}", "-mno-atomic", "-static", "-s", "-Wl,--gc-sections", "-o", str(binary),
             *(str(build / f"{unit}.o") for unit in ("mini_httpd", "match", "tdate_parse")), str(library), "-lcrypt", "-lm"])
        elf = run([str(args.toolchain / "arc-linux-readelf"), "-h", str(binary)])
        if "ARCompact" not in elf or "ARC700, v4 ABI" not in elf: raise ValueError("HTTPS executable is not ARC700 v4")
        program = run([str(args.toolchain / "arc-linux-readelf"), "-l", str(binary)])
        if "INTERP" in program: raise ValueError("HTTPS trial unexpectedly depends on a dynamic loader")
        disassembly = run([str(args.toolchain / "arc-linux-objdump"), "-d", str(binary)])
        if re.search(r"\s(?:llock|scond)(?:[.\s])", disassembly): raise ValueError("unsupported atomic instruction in HTTPS trial")
        legacy = subprocess.run(["unsquashfs", "-cat", str(args.legacy_image), "usr/sbin/mini_httpd-tls"], capture_output=True, check=True).stdout
        if digest(legacy) != LEGACY_BINARY_SHA: raise ValueError("legacy F314 TLS binary changed")
        manifest = {"schema": "lyoko.minihttpd-wolfssl-arc700-trial/v1", "status": "OFFLINE_LINK_PASS",
                    "mini_httpd_source_sha256": SOURCE_SHA, "existing_tls_patch_sha256": TLS_PATCH_SHA, "adapted_source_sha256": digest(patched),
                    "wolfssl_version": wolf["version"], "wolfssl_library_sha256": WOLF_LIBRARY_SHA, "options_sha256": wolf["options_sha256"],
                    "binary_bytes": binary.stat().st_size, "binary_sha256": digest(binary.read_bytes()),
                    "legacy_f314_tls_bytes": len(legacy), "legacy_f314_tls_sha256": digest(legacy),
                    "static_arc700_v4": True, "unsupported_atomics": False,
                    "host_qualification_sha256": HOST_REPORT_SHA, "source_matches_host_qualification": True,
                    "https_cgi_flag_server_owned": True, "tls12_rfc5746_indication": True,
                    "not_proven": ["ARC TLS 1.2/1.3 negotiation", "device client interoperability", "peak device RAM", "hardware runtime"],
                    "hardware_actions": False, "credential_files_used": False, "firmware_generated": False, "release_eligible": False}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".https-", dir=args.output.parent) as directory:
            stage = Path(directory) / "payload"; stage.mkdir()
            shutil.copy2(binary, stage / binary.name)
            (stage / "mini_httpd-adapted.c").write_bytes(patched)
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
            stage.rename(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--linux-worker", action="store_true", help=argparse.SUPPRESS)
    for name in ("source", "wolfssl", "toolchain", "sysroot", "tls-patch", "legacy-image", "host-report"):
        parser.add_argument("--" + name, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.linux_worker: linux_worker(args)
    else:
        import shlex
        from build_f306_unified_product_from_f305 import run_wsl, wsl_path
        from verify_lyoko_web_next_f314_rootfs import BASES
        output = (args.output or ROOT / "outputs/userland/minihttpd-wolfssl-5.9.2-arc700-cgi-tls-trial").resolve()
        command = ["python3", wsl_path(Path(__file__).resolve()), "--linux-worker", "--output", wsl_path(output),
                   "--source", wsl_path(ROOT / "work/sources/Quantenna-GPL/buildroot/package/zminihttpd/mini_httpd-1.19"),
                   "--wolfssl", wsl_path(ROOT / "outputs/userland/wolfssl-5.9.2-arc700-tlscompat-trial"),
                   "--host-report", wsl_path(ROOT / "outputs/userland/wolfssl-https-host-qualification/manifest.json"),
                   "--toolchain", wsl_path(ROOT / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin"),
                   "--sysroot", "/home/user/openmitrastar-uclibc-noatomic-sysroot",
                   "--tls-patch", wsl_path(ROOT / "work/mission-state/w4-https-getinfo/patches/mini_httpd-tls12.patch"),
                   "--legacy-image", wsl_path(BASES["f314"]["rootfs"])]
        print(run_wsl(shlex.join(command), args.distro))


if __name__ == "__main__": main()
