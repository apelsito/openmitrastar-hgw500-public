# Lyoko network certification

The certification path separates compiled capability, active configuration
and traffic proof. Presence of a module or procfs file is not a traffic PASS.

Run the read-only audit:

```powershell
python tools\audit_lyoko_network_capabilities.py `
  --output-dir outputs\certification\network-capabilities-f170
```

Current F276 runtime evidence, with kernel capability provenance inherited from
the physically verified F222 line:

- VLAN 802.1Q: compiled, no VLAN interface configured yet.
- IPv4 multicast: compiled.
- Bridge IGMP snooping: compiled; bridge controls are present.
- Runtime bridge policy: snooping `0`, querier `0`, multicast-router `1`.
- Observed groups: five IPv4 IGMP entries and twelve IPv6 entries.
- Quantenna regulatory region: Spain.
- DFS CAC and radar handling: not tested; channel 36 is not DFS evidence.

No additional kernel enablement is required for VLAN or IGMP. Certification
still requires real tagged traffic, multicast joins/leaves and forwarding,
bridge membership checks, packet-loss measurement, and DFS CAC/radar evidence.
No test may alter `mtd3`, `mtd5`, bootloader or environment.

The first configuration-only experiment is F175:

```powershell
.\tools\prepare_f175_network_config.ps1
```

It enables only IPv4 multicast and bridge IGMP/MLD snooping while deliberately
leaving multicast routing, GVRP and MVRP disabled. F175 is not a firmware image
and cannot be flashed until it is rebased onto an accepted datapath kernel.

Resolved configuration SHA-256:
`cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e`.

Latest kernel/network capability audit:
`outputs/certification/network-capabilities-f222-20260902T104854Z/audit.json`.

Current traffic-lab preflight:
`outputs/certification/network-traffic-preflight-f276-20260903T124800Z/preflight.json`.

- Router SSH and AELITA SSH both pass. Multicast/IGMP is `READY`: the remaining
  work is a real sender/receiver test where traffic actually traverses Lyoko.
- VLAN traffic is blocked because the controller has one active LAN interface;
  retagging it would remove the independent management and rollback path.
- The Ethernet adapter does expose an 802.1Q VLAN-ID property, so the remaining
  VLAN blocker is test topology, not driver capability.

The router-side multicast policy harness is ready offline at
`tools/q3_multicast_igmp_cert_remote.sh`. It snapshots all three bridge knobs,
enables `snooping=1`, `querier=1`, `router=0`, arms an automatic rollback
watchdog and restores the exact previous values. Its sandbox apply/rollback
test passes. It is not installed in F276 and has not been staged or executed on
the physical router. It must be integrated into a later versioned rootfs before
the physical traffic campaign; no ad-hoc RAM upload is part of the normal
release path.
