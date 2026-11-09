# OpenMitraStar F184 integrated capabilities candidate

Date: `2026-09-01`

F184 combines:

- F172 NAPI-128 kernel and `napi_weight=128` telemetry;
- F183 Foundation 1.4 rootfs;
- signed package feed, `lyoko-pkg` and ARC700 pkgbox;
- machine-readable capability registry and responsive Developer matrix.

Only the release identity differs from the F183 rootfs. The experimental F180
storage partition and F181/F182 SPI probe are intentionally excluded so the
physical datapath campaign remains attributable to the F172 kernel change.

Build:

```powershell
.\tools\build_f184_integrated_capabilities.ps1
```

Hardware validation remains `NOT_RUN`; F170 remains installed.

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f184-integrated-capabilities/build/openmitrastar-linux510-q3-persistent-f184-integrated-capabilities-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `5,111,808` bytes
- SHA-256: `5f2ed3b863ed66840e7f2e700ea95e344a309b4e067fba4068f70fc9336c02be`
- Candidate CRC32: `4b900325`
- Full-slot CRC32: `135b1147`
- Full-slot SHA-256:
  `22af6bc7b04b0043abd53039c1efe0262fd231d63b92b24b0f9a08bc7548fe0b`
- Offline tests: `16 passed`
- Repeated build SHA-256: identical

Dry run:

```powershell
.\tools\build_flash_test_f184_integrated.ps1 -SkipBuild
```

`-RunWifiCampaign` runs the three-pass F172 benchmark only after the complete
Foundation, package-manager and capability registry gate succeeds.
