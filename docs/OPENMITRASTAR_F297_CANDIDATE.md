# OpenMitraStar F297 Full offline multicast hold

Date: 2026-09-04

F297 restores the guarded multicast/IGMP certification backend to the current
F293/F294/F296 line. Live inspection proved that the installed F292 kernel has
bridge IGMP support but its rootfs does not contain `/usr/sbin/om-multicast-cert`.

## Artifact

- Runtime: `lyoko-foundation-6.5.4-f297-multicast-harness-device`
- Bytes: `5267456`
- SHA-256: `742523351bf22c49e6730e56b4fbc1c45123487588e99ecb2200d363b81dfa15`
- Full-slot CRC32: `fb0ba260`
- Full-slot SHA-256: `5aaa1f3a7b5871c8ef707a02cb05e4617b5b6e5a4d997e50e1a172d61dc87c8f`
- Bootbase and slot-fit contracts: PASS.
- Candidate eligible: false.
- Flash supported: false.
- Hardware boot: NOT RUN.

## Multicast safety contract

- Nothing runs at boot.
- Applying the test requires `OPENMITRASTAR_MULTICAST_CERT_V1`.
- The original bridge snooping, querier and multicast-router values are saved.
- An independent 300-second watchdog restores those exact values.
- Manual rollback is idempotent and removes its transient state.
- The backend contains no MTD, persistent-storage or boot-environment write.

## Physical test runner

`tools/run_f297_multicast_igmp_physical.py` is prepared for sequential tests on
the one available Windows Wi-Fi client:

1. enable bridge snooping and querier temporarily;
2. connect AELITA to 2.4 GHz using the runtime PSK without logging it;
3. send multicast in both directions and measure delivery;
4. restore AELITA to `MOVISTAR-WIFI6-A348`;
5. repeat on 5 GHz;
6. restore the exact original bridge values in all outcomes.

The result contains no client MAC, BSSID or PSK. Dry-run is PASS and confirms
that Lyoko and AELITA SSH are reachable. Execution is refused unless the exact
F297 runtime is installed.

The generated PowerShell sender/receiver scripts pass parser validation, and
the controller-side multicast implementation completed an 8/8 packet local
socket smoke test. The physical bridge traversal remains NOT RUN.

Evidence:

- `outputs/preflight/f297-multicast-20260904T020051Z/plan.json`
- `outputs/preflight/f297-multicast-local-smoke-20260904/result.json`

## Dependency boundary

F297 inherits the F293 telemetry kernel and therefore remains an offline hold
until F293 completes its physical 2.4/5 GHz campaign.
