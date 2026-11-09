# OpenMitraStar F305 Offline Candidate

Date: 2026-09-04

## Classification

- Version: `6.7.2-f305-unified-console-api`
- Status: offline build PASS
- Candidate eligible: no
- Flash supported: no
- Hardware validation: NOT RUN

F305 is the real integration of the F304 three-mode console and the F304 API
contract over the exact installed F301 runtime. It deliberately remains an
offline candidate because this task did not authorize hardware access or flash.

## Composition

- Runtime base: exact F301 SquashFS.
- UI source: `versions/lyoko-foundation-6.7.0-f304-three-mode-console`.
- API source: `versions/lyoko-foundation-6.7.1-f304-api-contract`.
- Unified source: `versions/lyoko-foundation-6.7.2-f305-unified-console-api`.
- Builder: `tools/build_f305_unified_console_api_from_f301.py`.
- Tests: `tools/test_f305_unified_console_api_builder.py` plus the F301/F304/F305 regressions.

The rootfs delta from F301 is limited to:

```text
etc/lyoko/capabilities.json
etc/lyoko/frontend.env
etc/openmitrastar/release
usr/libexec/openmitrastar/om-api-v1
usr/share/openmitrastar/web/dashboard.html
www/app.css
www/app.js
www/dashboard.html
```

## Preserved Contracts

- Kernel, config, DTB, vmlinux and compressed kernel: byte-identical to F301.
- Radio modules, firmware, power tables and startup/control files: 86/86 byte-identical to F301.
- Corrected login and `/dashboard.cgi` path retained.
- Store-protection observer remains disabled and without autoload.
- Multicast certification harness remains packaged but inactive.
- `lyoko_store` remains erased in the candidate and outside the image payload.
- No persistent configuration, package or firmware write API is enabled.

## Unified Product Surface

- One SPA with Normal, Advanced and Developer modes.
- Canonical `PATCH /api/v1/radios/{2g|5g}`.
- Compatibility alias `/api/v1/radios/{2g|5g}/stage`.
- Dynamic MTD sizes read from `/proc/mtd`.
- Complete frontend hashes for dashboard, JavaScript, CSS and login assets.
- 23 capabilities with F300 physical datapath evidence and coherent F305 identity.
- DFS remains fail-closed while the native radar detector is unavailable.

## Artifact

- File: `openmitrastar-linux510-f305-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`
- Bytes: `5,267,456`
- Candidate CRC32: `d5560cc6`
- Candidate SHA-256: `6a760cb6594dce1bd927f776afdfead2bc488ca910669dcdc8a31eeb20c068c3`
- Rootfs SHA-256: `4c02e21889bd9fee694eb4df1eb750ea54526f4efca1dfc1c24f0c1de6bdaadb`
- Full-slot CRC32: `f542b95e`
- Full-slot SHA-256: `115e36f6489c9d33f2bad446b2586f2243b670fbd31340cc73373bccd6359f96`

Private output:

```text
/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f305-device-bound
```

## Verification

- Two clean builds: 13/13 output files byte-identical.
- Combined F301, both F304 branches and F305 suites: 65/65 PASS.
- Bootbase contract and slot fit: PASS.
- `SHA256SUMS`: PASS.
- Runtime search for stale F301/F304/6.7.0/6.7.1 identities: PASS, no matches.
- Hardware, SSH, UART, TFTP, radio mutation, flash and MTD actions: zero.
