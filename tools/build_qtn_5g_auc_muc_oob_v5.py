#!/usr/bin/env python3
"""Build a self-contained OOB harness for the v5 AuC-off discriminator."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BUILDER = ROOT / "tools/build_qtn_5g_auc_muc_discriminant_runtime.py"
BASE_ONE_SHOT = ROOT / "tools/run_qtn_5g_aelita_one_shot.py"
BASE_COORDINATOR = ROOT / "tools/run_qtn_5g_aelita_uart_capture.py"
BASE_EVALUATOR = ROOT / "tools/evaluate_qtn_5g_uart_txpath.py"
PINNED = {
    RUNTIME_BUILDER: "30efe69b1c5f4c72dc3b7eef362a708111fa04b35384aa1965174e99e51f92a1",
    BASE_ONE_SHOT: "08060f5bc6d07387e60943cf2844c8fc7a2071be5549bccb53ca8ad74f0322ea",
    BASE_COORDINATOR: "f9eb086ba6efa429a77c901001af7b5ece7427ea2acfdbb18dd244fbf7523f27",
    BASE_EVALUATOR: "605efb7969bd2463c8af2dc67dfce939b3f08a1791aee69d6f4563f6a2c751c2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count is {count}, expected 1")
    return text.replace(old, new, 1)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def generate_evaluator(output: Path) -> Path:
    text = BASE_EVALUATOR.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    rollback_complete = rollback_match is not None\n',
        '    auc_restore_match = re.search(\n'
        '        r"OMRADIO5_ROLLBACK_COMPLETE reason=[^\\s]+ "\n'
        '        r"rf=closed wifi0=down eth0_2g=preserved "\n'
        '        r"auc_tx_restore_rc=(\\d+)",\n'
        '        window,\n'
        '    )\n'
        '    rollback_complete = rollback_match is not None\n'
        '    auc_restore_ok = bool(auc_restore_match and auc_restore_match.group(1) == "0")\n',
        "evaluator auc marker",
    )
    text = replace_once(
        text,
        '    elif (rollback_complete and rollback_codes_ok and not reset_seen\n'
        '          and management_ok and recovery_clean and loglevel_restored):\n',
        '    elif (rollback_complete and rollback_codes_ok and auc_restore_ok and not reset_seen\n'
        '          and management_ok and recovery_clean and loglevel_restored):\n',
        "evaluator terminal condition",
    )
    text = replace_once(
        text,
        '        "rollback_codes_ok": rollback_codes_ok,\n',
        '        "rollback_codes_ok": rollback_codes_ok,\n'
        '        "rollback_auc_tx_restore_ok": auc_restore_ok,\n'
        '        "rollback_auc_tx_restore_rc": (\n'
        '            int(auc_restore_match.group(1)) if auc_restore_match else None\n'
        '        ),\n',
        "evaluator result fields",
    )
    path = output / "evaluate_qtn_5g_uart_txpath_v5.py"
    write(path, text)
    return path


def generate_one_shot(output: Path, runtime_manifest_sha: str,
                      qdrv_sha: str, start_sha: str, stop_sha: str) -> Path:
    text = BASE_ONE_SHOT.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'ROOT = Path(__file__).resolve().parents[1]\n',
        'PACKAGE_DIR = Path(__file__).resolve().parent\n'
        'ROOT = Path(__file__).resolve().parents[3]\n',
        "one-shot root",
    )
    text = replace_once(
        text,
        'TRACE_DIR = ROOT / "outputs/kernel-port/quantenna-5g-tqe-rxalign-whcopy-runtime-v4-20260823"\n'
        'TRACE_MANIFEST = TRACE_DIR / "manifest.json"\n'
        'TRACE_MANIFEST_SHA = "cb26ddc8533cecc4387b5fe132e5e912f2d67cc259758fd2ba30feda0b6ea8b7"\n'
        'TRACE_QDRV = TRACE_DIR / "qdrv-tqe-rxalign-whcopy-txpath.ko"\n'
        'TRACE_QDRV_SHA = "f9982924fa655fb24b47f902752cbb9e682419b3e4684f29cb110b42648200f1"\n'
        'TRACE_START = TRACE_DIR / "om-radio5-start-tqe-rxalign-whcopy-txpath"\n'
        'TRACE_START_SHA = "acf4ecc87cf05afe07f5e4b1e19af1a47adc857e18e797b9497bc5d951063031"\n',
        'TRACE_DIR = PACKAGE_DIR\n'
        'TRACE_MANIFEST = TRACE_DIR / "runtime-manifest.json"\n'
        f'TRACE_MANIFEST_SHA = "{runtime_manifest_sha}"\n'
        'TRACE_QDRV = TRACE_DIR / "qdrv-tqe-rxalign-whcopy-auctx-muc-v5.ko"\n'
        f'TRACE_QDRV_SHA = "{qdrv_sha}"\n'
        'TRACE_START = TRACE_DIR / "om-radio5-start-auctx-muc-v5"\n'
        f'TRACE_START_SHA = "{start_sha}"\n'
        'TRACE_STOP = TRACE_DIR / "om-radio5-stop-auctx-muc-v5"\n'
        f'TRACE_STOP_SHA = "{stop_sha}"\n',
        "one-shot runtime constants",
    )
    text = replace_once(
        text,
        '        or manifest["artifacts"]["stop"]["sha256"] != qtn_runner.SAFE_STOP[1]\n',
        '        or sha256(TRACE_STOP) != TRACE_STOP_SHA\n'
        '        or manifest["artifacts"]["stop"]["sha256"] != TRACE_STOP_SHA\n',
        "one-shot stop verification",
    )
    text = replace_once(
        text,
        '    qtn_runner.SAFE_START = (TRACE_START, TRACE_START_SHA)\n',
        '    qtn_runner.SAFE_START = (TRACE_START, TRACE_START_SHA)\n'
        '    qtn_runner.SAFE_STOP = (TRACE_STOP, TRACE_STOP_SHA)\n',
        "one-shot stop override",
    )
    text = replace_once(
        text,
        '\n\ndef verify_local() -> dict:\n',
        '''

def stop_radio5_exception_verified(host: str, reason: str) -> bool:
    """Attempt the v5 stop without deleting the still-armed rollback assets."""
    command = rf"""set +e
stop={qtn_runner.SAFE_OVERLAY}/bin/om-radio5-stop
test -x "$stop" || {{ echo OMQTN5G_V5_EXCEPTION_STOP stop_rc=127 auc_tx_restore=unproven; exit 127; }}
"$stop" {reason}
stop_rc=$?
if [ "$stop_rc" = 0 ]; then
  echo OMQTN5G_V5_EXCEPTION_STOP stop_rc=0 auc_tx_restore=proven
else
  echo OMQTN5G_V5_EXCEPTION_STOP stop_rc=$stop_rc auc_tx_restore=unproven
fi
exit "$stop_rc"
"""
    result = qtn_runner.ssh(host, command, 45, check=False)
    return (
        result.returncode == 0
        and "OMQTN5G_V5_EXCEPTION_STOP stop_rc=0 auc_tx_restore=proven" in result.stdout
    )


def verify_local() -> dict:
''',
        "one-shot verified exception stop",
    )
    text = replace_once(
        text,
        '    radio_started = False\n    overlay_staged = False\n',
        '    radio_started = False\n    overlay_staged = False\n    rollback_armed = False\n',
        "one-shot rollback state",
    )
    text = replace_once(
        text,
        '        qtn_runner.arm_rollback(args.router_host, 240, run_id)\n',
        '        qtn_runner.arm_rollback(args.router_host, 240, run_id)\n'
        '        rollback_armed = True\n',
        "one-shot initial rollback",
    )
    text = replace_once(
        text,
        '    except Exception:\n'
        '        if overlay_staged:\n'
        '            qtn_runner.stop_radio5(args.router_host, "aelita-one-shot-failed")\n'
        '        qtn_runner.cleanup_safe_overlay(args.router_host)\n'
        '        raise\n',
        '    except Exception as original_error:\n'
        '        if overlay_staged and rollback_armed:\n'
        '            stop_ok = stop_radio5_exception_verified(\n'
        '                args.router_host, "aelita-one-shot-failed"\n'
        '            )\n'
        '            # The target-local rollback still owns cleanup.  Keeping the\n'
        '            # overlay is mandatory even when this immediate stop succeeds.\n'
        '            if not stop_ok:\n'
        '                raise RuntimeError(\n'
        '                    "v5 exception stop failed; outer rollback remains armed "\n'
        '                    "and overlay was preserved"\n'
        '                ) from original_error\n'
        '        elif overlay_staged:\n'
        '            # No rollback was armed yet, so no callback can depend on it.\n'
        '            qtn_runner.cleanup_safe_overlay(args.router_host)\n'
        '        raise\n',
        "one-shot exception rollback ownership",
    )
    text = text.replace(
        'python tools/run_qtn_5g_aelita_one_shot.py --execute ',
        'python -B outputs/kernel-port/quantenna-5g-auc-muc-oob-v5-20260823/'
        'run_qtn_5g_aelita_one_shot_v5.py --execute ',
    )
    path = output / "run_qtn_5g_aelita_one_shot_v5.py"
    write(path, text)
    return path


def generate_coordinator(output: Path, one_shot_sha: str, evaluator_sha: str) -> Path:
    text = BASE_COORDINATOR.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'ROOT = Path(__file__).resolve().parents[1]\n',
        'PACKAGE_DIR = Path(__file__).resolve().parent\n'
        'ROOT = Path(__file__).resolve().parents[3]\n',
        "coordinator root",
    )
    text = replace_once(
        text,
        'ONE_SHOT = ROOT / "tools/run_qtn_5g_aelita_one_shot.py"\n'
        'ONE_SHOT_SHA256 = "08060f5bc6d07387e60943cf2844c8fc7a2071be5549bccb53ca8ad74f0322ea"\n',
        'ONE_SHOT = PACKAGE_DIR / "run_qtn_5g_aelita_one_shot_v5.py"\n'
        f'ONE_SHOT_SHA256 = "{one_shot_sha}"\n',
        "coordinator one-shot",
    )
    text = replace_once(
        text,
        'EVALUATOR = ROOT / "tools/evaluate_qtn_5g_uart_txpath.py"\n'
        'EVALUATOR_SHA256 = "605efb7969bd2463c8af2dc67dfce939b3f08a1791aee69d6f4563f6a2c751c2"\n',
        'EVALUATOR = PACKAGE_DIR / "evaluate_qtn_5g_uart_txpath_v5.py"\n'
        f'EVALUATOR_SHA256 = "{evaluator_sha}"\n',
        "coordinator evaluator",
    )
    text = text.replace(
        'python tools/run_qtn_5g_aelita_uart_capture.py --execute ',
        'python -B outputs/kernel-port/quantenna-5g-auc-muc-oob-v5-20260823/'
        'run_qtn_5g_aelita_uart_capture_v5.py --execute ',
    )
    path = output / "run_qtn_5g_aelita_uart_capture_v5.py"
    write(path, text)
    return path


def artifact(path: Path) -> dict[str, object]:
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/kernel-port/quantenna-5g-auc-muc-oob-v5-20260823",
    )
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    for path, expected in PINNED.items():
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"pinned source mismatch: {path}")

    output.mkdir(parents=True, exist_ok=True)
    pycache = output / "__pycache__"
    if pycache.is_dir():
        shutil.rmtree(pycache)
    subprocess.run(
        [sys.executable, str(RUNTIME_BUILDER), "--output-dir", str(output)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    runtime_manifest = output / "manifest.json"
    runtime = json.loads(runtime_manifest.read_text(encoding="utf-8"))
    runtime_manifest_out = output / "runtime-manifest.json"
    runtime_manifest.replace(runtime_manifest_out)

    evaluator = generate_evaluator(output)
    one_shot = generate_one_shot(
        output, sha256(runtime_manifest_out),
        runtime["artifacts"]["qdrv"]["sha256"],
        runtime["artifacts"]["start"]["sha256"],
        runtime["artifacts"]["stop"]["sha256"],
    )
    coordinator = generate_coordinator(output, sha256(one_shot), sha256(evaluator))

    exact_command = (
        "python -B outputs/kernel-port/quantenna-5g-auc-muc-oob-v5-20260823/"
        "run_qtn_5g_aelita_uart_capture_v5.py --execute "
        "--ack OPENMITRASTAR_QTN_5G_UART_CAPTURE_RAM_ONLY --port COM3 "
        "--router-host 192.168.1.90 --seconds 120 --post-seconds 420 "
        "--capture-seconds 1470"
    )
    files = [
        output / "qdrv-tqe-rxalign-whcopy-auctx-muc-v5.ko",
        output / "om-radio5-start-auctx-muc-v5",
        output / "om-radio5-stop-auctx-muc-v5",
        runtime_manifest_out,
        evaluator,
        one_shot,
        coordinator,
    ]
    manifest = {
        "schema": "openmitrastar.qtn-5g-auc-muc-oob/v5",
        "classification": "ONE-RUN-RAM-ONLY-OOB-AUC-OFF-MUC-TX-DISCRIMINANT",
        "date": "2026-08-23",
        "artifacts": {path.name: artifact(path) for path in files},
        "external_pins": {
            "qtn_runner": "d044a31ff39ee9361a22914e72dc35669ddcbf0624049ef9307027f03af1127f",
            "uart_capture": "7a9da4a416dd4583aeca1299e94768f230cf49dde41d1fa3c3b146c0b4954df2",
        },
        "rollback_requirements": {
            "stop_rc": 0,
            "loglevel_restore_rc": 0,
            "auc_tx_restore_rc": 0,
            "management_ok": True,
            "recovery_clean": True,
            "loglevel_matches_original": True,
        },
        "exact_command": exact_command,
        "single_run": True,
        "flash": False,
        "mtd": False,
        "bootenv": False,
        "hardware_tested": False,
    }
    manifest_path = output / "manifest.json"
    write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    sums = [f"{sha256(path)}  {path.name}" for path in [*files, manifest_path]]
    write(output / "SHA256SUMS", "\n".join(sums) + "\n")
    print(
        "OMQTN5G_AUC_MUC_OOB_V5_BUILD_PASS=1 "
        f"manifest={sha256(manifest_path)} coordinator={sha256(coordinator)} flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
