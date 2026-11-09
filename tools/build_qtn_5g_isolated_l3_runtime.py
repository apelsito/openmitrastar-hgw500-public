#!/usr/bin/env python3
"""Build deterministic RAM-only isolated-L3 variants of radio5 start/stop."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin"
START = SOURCE / "om-radio5-start"
STOP = SOURCE / "om-radio5-stop"
START_SHA = "69cd207da9ced1c3fcc3829913b5e6aad7636ea0e960b59239ce9411011a4f4d"
STOP_SHA = "4c749599172491d85d09f8f4668b1dff5a0d8308d4485f7f325e2372cdf5b1c5"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_exact(text: str, old: str, new: str, count: int = 1) -> str:
    if text.count(old) != count:
        raise SystemExit(f"replacement count mismatch {text.count(old)} != {count}: {old[:80]!r}")
    return text.replace(old, new, count)


def build_start() -> bytes:
    raw = START.read_bytes()
    if sha(raw) != START_SHA:
        raise SystemExit("canonical start hash mismatch")
    text = raw.decode("utf-8")
    if (
        "OMQTN5G_ISOLATED_L3 address=192.168.77.1/24" in text
        and "ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up" in text
        and "brctl addif br0 wifi0" not in text
        and "topology=isolated-l3" in text
    ):
        return raw
    text = replace_exact(
        text,
        "/usr/sbin/om-radio5-stop",
        '${OM_RADIO5_STOP:-/usr/sbin/om-radio5-stop}',
        2,
    )
    text = replace_exact(
        text,
        '[ "$tqe_ring_entries" = 256 ] || refuse beacon-lifetime-requires-tqe256',
        'case "$tqe_ring_entries" in 256|512) ;; *) refuse beacon-lifetime-requires-tqe256 ;; esac',
    )
    text = replace_exact(text, " 'bridge=br0'", "", 2)
    text = replace_exact(
        text,
        '''[ ! -e /sys/class/net/br0/brif/wifi0 ] || refuse wifi0-already-bridged
brctl addif br0 wifi0 || refuse bridge-add-wifi0
[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && \\
\t[ -e /sys/class/net/br0/brif/wifi0 ] || refuse bridge-members
''',
        '''[ ! -e /sys/class/net/br0/brif/wifi0 ] || refuse wifi0-unexpectedly-bridged
ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up >/dev/null 2>&1 || true
ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || refuse isolated-l3-readback
[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && \\
\t[ ! -e /sys/class/net/br0/brif/wifi0 ] || refuse isolated-l3-topology
log 'OMQTN5G_ISOLATED_L3 address=192.168.77.1/24 br0_wifi0=0 eth0_2g=preserved'
''',
    )
    text = replace_exact(
        text,
        '''[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && \\
\t[ -e /sys/class/net/br0/brif/wifi0 ] || refuse bridge-lost''',
        '''[ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && \\
\t[ ! -e /sys/class/net/br0/brif/wifi0 ] || refuse isolated-l3-topology-lost
ifconfig wifi0 2>/dev/null | grep -q '192.168.77.1' || refuse isolated-l3-address-lost''',
    )
    text = text.replace(
        "bridge=br0 members=eth0,wlan0,wifi0",
        "topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0",
    )
    text = text.replace(
        "direct=eth0 bridge=br0 members=eth0,wlan0,wifi0",
        "direct=eth0 topology=isolated-l3 address=192.168.77.1/24 br0_members=eth0,wlan0",
    )
    marker = "# OMQTN5G_ISOLATED_L3_RUNTIME=1\n"
    text = text.replace("#!/bin/ash\n", "#!/bin/ash\n" + marker, 1)
    return text.encode("utf-8")


def build_stop() -> bytes:
    raw = STOP.read_bytes()
    if sha(raw) != STOP_SHA:
        raise SystemExit("canonical stop hash mismatch")
    text = raw.decode("utf-8")
    if "ifconfig wifi0 0.0.0.0" in text and '"$state/ready"' in text:
        return raw
    text = replace_exact(
        text,
        "ifconfig wifi0 down >/dev/null 2>&1 || true",
        "ifconfig wifi0 0.0.0.0 >/dev/null 2>&1 || true\nifconfig wifi0 down >/dev/null 2>&1 || true",
    )
    text = text.replace("#!/bin/ash\n", "#!/bin/ash\n# OMQTN5G_ISOLATED_L3_RUNTIME=1\n", 1)
    return text.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/kernel-port/quantenna-5g-isolated-l3-runtime-20260823",
    )
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    start_a, start_b = build_start(), build_start()
    stop_a, stop_b = build_stop(), build_stop()
    if start_a != start_b or stop_a != stop_b:
        raise SystemExit("runtime build is not reproducible")
    start_path = output / "om-radio5-start-isolated-l3"
    stop_path = output / "om-radio5-stop-isolated-l3"
    start_path.write_bytes(start_a)
    stop_path.write_bytes(stop_a)
    manifest = {
        "schema": "openmitrastar.qtn-5g-isolated-l3-runtime/v1",
        "classification": "RAM-ONLY-NO-BRIDGE-NO-FLASH",
        "source": {"start_sha256": START_SHA, "stop_sha256": STOP_SHA},
        "artifacts": {
            "start": {"file": start_path.name, "bytes": len(start_a), "sha256": sha(start_a)},
            "stop": {"file": stop_path.name, "bytes": len(stop_a), "sha256": sha(stop_a)},
        },
        "network": {
            "wifi0": "192.168.77.1/24",
            "wifi0_in_br0": False,
            "br0_members_preserved": ["eth0", "wlan0"],
            "tqe_ring_entries": 512,
        },
        "reproducible": True,
        "hardware_actions": False,
        "flash": False,
    }
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (output / "manifest.json").write_text(rendered, encoding="utf-8", newline="\n")
    print(
        "OMQTN5G_ISOLATED_L3_RUNTIME_BUILD_PASS=1 "
        f"start={manifest['artifacts']['start']['sha256']} "
        f"stop={manifest['artifacts']['stop']['sha256']} flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
