# OpenMitraStar F248 opkg compatibility candidate

F248 adds a strict OpenWrt-style `opkg` command subset over the signed Lyoko
package engine. It does not change the kernel, radio drivers, DMA, MTD layout or
storage policy.

Supported commands: `update`, `list`, `list-installed`, `print-architecture`,
`find`, `info`, `depends`, `status`, `install` and `remove`.

URLs, local archives, arbitrary options, downloads, upgrades, maintainer
scripts, network access and persistent installation are rejected. Production
paths are fixed; environment overrides are accepted by `lyoko-pkg` only when
the explicit test-mode flag is active.

## Artifact

- Bytes: `5242880`
- SHA-256: `cffb237439c9240aef3e800d0a6308d79658e8becfa1e513c2341ec91170b273`
- Rootfs SHA-256: `28ec3c6c78df99c2bd8e0c3bd80337b11731d23f77159ca3ffd2271728f46588`
- Full-slot SHA-256: `648e679ff41817dc686bbc533fa66c45c545decf349611b1406737d1f003c9ae`
- Hardware state: `NOT_RUN`
- Classification: offline hold, not authorized for flash.

Verification: 45 tests PASS, Bootbase/slot contract PASS and browser rendering
PASS with no console errors or horizontal overflow.
