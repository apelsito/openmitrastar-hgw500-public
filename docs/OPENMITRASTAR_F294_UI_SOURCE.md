# OpenMitraStar F294 hardware RX UI source

Date: 2026-09-04

F294 is an offline successor hold for the F293 hardware RX-demand telemetry.
It is packaged for reproducibility but explicitly marked non-eligible and
non-flashable until F293 has completed its physical campaign.

## Exact offline artifact

- Runtime: `lyoko-foundation-6.5.2-f294-emac-hw-rx-ui-device`
- Bytes: `5263360`
- SHA-256: `60a5ffc05a384aca112c998887958f7cc6c4e40124f3aece6bb5bc4ec17c16e3`
- Full-slot CRC32: `2c852b72`
- Full-slot SHA-256: `04774f3428aea41edff0c5605e92385ec839846560a98a7490770f83184ada51`
- Candidate eligible: false.
- Flash supported: false.
- Hardware boot: NOT RUN.

## User-visible change

The Developer diagnostics page now renders the receive path as five explicit
stages:

`Entrada MAC -> DMA -> Descriptores -> NAPI -> Recuperacion`

It adds six selectable metrics for physical MAC frames, MAC progress samples,
age of the last physical ingress, DMA missed frames, counter-read failures and
physical ingress immediately before an RX restart. Every metric provides a
plain-language explanation and a health rule.

## Validation

- Foundation and F294-specific suites: 39 PASS.
- JavaScript syntax: PASS.
- Frontend identity: PASS (`6.5.2`).
- Desktop viewport: 18 metrics, five path stages, no horizontal overflow.
- Mobile viewport `390x844`: no horizontal overflow; path and metrics collapse
  to one column.
- Metric selection updates the explanation panel.
- Browser console errors: zero.
- Browser favicon request: PASS using the bundled Movistar mark.
- Router, UART and flash actions: none.

Evidence:

- `outputs/frontend/f294-hw-rx-ui-browser-20260904/result.json`
- `versions/lyoko-foundation-6.5.2-f294-emac-hw-rx-ui/`
- `tools/test_f294_emac_hw_rx_ui.py`

## Promotion boundary

F294 must remain an offline hold until F293 boots and its new counters prove
valid under three physical 2.4 GHz runs. If F293 is accepted, F294 can be
promoted as a rootfs-only successor over those exact kernel bytes.
