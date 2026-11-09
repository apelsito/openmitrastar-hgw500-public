from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f189_multicast_igmp as f189  # noqa: E402


def test_network_fragment_is_minimal() -> None:
    lines = set(f189.CONFIG.read_text(encoding="utf-8").splitlines())
    assert "CONFIG_IP_MULTICAST=y" in lines
    assert "CONFIG_BRIDGE_IGMP_SNOOPING=y" in lines
    assert "CONFIG_VLAN_8021Q=y" in lines
    assert "# CONFIG_IP_MROUTE is not set" in lines
    assert "# CONFIG_VLAN_8021Q_GVRP is not set" in lines
    assert "# CONFIG_VLAN_8021Q_MVRP is not set" in lines


def test_capability_remains_unproven() -> None:
    registry = json.loads((f189.OVERLAY / "etc/lyoko/capabilities.json").read_text(encoding="utf-8"))
    igmp = next(item for item in registry["items"] if item["id"] == "network.igmp")
    assert igmp["state"] == "certification_required"
    assert "no-traffic-proof" in igmp["evidence"]


def test_runtime_policy_fails_closed_with_snooping_disabled() -> None:
    policy = (f189.OVERLAY / "usr/sbin/om-multicast-policy").read_text(encoding="utf-8")
    init = (f189.OVERLAY / "etc/init.d/S33-multicast-policy").read_text(encoding="utf-8")
    api = (f189.OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    assert "multicast_snooping" in policy
    assert "disabled-until-certified" in policy
    assert "printf '%s\\n' 0" in policy
    assert "exec /usr/sbin/om-multicast-policy" in init
    assert '"multicast"' in api
    assert "bridge mdb" not in policy
    ready = (f189.OVERLAY / "etc/init.d/S90-ready").read_text(encoding="utf-8")
    assert "om-multicast-policy" in ready
    assert "om-degraded-clear S33-multicast-policy" in ready


def test_runtime_policy_disables_snooping_in_sandbox() -> None:
    scratch = ROOT / ".codex_tmp"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lyoko-multicast-", dir=scratch) as directory:
        root = Path(directory)
        snooping = root / "multicast_snooping"
        state = root / "state"
        snooping.write_text("1\n", encoding="ascii")
        script = f189.OVERLAY / "usr/sbin/om-multicast-policy"
        command = (
            f"OM_MULTICAST_STATE_DIR='{f189.wsl_path(state)}' "
            f"OM_MULTICAST_SNOOPING_PATH='{f189.wsl_path(snooping)}' "
            f"sh '{f189.wsl_path(script)}'"
        )
        proc = subprocess.run(["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", command], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        assert proc.returncode == 0, proc.stderr
        assert snooping.read_text(encoding="ascii").strip() == "0"
        assert "policy=disabled-until-certified" in (state / "multicast.env").read_text(encoding="ascii")


def test_built_contract() -> None:
    manifest_path = f189.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f189.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    config = (f189.OUT / f"{f189.BASE}.config").read_text(encoding="utf-8")
    assert manifest["schema"] == "openmitrastar.f189-multicast-igmp/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["napi_binary_contract"]["weight"] == 128
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] != source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert "CONFIG_IP_MULTICAST=y\n" in config
    assert "CONFIG_BRIDGE_IGMP_SNOOPING=y\n" in config
    assert "CONFIG_VLAN_8021Q=y\n" in config
    assert "# CONFIG_IP_MROUTE is not set\n" in config
    assert manifest["physical_validation"]["status"] == "NOT_RUN"


def test_builder_has_no_runtime_policy_or_flash_actions() -> None:
    source = Path(f189.__file__).read_text(encoding="utf-8")
    for forbidden in ("bridge mdb", "ip link add link", "flash_erase", "mtd_debug", "fw_setenv", "COM3"):
        assert forbidden not in source
