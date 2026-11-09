# OpenMitraStar F176 package UI candidate

Date: `2026-09-01`

F176 layers Foundation 1.2 over the signed package base F174.

It adds:

- authenticated `GET /api/v1/packages`;
- installed package name/version and Lyoko ABI;
- signed-feed key ID and verification state;
- explicit `runtime_install_enabled=false`;
- Developer package panel;
- responsive wrapping for long hashes and diagnostics.

No install, remove, fetch, mount, MTD or configuration mutation endpoint is
added. Kernel, DTB, radio modules and the packaged `lyoko-sysinfo` payload are
byte-identical to F174.

Build:

```powershell
.\tools\build_f176_lyoko_package_ui.ps1
```

Hardware validation remains `NOT_RUN`.

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f176-lyoko-package-ui-from-f174/build/openmitrastar-linux510-q3-persistent-f176-lyoko-package-ui-from-f174-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `4,968,448` bytes
- SHA-256: `5151ea00cc23d24cc11478779e1a1b155449e21ad83d3356e6c59052aaed5144`
- Candidate CRC32: `bde12dc6`
- Full-slot CRC32: `644c231d`
- Full-slot SHA-256:
  `0186ae62f7134affde01810166649d8d595458e82d2f39e557da24b34dc20ab1`
- Bootbase and slot fit: PASS
- Offline suite: `12 passed`
- Repeated build SHA-256: identical
- Extracted SquashFS package API: PASS
- Mobile viewport: `390 px`, document width `375 px`, no horizontal overflow

The exact frontend source is frozen under
`versions/lyoko-foundation-1.2-f176/`.
