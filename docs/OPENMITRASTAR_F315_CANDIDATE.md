# OpenMitraStar F315 radar shadow candidate

Date: 2026-09-05

F315 is the first versioned `mtd4` successor to installed F314 that packages
the reconstructed QT4 acquisition and classification path in shadow mode.
It is built and flash-capable, but it has not been installed or exercised on
hardware.

## Artifact

- Candidate bytes: `5,275,648`
- Candidate SHA-256:
  `735e19dd12c91392096afa741cf77f55593f79b1bccff995394da9ef3b43d377`
- Full-slot CRC32: `b719af06`
- Full-slot SHA-256:
  `5950f378e604ac46ee30cda2e445aa88eb9b6ebeeeec23362f9b67b74d20582c`
- Kernel SHA-256:
  `fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649`
- Shadow provider: `qtn_radar_shadow_f315.ko`, 39,548 bytes, SHA-256
  `a4781e911aabca66ed5e640ae03a5b6772be0af6553cd64e035ec0b26f29d3c7`.

## Authority boundary

F315 configures and reads the bounded QT4 acquisition path only when explicitly
enabled. It exports the complete 18-symbol qdrv radar ABI, but
`radar_start=false`, `radar_get_status=false`, callback invocation is
structurally fixed at zero and DFS transmission is never authorized.

The physical gate requires an exact `mtd4` installation, a non-DFS boot,
dual-radio regression and bounded shadow observation. Ad-hoc module loading is
not allowed because the acquisition path must be tested as one versioned image.

