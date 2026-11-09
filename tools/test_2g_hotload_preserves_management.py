#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ROOT / "tools/apply_2g_be_tx_summary_remote.sh",
    ROOT / "tools/apply_2g_queue_guard_rootfs_remote.sh",
    ROOT / "tools/apply_2g_speed_profile_rootfs_remote.sh",
]


def test_2g_hotloads_do_not_destroy_management_bridge() -> None:
    for script in SCRIPTS:
        text = script.read_text(encoding="utf-8")
        assert "/usr/sbin/om-radio-stop" not in text, script
        assert "brctl delbr" not in text, script
        assert 'brctl delif br0 eth0' not in text, script
        assert '[ -e /sys/class/net/br0/brif/eth0 ] || fail br0-lost-eth0' in text, script


def test_2g_hotloads_only_detach_wlan0_before_module_reload() -> None:
    for script in SCRIPTS:
        text = script.read_text(encoding="utf-8")
        stop = text[text.index("stop_radio2g_preserve_management()") : text.index("[ \"$release\"")]
        assert "hostapd_cli" in stop, script
        assert "brctl delif br0 wlan0" in stop, script
        assert "ifconfig wlan0 down" in stop, script
        assert "ifconfig br0 192.168.1.90 netmask 255.255.255.0 up" in stop, script
        assert "route add default gw 192.168.1.1 dev br0" in stop, script
