# OpenMitraStar F276 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.3.1-f276-qtn-plan-api-fix-device`
- Target: physical `mtd4/linux_live`
- Candidate bytes: `5259264`
- Candidate SHA-256: `678bb33018905939d07da33c39a988cc78f66a9f1488751c44d24aac0ee2dced`
- Full-slot CRC32: `04a21521`
- Full-slot SHA-256: `aad63e4690520be876821f01fa13021d13e6618277b07e409129bdf558e8fe6b`
- Bootbase TFTP write/readback and protected-partition checks: PASS
- Platform gate: PASS

## 5 GHz planning interface

F276 fixes the authenticated `POST /api/v1/radios/5g/plan` route. A physical
request for channel 44 and 40 MHz returned:

- `mutation_required=true`;
- `apply_allowed=false`;
- `dfs_requested=false`;
- PHY mode change required;
- WEXT channel change required;
- hostapd-qtn reconfiguration required.

The radio status was byte-for-byte identical before and after the request, and
the fatal marker count remained zero. The Developer UI can therefore inspect
the exact operation plan while the actual 5 GHz apply path remains disabled.

## Current boundary

The installed step runner has physically proved `rf-write-same` and
`interface-up-same`. The next unproven operation is `mode-write-same`, which
must run with UART capture and physical power-cycle recovery available.

Evidence:

- `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f276-device-bound\flash-one-shot-20260903T120357Z\result.json`
- `outputs/postflash/f276-device-20260903T120347Z/`
- `outputs/postflash/f276-qtn-plan-20260903-140735/router.log`

