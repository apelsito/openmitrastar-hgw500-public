from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "versions/lyoko-foundation-5.2-f252/overlay/usr/sbin/om-config-store"


def wsl(path: Path) -> str:
    value = path.resolve()
    return f"/mnt/{value.drive[0].lower()}/{value.as_posix()[3:]}"


def run(root: Path, command: str) -> subprocess.CompletedProcess[str]:
    env = f"OM_CONFIG_STORE_TEST_MODE=1 OM_CONFIG_STORE_MOUNT={wsl(root / 'persist')} OM_CONFIG_STORE_ROOT={wsl(root / 'persist/openmitrastar/config')} OM_CONFIG_STORE_ACTIVE={wsl(root / 'active.conf')} OM_CONFIG_STORE_FEATURE={wsl(root / 'feature')} OM_CONFIG_STORE_MOUNTS={wsl(root / 'mounts')}"
    return subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", f"{env} sh {shlex.quote(wsl(STORE))} {command}"], text=True, capture_output=True, check=False)


def setup(root: Path) -> None:
    (root / "persist/openmitrastar/config").mkdir(parents=True, exist_ok=True)
    (root / "feature").write_text("OPENMITRASTAR_CONFIG_PERSIST=1\n", encoding="ascii", newline="\n")
    (root / "mounts").write_text(f"/dev/mtdblock4 {wsl(root / 'persist')} jffs2 rw,relatime 0 0\n", encoding="ascii", newline="\n")


def test_two_slot_commit_load_and_rollback() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-config-store-") as directory:
        root = Path(directory); setup(root)
        active = root / "active.conf"
        active.write_text("CONFIG_SCHEMA=1\nRADIO2_CHANNEL=1\nRADIO5_CHANNEL=36\n", encoding="ascii", newline="\n")
        first = run(root, "commit"); assert first.returncode == 0, first.stderr
        assert "slot=A" in first.stdout
        active.write_text("CONFIG_SCHEMA=1\nRADIO2_CHANNEL=6\nRADIO5_CHANNEL=44\n", encoding="ascii", newline="\n")
        second = run(root, "commit"); assert second.returncode == 0, second.stderr
        assert "slot=B" in second.stdout and "RADIO2_CHANNEL=6" in run(root, "load").stdout
        rolled = run(root, "rollback"); assert rolled.returncode == 0, rolled.stderr
        assert "slot=A" in rolled.stdout and "RADIO2_CHANNEL=1" in run(root, "load").stdout


def test_store_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-config-store-") as directory:
        root = Path(directory); setup(root)
        (root / "active.conf").write_text("CONFIG_SCHEMA=1\nWIFI_PSK=secret\n", encoding="ascii", newline="\n")
        invalid = run(root, "commit"); assert invalid.returncode != 0 and "invalid-config-content" in invalid.stderr
        (root / "feature").write_text("OPENMITRASTAR_CONFIG_PERSIST=0\n", encoding="ascii", newline="\n")
        blocked = run(root, "commit"); assert blocked.returncode != 0 and "feature-disabled" in blocked.stderr
        (root / "mounts").write_text(f"/dev/mtdblock4 {wsl(root / 'persist')} jffs2 ro,relatime 0 0\n", encoding="ascii", newline="\n")
        assert run(root, "load").returncode != 0


def test_status_reports_unavailable_or_corrupt_without_aborting() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-config-store-") as directory:
        root = Path(directory); setup(root)
        (root / "mounts").write_text("", encoding="ascii")
        unavailable = run(root, "status")
        assert unavailable.returncode == 0
        assert '"store_ready":false' in unavailable.stdout
        setup(root)
        (root / "persist/openmitrastar/config/current").write_text("A\n", encoding="ascii", newline="\n")
        (root / "persist/openmitrastar/config/A.conf").write_text("CONFIG_SCHEMA=1\nWIFI_PSK=forbidden\n", encoding="ascii", newline="\n")
        (root / "persist/openmitrastar/config/A.meta").write_text("sha256=bad\n", encoding="ascii", newline="\n")
        corrupt = run(root, "status")
        assert corrupt.returncode == 0
        assert '"active_valid":false' in corrupt.stdout
