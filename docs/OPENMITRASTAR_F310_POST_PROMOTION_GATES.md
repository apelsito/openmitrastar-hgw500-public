# OpenMitraStar F310 Post-Promotion Gates

Date: 2026-09-04

## Scope

This offline preparation is pinned to the exact F310 device-bound artifact:

- runtime: `lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device`;
- candidate SHA-256: `df451d720d8a959ff79ae6a2377940f6f9c3253f22d00f4b15752827e55ba330`;
- router host-key file: `known_hosts.f310` with strict SSH v2 pinning;
- shared physical lock: `outputs/locks/f301-physical-radio.lock`;
- zero firmware flash, MTD writes or persistent configuration writes.

Preparation and validation performed no router, AELITA, COM3, UART, TFTP,
radio or MTD operation. Physical execution remains explicitly gated.

## Gate Order

1. Multicast and IGMP on 2.4 GHz and 5 GHz.
2. Read-only F295 store-protection observer, loaded only in RAM and removed.
3. Isolated VLAN 4090 outside `br0`.

`run_f310_post_promotion_gates.py` is sequential and fail-fast. It checks for
active F301, F306 or F310 soak evidence before starting and again before every
child. Every child uses the same physical lock, writes a separate evidence
directory and must restore its runtime-only state before returning.

## Files

```text
tools/f310_post_promotion_common.py
tools/run_f310_multicast_igmp_physical.py
tools/f310_store_protection_probe.ps1
tools/f310_vlan_gate.py
tools/run_f310_post_promotion_gates.py
tools/test_f310_post_promotion_gates.py
```

## Offline Preflight

```powershell
python tools\run_f310_post_promotion_gates.py
```

## Future Physical Execution

Only after the exact F310 image is installed and its normal platform gate has
passed:

```powershell
python tools\run_f310_post_promotion_gates.py --execute `
  --ack OPENMITRASTAR_F310_POST_PROMOTION_GATES `
  --controller-interface Ethernet
```

This command does not flash firmware. It runs the three runtime gates in the
fixed order above and stops on the first non-PASS result.

## Offline Result

- Combined F310 regression: `39/39 PASS`.
- Coordinator dry-run: PASS.
- Child preflights: multicast/IGMP PASS, store-protection PASS, VLAN4090 PASS.
- Dry-run evidence:
  `outputs/preflight/f310-post-promotion-20260904T204921Z`.
- `hardware_actions_performed=false`, `persistent_writes=false`,
  `mtd_writes=false`, `flash=false`.
- The packaged `known_hosts.f310` hash remained
  `020d570ac4a811268852fa973f93ad614005646e3ee7e8a8e5419a74283ac845`.
