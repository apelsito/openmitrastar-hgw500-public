"""Build the existing pinned ARC hostapd with WPS; no device/network actions."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = ROOT / "work/mission-state/w2-ap-bundle/hostapd-minimal.config"
TARBALL = "/home/user/router-emulation/openwrt/dl/hostapd-2026.07.09~f08f2749.tar.zst"
TARBALL_SHA = "c1a978092c8a6e43a9e1bd47e1f334637b9c4969ca741c30ff45c24539132ca4"
LIBNL_BUILD = "/home/user/openmitrastar-build/iw-arc700/libnl-tiny"
LIBNL_SHA = "0782220718d94276f1b9477b982a81013babe3c0b2fcf738acec24639606399b"


def linux(path: Path) -> str:
    p = path.resolve()
    return "/mnt/" + p.drive[0].lower() + p.as_posix()[2:]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "outputs/kernel-port" / ("f335-hostapd-wps-"+stamp)
    out.mkdir(parents=True, exist_ok=False)
    source = SOURCE_CONFIG.read_text()
    if source.count("CONFIG_NO_AES_EXTRAS=y") != 1 or "CONFIG_WPS=" in source:
        raise SystemExit("The verified minimal source configuration changed")
    config = source.replace("CONFIG_NO_AES_EXTRAS=y\n", "", 1)
    config += "\n# F335: OEM WPS functionality, no startup or registrar activation.\nCONFIG_WPS=y\n"
    (out/"hostapd-baseline.config").write_bytes(SOURCE_CONFIG.read_bytes())
    (out/"hostapd-wps.config").write_text(config, encoding="ascii", newline="\n")
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    q = shlex.quote
    tc = linux(ROOT/"work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-")
    script = f'''set -eu
out={q(linux(out))}
tc={q(tc)}
tarball={q(TARBALL)}
libnl_build={q(LIBNL_BUILD)}
libnl_source=/home/user/router-emulation/openwrt/build_dir/target-arm_cortex-a7_musl_eabi/libnl-tiny-2025.12.02~40493a65
sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot
test "$(sha256sum "$tarball" | cut -d' ' -f1)" = {TARBALL_SHA}
test "$(sha256sum "$libnl_build/libnl-tiny.a" | cut -d' ' -f1)" = {LIBNL_SHA}
"${{tc}}gcc" --version > "$out/compiler-version.txt"
export SOURCE_DATE_EPOCH=1787011200
export LC_ALL=C
for lane in a b; do
 build=/home/user/openmitrastar-build/f335-hostapd-wps-{stamp}-$lane
 test ! -e "$build"
 mkdir -p "$build" "$out/$lane"
 tar --zstd -xf "$tarball" -C "$build" --strip-components=1
 cp "$out/hostapd-wps.config" "$build/hostapd/.config"
 {{
  printf '\\nCFLAGS += --sysroot=%s -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections\\n' "$sysroot"
  printf 'CFLAGS += -I%s/src -I%s/src/utils -I%s/include -D_GNU_SOURCE\\n' "$build" "$build" "$libnl_source"
  printf 'LDFLAGS += --sysroot=%s -static -Wl,--gc-sections -L%s\\n' "$sysroot" "$libnl_build"
  printf 'LIBS += -L%s\\n' "$libnl_build"
 }} >> "$build/hostapd/.config"
 make -C "$build/hostapd" -j4 hostapd hostapd_cli CC="${{tc}}gcc" AR="${{tc}}ar" PKG_CONFIG=/bin/false V=1 > "$out/build-$lane.log" 2>&1
 "${{tc}}strip" --strip-unneeded "$build/hostapd/hostapd" "$build/hostapd/hostapd_cli"
 cp "$build/hostapd/hostapd" "$build/hostapd/hostapd_cli" "$out/$lane/"
 cp "$build/hostapd/.config" "$out/$lane/effective.config"
 for binary in hostapd hostapd_cli; do
  "${{tc}}readelf" -h -l "$out/$lane/$binary" > "$out/$lane/$binary.elf.txt"
  "${{tc}}objdump" -d "$out/$lane/$binary" > "$out/$lane/$binary.disassembly.txt"
  grep -Eq 'Machine:.*ARC|Machine:.*ARCompact' "$out/$lane/$binary.elf.txt"
  ! grep -q 'Requesting program interpreter' "$out/$lane/$binary.elf.txt"
  ! grep -Eq '\\b(llock|scond)\\b' "$out/$lane/$binary.disassembly.txt"
 done
 strings "$out/$lane/hostapd" > "$out/$lane/hostapd.strings.txt"
 strings "$out/$lane/hostapd_cli" > "$out/$lane/hostapd_cli.strings.txt"
 grep -q 'WPS-PBC-ACTIVE' "$out/$lane/hostapd.strings.txt"
 grep -q 'WPS-TIMEOUT' "$out/$lane/hostapd.strings.txt"
 grep -q 'WPS-SUCCESS' "$out/$lane/hostapd.strings.txt"
 grep -q 'wps_pbc' "$out/$lane/hostapd_cli.strings.txt"
 grep -q 'wps_cancel' "$out/$lane/hostapd_cli.strings.txt"
 grep -q 'wps_get_status' "$out/$lane/hostapd_cli.strings.txt"
done
cmp "$out/a/hostapd" "$out/b/hostapd"
cmp "$out/a/hostapd_cli" "$out/b/hostapd_cli"
'''
    (out/"build.sh").write_bytes(script.encode("utf8"))
    p = subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", linux(out/"build.sh")],
                       capture_output=True, timeout=900)
    (out/"build.stdout").write_bytes(p.stdout)
    (out/"build.stderr").write_bytes(p.stderr)
    report = {"schema": "openmitrastar.f335-hostapd-wps-offline/v1",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "PASS_OFFLINE_WPS_BUILD" if p.returncode == 0 else "FAIL_BUILD",
              "build_returncode": p.returncode, "source_archive_sha256": TARBALL_SHA,
              "libnl_tiny_sha256": LIBNL_SHA, "baseline_config_sha256": sha(SOURCE_CONFIG),
              "wps_config_sha256": sha(out/"hostapd-wps.config"),
              "baseline_hostapd_sha256": "b772c70ae7aa9a045571ecc9b1168ab4e3faebe97ecc668d2227d36f0a13b1a7",
              "baseline_cli_sha256": "f7d6bc0aad17dcbc087ebc6bdd578671f441bd96845c20038a7161300b1ad728",
              "hardware_actions": False, "wps_activated": False, "firmware_created": False,
              "physical_acceptance": "UNRUN", "still_required": ["versioned startup/control integration", "enrollment/cancel/timeout/client acceptance"],
              "artifacts": {}}
    for name in ("hostapd", "hostapd_cli"):
        a, b = out/"a"/name, out/"b"/name
        if a.exists():
            report["artifacts"][name] = {"path": str(a), "bytes": a.stat().st_size,
                                        "sha256": sha(a), "reproduced": b.exists() and a.read_bytes() == b.read_bytes()}
    (out/"result.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"output_directory": str(out), **report}, indent=2))
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
