from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-2.1-dev"
POLICY = FOUNDATION / "overlay/usr/sbin/om-ipv6-local-policy"
READY = FOUNDATION / "overlay/etc/init.d/S90-ready"
API = FOUNDATION / "overlay/usr/libexec/openmitrastar/om-api-v1"


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def test_policy_recovers_when_bridge_sysctl_appears_late() -> None:
    scratch = ROOT / ".codex_tmp"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ipv6-late-", dir=scratch) as directory:
        root = Path(directory)
        compatible = root / "compatible"
        conf = root / "conf"
        state = root / "state.json"
        compatible.write_text("mitrastar,hgw-500bna-qcv2\0qtn,topaz\0", encoding="utf-8")
        for name in ("all", "default", "eth0"):
            target = conf / name / "disable_ipv6"
            target.parent.mkdir(parents=True)
            target.write_text("0\n", encoding="ascii")
        command = (
            f"set -eu; (sleep 1; mkdir -p '{wsl_path(conf / 'br0')}'; printf '0\\n' >'{wsl_path(conf / 'br0/disable_ipv6')}') & "
            f"OM_IPV6_COMPATIBLE_FILE='{wsl_path(compatible)}' OM_IPV6_CONF_ROOT='{wsl_path(conf)}' "
            f"OM_IPV6_STATE_FILE='{wsl_path(state)}' OM_IPV6_WAIT_SECONDS=3 sh '{wsl_path(POLICY)}'"
        )
        proc = subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", command], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
        assert proc.returncode == 0, proc.stderr
        for name in ("all", "default", "eth0", "br0"):
            assert (conf / name / "disable_ipv6").read_text(encoding="ascii").strip() == "1"
        payload = json.loads(state.read_text(encoding="ascii"))
        assert payload["status"] == "pass"
        assert payload["wait_seconds"] == 3


def test_policy_still_fails_when_bridge_never_appears() -> None:
    scratch = ROOT / ".codex_tmp"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ipv6-missing-", dir=scratch) as directory:
        root = Path(directory)
        compatible = root / "compatible"
        conf = root / "conf"
        compatible.write_text("mitrastar,hgw-500bna-qcv2\0", encoding="utf-8")
        for name in ("all", "default", "eth0"):
            target = conf / name / "disable_ipv6"
            target.parent.mkdir(parents=True)
            target.write_text("0\n", encoding="ascii")
        command = (
            f"OM_IPV6_COMPATIBLE_FILE='{wsl_path(compatible)}' OM_IPV6_CONF_ROOT='{wsl_path(conf)}' "
            f"OM_IPV6_STATE_FILE='{wsl_path(root / 'state.json')}' OM_IPV6_WAIT_SECONDS=1 sh '{wsl_path(POLICY)}'"
        )
        proc = subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", command], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
        assert proc.returncode != 0
        assert "missing-br0" in proc.stderr


def test_ready_retries_and_status_exposes_degraded_services() -> None:
    ready = READY.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    assert 'ipv6_attempt=0' in ready
    assert 'OM_IPV6_WAIT_SECONDS=10' in ready
    assert 'ipv6_attempt" -lt 3' in ready
    assert 'om-degraded-clear S34-ipv6-local-policy' in ready
    assert "degraded_services_json" in api
    assert '"degraded_services"' in api
