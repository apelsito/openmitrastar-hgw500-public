"""Build the F325 single-boot diagnostic provider; no device operations."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

import build_f315_radar_shadow_offline as donor
from build_f324_radar_lifecycle_offline import linux

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f325_radar_once"
QDRV_SOURCE = ROOT / "outputs/kernel-port/f315-radar-shadow-20260905/qdrv-f315-external-radar.ko"
QDRV_SHA = "1dda1a7c7e86bc6391dc113f45d7a3372fcb36894f0a7202abf82688076c35b0"
EPOCH = 1789776000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    main_c = (SOURCE / "qtn_radar_shadow_f315_main.c").read_text()
    assert sha(QDRV_SOURCE) == QDRV_SHA
    assert main_c.count("writel(") == 2
    for symbol in donor.EXPECTED_API:
        assert f"EXPORT_SYMBOL({symbol});" in main_c
    for marker in ("module_param_cb(shadow_arm", "try_module_get(THIS_MODULE)",
                   "f325_once_due(&f325_session, jiffies)", "cancel_delayed_work_sync(&f315_poll_work)",
                   "f325-single-boot-reset-required", "hardware_restored=0", "callback_invocations=0",
                   "shadow_channel != 36 || shadow_bandwidth != 80 || shadow_arm"):
        assert marker in main_c, marker
    for forbidden in ("qdrv_radar_detected", "mark_radar", "call_usermodehelper", "kernel_restart(", "__module_put("):
        assert forbidden not in main_c, forbidden
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = ROOT / "outputs/kernel-port" / ("f325-radar-once-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out / "source"
    shutil.copytree(SOURCE, snapshot)
    q = shlex.quote
    tc = linux(ROOT / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-")
    build = "/home/user/openmitrastar-build/f325-once-" + stamp
    script = f'''set -eu
out={q(linux(out))}
source={q(linux(snapshot))}
build={q(build)}
tc={q(tc)}
src={q(donor.KERNEL_SRC)}
kout={q(donor.KERNEL_OUT)}
qtn={q(linux(ROOT / "work/sources/Quantenna-GPL"))}
compat={q(linux(ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/compat/include"))}
symvers={q(linux(ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/Module.symvers"))}
test ! -e "$build"
mkdir -p "$build/a" "$build/b"
test "$(make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" kernelrelease)" = {q(donor.EXPECTED_RELEASE)}
cc -std=c99 -O2 -Wall -Wextra -Werror -pedantic "$source/test_f325_once.c" -o "$out/test-once"
"$out/test-once" >"$out/once-tests.log"
cc -std=c99 -O2 -Wall -Wextra -Werror "$source/test_f315_radar_core.c" "$source/f315_radar_core.c" -o "$out/test-core"
"$out/test-core" >"$out/core-tests.log"
for lane in a b; do
    cp "$source"/* "$build/$lane/"
    SOURCE_DATE_EPOCH={EPOCH} KBUILD_BUILD_TIMESTAMP=@{EPOCH} KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 \\
      make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build/$lane" QTN_GPL="$qtn" QDRV_COMPAT="$compat" \\
      KBUILD_EXTRA_SYMBOLS="$symvers" -j2 modules >"$out/build-$lane.log" 2>&1
done
cmp "$build/a/qtn_radar_shadow_f315.ko" "$build/b/qtn_radar_shadow_f315.ko"
cp "$build/a/qtn_radar_shadow_f315.ko" "$out/"
cp "$build/a/Module.symvers" "$out/provider-Module.symvers"
modinfo "$out/qtn_radar_shadow_f315.ko" >"$out/modinfo.txt"
test "$(modinfo -F vermagic "$out/qtn_radar_shadow_f315.ko")" = {q(donor.EXPECTED_VERMAGIC)}
"${{tc}}nm" -u "$out/qtn_radar_shadow_f315.ko" >"$out/imports.txt"
"${{tc}}readelf" -h "$out/qtn_radar_shadow_f315.ko" >"$out/readelf.txt"
"${{tc}}readelf" -p __ksymtab_strings "$out/qtn_radar_shadow_f315.ko" >"$out/exports.txt"
while read -r unused symbol; do
    test -z "$symbol" && continue
    if ! grep -q "[[:space:]]$symbol[[:space:]]" "$kout/Module.symvers" && ! grep -q "[[:space:]]$symbol[[:space:]]" "$symvers"; then
        echo "unresolved:$symbol" >&2; exit 1
    fi
done <"$out/imports.txt"
'''
    (out / "build.sh").write_bytes(script.encode())
    proc = subprocess.run(["wsl.exe", "-d", donor.DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-s"],
                          input=script.encode(), capture_output=True, timeout=600, check=False)
    (out / "build.stdout.txt").write_bytes(proc.stdout)
    (out / "build.stderr.txt").write_bytes(proc.stderr)
    if proc.returncode:
        print(json.dumps({"status": "FAIL_OFFLINE_BUILD", "output": str(out), "returncode": proc.returncode}))
        return 1
    provider = out / "qtn_radar_shadow_f315.ko"
    exports = set(re.findall(r"\[\s*[0-9a-f]+\]\s+(\w+)", (out / "exports.txt").read_text()))
    assert exports == set(donor.EXPECTED_API), exports
    assert "ARC" in (out / "readelf.txt").read_text()
    for lane in ("a", "b"):
        log = (out / f"build-{lane}.log").read_text()
        assert not re.search(r"frame size|undefined!|ERROR: modpost", log)
    shutil.copy2(QDRV_SOURCE, out / QDRV_SOURCE.name)
    result = {
        "schema": "openmitrastar.f325-radar-once-offline/v1", "status": "PASS_OFFLINE_DIAGNOSTIC_MODULE",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": {"file": provider.name, "bytes": provider.stat().st_size, "sha256": sha(provider), "reproducible": True},
        "qdrv": {"file": QDRV_SOURCE.name, "sha256": QDRV_SHA, "changed": False},
        "abi_exports": sorted(exports), "kernel": donor.EXPECTED_RELEASE,
        "lifecycle": {"auto_arm": False, "arm_once_per_boot": True, "window_ms": 20000,
                      "hardware_dirty_before_configuration": True, "self_pin_until_reboot": True,
                      "hardware_stop_proven": False, "hardware_restore_proven": False,
                      "cleanup": "STOP_SOFTWARE_POLLING_THEN_FULL_BOOT_RECOVERY_REQUIRED"},
        "authority": {"radar_start": False, "radar_get_status": False, "callbacks": 0, "dfs_tx": False},
        "sources": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in sorted(SOURCE.iterdir()) if p.is_file()],
        "hardware_actions": False, "flash_ready": False,
    }
    (out / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    (out / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(out.iterdir())
                                             if p.is_file() and p.name != "SHA256SUMS"), encoding="ascii")
    print(json.dumps({"status": result["status"], "provider": result["provider"], "output": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
