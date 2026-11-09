# OpenMitraStar F179 integrated candidate

Date: `2026-09-01`

F179 combines two already isolated offline branches:

- F172 kernel: EMAC NAPI weight `128`, exposed as `napi_weight=128`;
- F177 rootfs: Foundation 1.2, signed feed, ARC700 pkgbox and volatile
  `lyoko-pkg`.

The F177 rootfs changes only its release identity to F179. Radios, TQE, bridge,
rates, security and flash layout remain unchanged. The proposed F178 storage
split is deliberately excluded.

F179 is intended to reduce the eventual hardware cycle to one promotion while
retaining F172 as the isolated datapath reference.

Build:

```powershell
.\tools\build_f179_integrated_candidate.ps1
```

Hardware validation remains `NOT_RUN`; F170 remains installed.

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f179-integrated-napi-package-manager/build/openmitrastar-linux510-q3-persistent-f179-integrated-napi-package-manager-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `5,107,712` bytes
- SHA-256: `dccba4e5f76d2f29aef930b3a0d11b2b22fd7268a35b5d2d6fd7f43127fd1af3`
- Candidate CRC32: `ccf5d923`
- Full-slot CRC32: `7018e327`
- Full-slot SHA-256:
  `e96728621a537fd118775725fc053c685bd6d4892c833d1cd0d13bdeedbd710f`
- Offline tests: `16 passed`

Guarded dry run:

```powershell
.\tools\build_flash_test_f179_integrated.ps1 -SkipBuild
```

The optional `-RunWifiCampaign` continues automatically into the three-run
F172 physical benchmark only after the integrated post-flash gate passes.

## Extracted runtime proof

The final F179 SquashFS was extracted and exercised with its real paths:

- `/api/v1/packages`: PASS, signed feed visible;
- `lyoko-pkg list`: two packages;
- `lyoko-pkg verify lyoko-netdiag`: PASS;
- volatile install under `/run`: PASS;
- package execution: PASS;
- package removal and cleanup: PASS;
- release identity `lyoko-foundation-1.3-f179`: PASS;
- kernel contains `napi_weight=%u`: PASS.

This is still host-side execution with an equivalent native command shim. The
ARC700 `pkgbox` binary itself remains pending physical execution.
