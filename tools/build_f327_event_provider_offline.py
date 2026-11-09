"""Build F327 lifecycle tests and a non-authoritative Linux 5.10 ARC module.

No SSH, UART, network, firmware packaging or hardware actions. Every run creates
a new immutable evidence directory; original F316 and sealed sources are read.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from compose_f327_oem_adapter import compose

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f327_radar_event_lifecycle"
ORIGINAL = ROOT / "work/kernel-port/modules/f316_radar_native"
DISTRO = "podman-mem9-tidb"
KERNEL = "/home/user/mitrastar-linux-5.10.260"
KOUT = "/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample"
RELEASE = "5.10.260-openmitrastar-radiohw"
API = (
    "detect_drv_sample_loc_get", "dfs_rqmt_code", "radar_disable", "radar_enable",
    "radar_get_chan", "radar_get_status", "radar_ocac_info_addr_get",
    "radar_record_buffer_pt", "radar_register", "radar_register_is_dfs_chan",
    "radar_register_is_dfs_weather_chan", "radar_register_statcb", "radar_set_bw",
    "radar_set_chan", "radar_set_shared_params", "radar_start", "radar_stop",
    "sta_dfs_is_region_required",
)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def linux(path: Path) -> str:
    path = path.resolve()
    if not re.fullmatch(r"[A-Za-z]:", path.drive):
        raise ValueError("expected Windows local path")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]

def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = ROOT / "outputs/kernel-port" / ("f327-event-provider-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out / "source"
    snapshot.mkdir()
    files = [p for p in SOURCE.rglob("*") if p.is_file() and
             (p.suffix in {".c", ".h", ".inc", ".md"} or p.name == "Makefile")]
    for path in files:
        target = snapshot / path.relative_to(SOURCE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copyfile(Path(__file__), out / Path(__file__).name)
    shutil.copyfile(ROOT / "tools/compose_f327_oem_adapter.py", out / "compose_f327_oem_adapter.py")
    classifier_parity = []
    for copied in sorted((SOURCE / "classifier").rglob("*")):
        if copied.is_file():
            original = ORIGINAL / copied.relative_to(SOURCE)
            if sha(copied) != sha(original):
                raise ValueError(f"F316 classifier changed: {copied}")
            classifier_parity.append({"path": str(copied.relative_to(SOURCE)), "sha256": sha(copied)})
    original_main = ORIGINAL / "qtn_radar_native_f316_main.c"
    if sha(original_main) != "c8425105133b0d2e365d7aad6dca6aad2e8be7c2dd3ecb34b1ba3961e0a0e535":
        raise ValueError("original F316 source changed")
    main_source = (SOURCE / "qtn_radar_native_f327_main.c").read_text()
    assert main_source == compose()
    assert "#define F327_RELEASE_QUALIFIED 0" in main_source
    assert "if (authoritative_enable || weather_enable)" in main_source
    worker_source = (SOURCE / "f327_oem_worker.inc").read_text()
    assert worker_source.index("f327_capture_begin(&f327_session, &capture)") < worker_source.index("f315_capture_batch(batch)")
    assert '#include "f327_oem_kernel_adapter.inc"' in main_source
    assert '#include "f327_kernel_transition.inc"' not in main_source
    for name in API:
        assert f"EXPORT_SYMBOL({name});" in main_source
    q = shlex.quote
    tc = linux(ROOT / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-")
    qtn = linux(ROOT / "work/sources/Quantenna-GPL")
    compat = linux(ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/compat/include")
    symvers = linux(ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/Module.symvers")
    script = f"""set -eu
out={q(linux(out))}
source={q(linux(snapshot))}
base="$source/classifier"
tc={q(tc)}
sources=("$source/f327_event_lifecycle.c" "$base/f316_classifier.c" "$base/preprocess/f316_preprocess.c" "$base/ssr_itlv/f316_ssr_itlv.c" "$base/lsr/f316_lsr.c" "$base/postfilter/f316_postfilter.c" "$base/candidate_selector/f316_candidate_selector.c")
cc --version >"$out/host-compiler.txt"
"${{tc}}gcc" --version >"$out/arc-compiler.txt"
for testname in event_lifecycle oem_adapter; do
  cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -I"$base" -I"$source" "${{sources[@]}}" "$source/test_f327_${{testname}}.c" -o "$out/test_${{testname}}"
  "$out/test_${{testname}}" >"$out/test_${{testname}}.log" 2>&1
done
cc -std=c11 -O0 -Wall -Wextra -Werror -pedantic -fanalyzer -I"$base" -I"$source" -c "$source/f327_event_lifecycle.c" -o "$out/analyzed-core.o" >"$out/analyzer.log" 2>&1
if cc -std=c11 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -I"$base" -I"$source" "${{sources[@]}}" "$source/test_f327_event_lifecycle.c" -o "$out/test_sanitized" >"$out/sanitizer-build.log" 2>&1; then
  "$out/test_sanitized" >"$out/sanitizer-run.log" 2>&1
  printf 'PASS\n' >"$out/sanitizer-status.txt"
else
  printf 'NOT_RUN_RUNTIME_OR_TOOLCHAIN_UNAVAILABLE\n' >"$out/sanitizer-status.txt"
fi
test "$(make -s -C {q(KERNEL)} O={q(KOUT)} ARCH=arc CROSS_COMPILE="$tc" kernelrelease)" = {q(RELEASE)}
for variant in a b; do
  build=$(mktemp -d "/home/user/openmitrastar-build/f327-${{variant}}-XXXXXXXX")
  printf '%s\n' "$build" >"$out/build-${{variant}}-directory.txt"
  cp -a "$source"/. "$build"/
  SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 \\
  make -C {q(KERNEL)} O={q(KOUT)} ARCH=arc CROSS_COMPILE="$tc" M="$build" QTN_GPL={q(qtn)} QDRV_COMPAT={q(compat)} KBUILD_EXTRA_SYMBOLS={q(symvers)} KBUILD_MODPOST_WARN=1 -j8 modules >"$out/build-${{variant}}.log" 2>&1
  cp "$build/qtn_radar_native_f327.ko" "$out/provider-${{variant}}.ko"
done
! grep -q 'frame size' "$out/build-a.log" "$out/build-b.log"
cmp "$out/provider-a.ko" "$out/provider-b.ko"
cp "$out/provider-a.ko" "$out/qtn_radar_native_f327.ko"
modinfo "$out/qtn_radar_native_f327.ko" >"$out/modinfo.txt"
test "$(modinfo -F vermagic "$out/qtn_radar_native_f327.ko")" = {q(RELEASE + ' mod_unload ARC700')}
"${{tc}}readelf" -h "$out/qtn_radar_native_f327.ko" >"$out/readelf.txt"
"${{tc}}nm" -u "$out/qtn_radar_native_f327.ko" >"$out/imports.txt"
"${{tc}}readelf" -p __ksymtab_strings "$out/qtn_radar_native_f327.ko" >"$out/exports.txt"
for symbol in {' '.join(API)}; do grep -Eq "[[:space:]]${{symbol}}$" "$out/exports.txt"; done
"${{tc}}objdump" -dr "$out/qtn_radar_native_f327.ko" >"$out/objdump.txt"
"""
    (out / "build.sh").write_bytes(script.encode("utf-8"))
    process = subprocess.run(["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-s"], input=script.encode(), capture_output=True, timeout=300, check=False)
    (out / "build.stdout.txt").write_bytes(process.stdout)
    (out / "build.stderr.txt").write_bytes(process.stderr)
    report = {"schema": "openmitrastar.f327-event-provider/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "OFFLINE_BUILD_FAILED", "returncode": process.returncode, "hardware_actions": False,
              "evidence_directory": str(out), "original_f316_sha256": sha(original_main),
              "classifier_copies_unchanged": classifier_parity}
    if process.returncode == 0:
        module = out / "qtn_radar_native_f327.ko"
        report.update(status="PASS_OFFLINE_KERNEL_INTEGRATION_NO_DFS_AUTHORITY",
                      lifecycle_tests=(out / "test_event_lifecycle.log").read_text().strip(),
                      kernel_adapter_tests=(out / "test_oem_adapter.log").read_text().strip(),
                      sanitizer=(out / "sanitizer-status.txt").read_text().strip(), analyzer="PASS",
                      module={"path": str(module), "bytes": module.stat().st_size, "sha256": sha(module), "vermagic": RELEASE + " mod_unload ARC700"},
                      reproducible=sha(out / "provider-a.ko") == sha(out / "provider-b.ko"),
                      abi_exports=list(API), firmware_image_created=False, physical_pass=False,
                      limitations=["No kernel runtime concurrency test", "QT4 acquisition ownership and reset lifetime not accepted", "Original F316 classifier equivalence gaps preserved", "DFS callbacks and radar_start cannot authorize TX in this artifact"])
        report["qdrv_execution_abi"] = "OEM_NONBLOCKING_REQUESTS_IRQ_SAFE_SOURCE_AND_MODEL_CHECKED_PHYSICAL_PENDING"
        report["inherited_callback_semantics"] = "Already admitted callback may finish after disable; no universal drain claim"
    report["sources"] = [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in sorted(files)]
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps({k: v for k, v in report.items() if k not in {"sources", "classifier_copies_unchanged", "abi_exports"}}, indent=2))
    return int(process.returncode != 0)

if __name__ == "__main__":
    raise SystemExit(main())
