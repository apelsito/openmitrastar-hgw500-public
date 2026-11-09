#!/usr/bin/env python3
"""Build F157 from F156 with wifi0 persistently attached to br0."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f125_5g_assoc_window_guard_from_f124 as f125
import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f156_5g_txba_stable_from_f155 as f156


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f157-5g-persistent-bridge-from-f156"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F157_FROM_F156_5G_PERSISTENT_BRIDGE"

SRC_BUILD = f156.OUT
SRC_BASE = f156.BASE_OUT
QDRV_SHA = f156.QDRV_SHA
WLAN_SHA = f156.WLAN_SHA
MODULE_BUILD = f156.MODULE_BUILD
NEW_QDRV = f156.NEW_QDRV
BUILD_PROFILE = f156.BUILD_PROFILE
MODULE_MANIFEST = f156.MODULE_MANIFEST


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_exact(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"F157 {label} count mismatch: expected {count}, got {actual}")
    return text.replace(old, new)


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    text = replace_exact(
        text,
        "[ ! -e /sys/class/net/br0/brif/wifi0 ] && [ \"$(cat \"$rf\" 2>/dev/null)\" = 1 ] ||\n"
        "\t\trefuse stale-ready-state\n"
        "\tlog 'OMRADIO5_READY state=already-running direct=eth0 radio2g=wlan0 radio5g=wifi0 topology=isolated-l3'",
        "[ -e /sys/class/net/br0/brif/wifi0 ] && [ \"$(cat \"$rf\" 2>/dev/null)\" = 1 ] ||\n"
        "\t\trefuse stale-ready-state\n"
        "\t! ifconfig wifi0 2>/dev/null | grep -q 'inet addr:' || refuse stale-wifi0-ip\n"
        "\tlog 'OMRADIO5_READY state=already-running direct=eth0 radio2g=wlan0 radio5g=wifi0 topology=br0'",
        "already-running topology",
    )
    text = replace_exact(
        text,
        "'driver=madwifi' 'interface=wifi0' 'hw_mode=a' 'channel=36'",
        "'driver=madwifi' 'interface=wifi0' 'bridge=br0' 'hw_mode=a' 'channel=36'",
        "hostapd bridge option",
        count=2,
    )
    text = replace_exact(
        text,
        "log \"OMRADIO5_DRY_RUN_PASS direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0 region=$region channel=36 bw=$bw security=$security_profile psk=$([ \"$security_profile\" = secure ] && printf redacted || printf unused) tqe_ring=$tqe_ring_entries qdrv_profile=$qdrv_profile fwt_ctrl=absent ioss=untouched\"",
        "log \"OMRADIO5_DRY_RUN_PASS direct=eth0 topology=br0 address=br0:192.168.1.90 br0_members=eth0,wlan0,wifi0 region=$region channel=36 bw=$bw security=$security_profile psk=$([ \"$security_profile\" = secure ] && printf redacted || printf unused) tqe_ring=$tqe_ring_entries qdrv_profile=$qdrv_profile fwt_ctrl=absent ioss=untouched\"",
        "dry-run topology",
    )
    text = replace_exact(
        text,
        "[ ! -e /sys/class/net/br0/brif/wifi0 ] || refuse wifi0-unexpectedly-bridged\n"
        "ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up >/dev/null 2>&1 || true\n"
        "ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || refuse isolated-l3-readback\n"
        "[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && \\\n"
        "\t[ ! -e /sys/class/net/br0/brif/wifi0 ] || refuse isolated-l3-topology\n"
        "log 'OMQTN5G_ISOLATED_L3 address=192.168.77.1/24 br0_wifi0=0 eth0_2g=preserved'",
        "[ ! -e /sys/class/net/br0/brif/wifi0 ] || brctl delif br0 wifi0 >/dev/null 2>&1 || true\n"
        "ifconfig wifi0 0.0.0.0 up >/dev/null 2>&1 || refuse wifi0-clear-ip\n"
        "! ifconfig wifi0 2>/dev/null | grep -q 'inet addr:' || refuse wifi0-ip-still-present\n"
        "brctl addif br0 wifi0 >/dev/null 2>&1 || refuse wifi0-bridge-add\n"
        "[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && \\\n"
        "\t[ -e /sys/class/net/br0/brif/wifi0 ] || refuse bridge-topology\n"
        "log 'OMQTN5G_BRIDGE_READY address=br0:192.168.1.90 br0_members=eth0,wlan0,wifi0'",
        "runtime bridge setup",
    )
    text = replace_exact(
        text,
        "[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && \\\n"
        "\t[ ! -e /sys/class/net/br0/brif/wifi0 ] || refuse isolated-l3-topology-lost\n"
        "ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || refuse isolated-l3-address-lost",
        "[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && \\\n"
        "\t[ -e /sys/class/net/br0/brif/wifi0 ] || refuse bridge-topology-lost\n"
        "! ifconfig wifi0 2>/dev/null | grep -q 'inet addr:' || refuse wifi0-address-returned",
        "post-CoC topology",
    )
    text = text.replace(
        "OMRADIO5_VISIBILITY_PROBE direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0",
        "OMRADIO5_VISIBILITY_PROBE direct=eth0 topology=br0 address=br0:192.168.1.90 br0_members=eth0,wlan0,wifi0",
    )
    text = text.replace(
        "OMRADIO5_READY direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0",
        "OMRADIO5_READY direct=eth0 topology=br0 address=br0:192.168.1.90 br0_members=eth0,wlan0,wifi0",
    )
    patched = text.encode("ascii")
    return patched, {
        "entry": engine.START_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "topology": "br0=eth0+wlan0+wifi0",
        "wifi0_ipv4": "none; bridge owns 192.168.1.90/24",
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    replacements: dict[str, bytes] = {}
    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    seen = False
    report: dict[str, object] = {}

    for entry in entries:
        if entry.name == engine.START_ENTRY:
            patched, item = patch_start(entry.data)
            replacements[entry.name] = patched
            report["start_script"] = item
            patched_entries.append(f125.replace_entry(entry, patched))
            seen = True
        elif entry.name == engine.PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)

    if not seen:
        raise SystemExit(f"missing CPIO entry: {engine.START_ENTRY}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {engine.PAD_ENTRY}")

    final_entries: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == engine.HASHES_ENTRY:
            patched, hashes_patch = f122.patch_hashes(entry.data, replacements)
            final_entries.append(f125.replace_entry(entry, patched))
        else:
            final_entries.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {engine.HASHES_ENTRY}")
    report["artifact_hashes"] = hashes_patch

    interim = b"".join(f71.serialize_entry(entry) for entry in final_entries)
    size_delta = start + len(interim) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F157 fixed-size padding cannot absorb delta={size_delta}")
    final_entries[pad_index] = f125.replace_entry(final_entries[pad_index], b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in final_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _entries, new_remainder = f71.parse_first_cpio(result)
    if (
        new_start != start
        or new_remainder != remainder
        or len(result) != len(raw)
        or len(result) - len(new_remainder) != old_cpio_end
    ):
        raise SystemExit("F157 changed fixed payload layout")
    report["fixed_size_compensation"] = {
        "entry": engine.PAD_ENTRY,
        "old_padding_bytes": old_pad_size,
        "new_padding_bytes": new_pad_size,
        "removed_bytes": size_delta,
        "raw_bytes_preserved": True,
        "cpio_end_preserved": True,
    }
    return result, report


@contextlib.contextmanager
def variant_context():
    names = (
        "BUILD_TAG", "OUT", "BASE_OUT", "CLASSIFICATION", "SRC_BUILD",
        "SRC_BASE", "OLD_QDRV_SHA", "NEW_QDRV_SHA", "NEW_QDRV",
        "BUILD_PROFILE", "MODULE_MANIFEST", "WLAN_SHA",
    )
    old = {name: getattr(engine, name) for name in names}
    values = {
        "BUILD_TAG": BUILD_TAG,
        "OUT": OUT,
        "BASE_OUT": BASE_OUT,
        "CLASSIFICATION": CLASSIFICATION,
        "SRC_BUILD": SRC_BUILD,
        "SRC_BASE": SRC_BASE,
        "OLD_QDRV_SHA": QDRV_SHA,
        "NEW_QDRV_SHA": QDRV_SHA,
        "NEW_QDRV": NEW_QDRV,
        "BUILD_PROFILE": BUILD_PROFILE,
        "MODULE_MANIFEST": MODULE_MANIFEST,
        "WLAN_SHA": WLAN_SHA,
    }
    try:
        for name, value in values.items():
            setattr(engine, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    original = engine.patch_cpio
    with variant_context():
        engine.patch_cpio = patch_cpio
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = engine.main()
        finally:
            engine.patch_cpio = original
    if rc:
        return rc

    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    manifest["change_scope"] = {
        "radio2g": "unchanged from F156 and remains in br0",
        "radio5_modules_security_txba": "byte-identical to F156",
        "radio5_start": "wifi0 has no L3 address and joins br0 before hostapd starts",
        "management": "192.168.1.90 remains owned by br0",
        "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F156",
    }
    manifest["runtime_policy"] = {
        "topology": "br0=eth0+wlan0+wifi0",
        "wifi0_ipv4": "none",
        "service": "WPA2-PSK/CCMP with persistent tx_ba_disable=1",
        "expected_effect": "OEM-like transparent LAN service on both radios after boot",
        "persistent_flash_writes": 0,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    sums_path = OUT / "SHA256SUMS"
    lines = []
    for line in sums_path.read_text(encoding="ascii").splitlines():
        _digest, name = line.split("  ", 1)
        path = OUT / name
        lines.append(f"{sha256(path.read_bytes())}  {name}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
