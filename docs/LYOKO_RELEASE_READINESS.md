# Lyoko release readiness

Release readiness is generated from current artifacts and a live read-only SSH
probe. Offline builds never count as hardware PASS.

Run:

```powershell
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
python tools\audit_lyoko_release_readiness.py `
  --output-dir "outputs\release-readiness\$stamp"
```

The report tracks persistent boot, recovery, both radios, datapath performance,
DFS, Foundation, packages, VLAN, IGMP, hardware controls, soak and museum
evidence. `lyoko-v1` is ready only when every mandatory requirement is `PASS`.

## Current snapshot - 2026-09-03

The live F282-aware audit reports:

- `5 PASS`
- `8 PARTIAL`
- `2 BLOCKED`
- `2 NOT_RUN`

Current PASS areas are persistent Linux 5.10 boot, exact SquashFS layout,
authenticated Developer web/API, the signed ARC700/uClibc package lifecycle
and the generated museum. Current F282 SSID visibility remains partial because
the passive Windows scan stayed on A348, although both AP states and TX counters
advanced after the successful hostapd restart.

The remaining hard blockers are independent `mtd3` recovery and VLAN test
topology. Multicast/IGMP is no longer blocked: the router, AELITA and controller
preflight pass, so its real traffic test is ready to run when changing client
connectivity is acceptable.

Canonical report:
`outputs/release-readiness/f285-current-20260903T220000Z/REPORT.md`.
