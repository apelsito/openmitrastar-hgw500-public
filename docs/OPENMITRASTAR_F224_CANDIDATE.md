# OpenMitraStar F224 Candidate

Date: 2026-09-02

F224 is the next private Foundation candidate built from the installed F222
baseline. It introduces `lyoko.radio.settings/v1`, making the backend contract
the source of truth for Wi-Fi controls, allowed values, recommendations,
tradeoffs, certification state and blocked reasons.

## Artifact

- Bytes: `5206016`
- SHA-256: `7b1662834a3c56632bffafc4a062a1fbd7ebcb4b7e66dd9163e458b8212e2d73`
- Full-slot CRC32: `458604b1`
- Full-slot SHA-256: `0da70861afe77b38a2c038efaed3843ce93a4e20ecd34c2d7be2875be11b90a1`
- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f224-device-bound`

## Scope

- The 2.4 GHz channel selector is generated from channels 1 through 13.
- The 5 GHz selector exposes only certified non-DFS channels 36, 40, 44 and 48.
- DFS channels remain visible in the machine contract as candidates requiring
  certification, but cannot be selected by the UI.
- SSID, channel and bandwidth remain the only writable settings.
- TX power, regulatory region, DFS and security remain explicitly locked with
  machine-readable reasons.
- The setting inspector consumes the same contract as the controls instead of
  relying only on labels embedded in JavaScript.

## Preservation

- Kernel LZMA: byte-identical to F222.
- Kernel config: byte-identical to F222.
- DTB and rootfs/store split: byte-identical to F222.
- Package manager, signed feed, stable SSH identity and storage policy:
  preserved.
- No UART, router, radio or flash action occurred during the build.

## Evidence

- Foundation and contract tests: 19 PASS.
- SHA256SUMS: PASS.
- Desktop browser rendering: PASS.
- Mobile 390x844 rendering: PASS with no horizontal or field overflow.
- Dynamic channel contracts: PASS for both bands.
- Emulator stage, apply, reload and rollback: PASS; channel restored to 1.

F224 remains `NOT_RUN` on hardware. It must not replace the F223 datapath
experiment; the two changes should be combined only after F223 proves the RX
ring improvement physically.
