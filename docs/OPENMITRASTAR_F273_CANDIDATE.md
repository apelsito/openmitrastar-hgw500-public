# OpenMitraStar F273 Full candidate

Date: 2026-09-03

- Runtime: `lyoko-foundation-6.2.2-f273-qtn-delta-plan-device`
- Candidate bytes: `5259264`
- Candidate SHA-256: `4c3265c0f2e3be8ee4aeb1c4a6ea82fb91ed3f75166a9c6b1db3f561d4bd391e`
- Full-slot CRC32: `b0e9e701`
- Full-slot SHA-256: `5b0a4456880366b98e45d1396aaa343e6aae857cb66a86610b18cc394ff6fed9`
- Bootbase contract and slot fit: PASS
- Kernel and radio modules: byte-identical to installed F272
- Hardware boot: NOT RUN

## Change

F273 changes only `/usr/sbin/om-qtnctl` plus release identity.

It adds a read-only `plan <config-file>` operation that reports whether SSID,
channel or bandwidth actually differ and which classes of operation would be
required. It also adds an exact no-op fast path: an unchanged configuration
returns verified success without stopping hostapd-qtn or issuing WEXT/MuC
commands.

Dynamic Quantenna mutation remains disabled by default. F273 does not run any
new operation at boot and does not expose the unsafe path through the web.

## Validation

- Quantenna backend tests, including plan and no-op apply: 5 PASS.
- Builder tests: 2 PASS.
- Bootbase contract and slot fit: PASS.
- Physical flash: NOT RUN.

Design analysis and the next hardware boundary are documented in
`docs/QTN_DYNAMIC_CONTROL_ISOLATION_F273.md`.
