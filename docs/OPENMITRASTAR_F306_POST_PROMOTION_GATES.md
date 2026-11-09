# OpenMitraStar F306 Post-Promotion Gates

Date: 2026-09-04

## Scope

The post-promotion suite is pinned to:

- runtime `lyoko-foundation-6.7.3-f306-unified-product-device`;
- candidate SHA-256 `a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2`;
- shared physical lock `outputs/locks/f301-physical-radio.lock`;
- persistent SSH host-key files and the SSH v2 policy;
- zero persistent writes, zero MTD writes and zero firmware writes.

## Gate Order

1. Multicast and IGMP on 2.4 GHz and 5 GHz.
2. Read-only store-protection observer loaded only in RAM.
3. Isolated VLAN 4090 outside `br0`.

The coordinator checks that no F301 or F306 soak is active before execution and
again before every gate. Each child acquires the shared physical lock, keeps its
own immutable evidence directory, restores its runtime snapshot and disarms its
watchdogs. A non-PASS result stops the sequence immediately.

## Commands

Offline preflight:

```powershell
python tools\run_f306_post_promotion_gates.py
```

Physical execution is intentionally separate and requires the exact
acknowledgement. It must only be used after F306 promotion has passed:

```powershell
python tools\run_f306_post_promotion_gates.py --execute `
  --ack OPENMITRASTAR_F306_POST_PROMOTION_GATES `
  --controller-interface Ethernet
```

The preparation described here executed no SSH, UART, radio, flash or MTD
operation.

