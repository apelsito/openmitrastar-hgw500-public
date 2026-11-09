from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/q3_multicast_igmp_cert_remote.sh"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def run(root: Path, action: str) -> subprocess.CompletedProcess[str]:
    env = (
        f"OM_MC_STATE_DIR={shlex.quote(wsl_path(root / 'state'))} "
        f"OM_MC_SNOOPING_PATH={shlex.quote(wsl_path(root / 'snooping'))} "
        f"OM_MC_QUERIER_PATH={shlex.quote(wsl_path(root / 'querier'))} "
        f"OM_MC_ROUTER_PATH={shlex.quote(wsl_path(root / 'router'))} "
        "OM_MC_WATCHDOG_SECONDS=0 "
    )
    return subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", env + f"sh {shlex.quote(wsl_path(SCRIPT))} {action}"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )


def test_multicast_policy_apply_and_rollback_are_exact() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-multicast-") as directory:
        root = Path(directory)
        (root / "snooping").write_bytes(b"0\n")
        (root / "querier").write_bytes(b"0\n")
        (root / "router").write_bytes(b"1\n")
        applied = run(root, "apply")
        assert applied.returncode == 0, applied.stderr
        assert "OMMC_APPLY_PASS" in applied.stdout
        assert (root / "snooping").read_text().strip() == "1"
        assert (root / "querier").read_text().strip() == "1"
        assert (root / "router").read_text().strip() == "0"
        rolled_back = run(root, "rollback")
        assert rolled_back.returncode == 0, rolled_back.stderr
        assert "OMMC_ROLLBACK_PASS" in rolled_back.stdout
        assert (root / "snooping").read_text().strip() == "0"
        assert (root / "querier").read_text().strip() == "0"
        assert (root / "router").read_text().strip() == "1"
        assert not (root / "state").exists()


def test_multicast_policy_contains_no_persistent_or_flash_writes() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "multicast_snooping" in source
    assert "multicast_querier" in source
    assert "multicast_router" in source
    assert "watchdog_seconds" in source
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "/persist", "/dev/mtd"):
        assert forbidden not in source
