from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "versions/lyoko-foundation-6.3.3-f278-multicast-cert-harness/overlay/usr/sbin/om-multicast-cert"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def run(root: Path, action: str, *, ack: bool = False, watchdog: int = 30) -> subprocess.CompletedProcess[str]:
    env = (
        f"OM_MC_STATE_DIR={shlex.quote(wsl_path(root / 'state'))} "
        f"OM_MC_LOCK_DIR={shlex.quote(wsl_path(root / 'lock'))} "
        f"OM_MC_FEATURE={shlex.quote(wsl_path(root / 'feature'))} "
        f"OM_MC_SNOOPING_PATH={shlex.quote(wsl_path(root / 'snooping'))} "
        f"OM_MC_QUERIER_PATH={shlex.quote(wsl_path(root / 'querier'))} "
        f"OM_MC_ROUTER_PATH={shlex.quote(wsl_path(root / 'router'))} "
        f"OM_MC_WATCHDOG_SECONDS={watchdog} "
        f"OM_MC_SELF={shlex.quote(wsl_path(SCRIPT))} "
    )
    if ack:
        env += "OM_MC_ACK=OPENMITRASTAR_MULTICAST_CERT_V1 "
    return subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", env + f"sh {shlex.quote(wsl_path(SCRIPT))} {action}"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )


def fixture(root: Path) -> None:
    (root / "feature").write_text("OPENMITRASTAR_MULTICAST_CERT=1\n", encoding="ascii")
    (root / "snooping").write_text("0\n", encoding="ascii")
    (root / "querier").write_text("0\n", encoding="ascii")
    (root / "router").write_text("1\n", encoding="ascii")


def test_status_is_json_and_read_only() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-multicast-status-") as directory:
        root = Path(directory)
        fixture(root)
        result = run(root, "status")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["available"] is True
        assert payload["active"] is False
        assert payload["snooping"] == "0"
        assert payload["querier"] == "0"
        assert payload["router"] == "1"
        assert not (root / "state").exists()


def test_apply_requires_exact_ack() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-multicast-ack-") as directory:
        root = Path(directory)
        fixture(root)
        result = run(root, "apply")
        assert result.returncode != 0
        assert json.loads(result.stdout)["error"] == "acknowledgement-required"
        assert (root / "snooping").read_text().strip() == "0"
        assert (root / "querier").read_text().strip() == "0"
        assert (root / "router").read_text().strip() == "1"


def test_apply_and_rollback_restore_exact_values() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-multicast-cycle-") as directory:
        root = Path(directory)
        fixture(root)
        applied = run(root, "apply", ack=True)
        assert applied.returncode == 0, applied.stderr
        assert json.loads(applied.stdout)["active"] is True
        assert (root / "snooping").read_text().strip() == "1"
        assert (root / "querier").read_text().strip() == "1"
        assert (root / "router").read_text().strip() == "0"
        rolled_back = run(root, "rollback")
        assert rolled_back.returncode == 0, rolled_back.stderr
        assert json.loads(rolled_back.stdout)["restored"] is True
        assert (root / "snooping").read_text().strip() == "0"
        assert (root / "querier").read_text().strip() == "0"
        assert (root / "router").read_text().strip() == "1"
        assert not (root / "state").exists()


def test_harness_has_no_persistent_or_flash_write_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/persist", "/dev/mtd", "/mnt/ccc"):
        assert forbidden not in source
    assert "OPENMITRASTAR_MULTICAST_CERT_V1" in source
    assert "rollback-watchdog" in source
    assert "rollback watchdog" in source
    assert "acquire_lock" in source
