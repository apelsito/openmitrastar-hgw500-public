# OpenMitraStar F229 Candidate

Date: 2026-09-02

F229 extends the F227 Foundation with a detailed, read-only hardware inventory.

## Artifact

- Bytes: `5210112`
- SHA-256: `32b9114d3a96717f0865993e6e2e9e04fe6213db15a3d88364a1ac04d8d0ff4b`
- Full-slot CRC32: `51071848`
- Full-slot SHA-256: `a258a0dbb5ca084f2279e75c1da9c5adac65a2239b3d0c79706b3ac089454936`
- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f229-device-bound`

## Hardware Surface

- Buttons are shown individually: Wi-Fi 2.4 GHz, Wi-Fi 5 GHz and reset.
- Six LED-class devices are shown individually with raw brightness and maximum.
- The proven Wi-Fi 2.4 GHz LED polarity is reported as active-low.
- Unknown LED polarities remain explicitly unknown; the UI does not infer a
  physical on/off state from raw brightness.
- Temperature and watchdog remain honestly unavailable when the kernel exposes
  no source.
- No LED, GPIO or button write operation is present.

## Evidence

- Foundation and artifact tests: 21 PASS.
- SHA256SUMS: PASS.
- Desktop browser inventory: PASS.
- Mobile 390x844: 3 button rows, 6 LED rows and no overflow.
- Kernel, config and DTB: byte-identical to F227/F222.
- No router, UART, radio or flash operation occurred.

F229 remains hardware `NOT_RUN`.
