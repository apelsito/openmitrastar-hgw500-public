# OpenMitraStar F184 GO/NO-GO

Decision date: `2026-09-01`

## Decision

`GO_PENDING_EXPLICIT_HARDWARE_AUTHORIZATION`

F184 is the preferred next physical candidate. It supersedes a separate F172
promotion because it uses the exact F172 kernel while adding only inactive or
read-only product features from F183.

## Current hardware baseline

- Installed firmware: F170 in physical `mtd4/linux_live`.
- Current full-slot CRC32: `d77c9c82` from the last verified readback.
- Fresh read-only gate: PASS.
- SSH, SquashFS root, `/persist` read-only, both radios, 5 GHz power, bridge and
  fatal-marker checks: PASS.
- Evidence:
  `outputs/postflash/f170-pre-f184-go-no-go-20260901T141704Z/status.json`.

## Exact candidate

- Path:
  `work/mission-state/q3-persistent-composite-f184-integrated-capabilities/build/openmitrastar-linux510-q3-persistent-f184-integrated-capabilities-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `5,111,808` bytes.
- SHA-256: `5f2ed3b863ed66840e7f2e700ea95e344a309b4e067fba4068f70fc9336c02be`.
- Candidate CRC32: `4b900325`.
- Full-slot CRC32: `135b1147`.
- Full-slot SHA-256:
  `22af6bc7b04b0043abd53039c1efe0262fd231d63b92b24b0f9a08bc7548fe0b`.
- Bootbase contract and slot fit: PASS.
- Repeated build SHA-256: identical.
- Hardware validation: `NOT_RUN`.

## Included

- F172 EMAC NAPI weight `128` with `napi_weight=128` telemetry.
- F177 `lyoko-pkg`, static ARC700 pkgbox and two signed packages.
- F183 capability registry and responsive Foundation 1.4 UI.
- F171 health/no-op transaction corrections.

## Explicitly excluded

- F175 multicast/IGMP kernel configuration.
- F178/F180 `lyoko_store` partition split.
- F181/F182 SPI probe.
- Runtime network package downloads.
- Any write outside physical `mtd4/linux_live`.

## Flash and acceptance sequence

```powershell
.\tools\build_flash_test_f184_integrated.ps1 `
  -Execute -SkipBuild -RunWifiCampaign
```

The wrapper:

1. verifies the exact F184 artifact and expected F170 full-slot CRC;
2. acquires `topaz>` automatically;
3. transfers through UART/YMODEM;
4. erases and writes physical `mtd4` only;
5. verifies readback and protected partitions;
6. boots F184;
7. validates Foundation, NAPI-128, package manager and capability registry;
8. runs three matched 32 MiB bidirectional 2.4 GHz tests when
   `-RunWifiCampaign` is selected.

Rollback remains manual UART `ATGO` to preserved `mtd3/linux_safety`.
