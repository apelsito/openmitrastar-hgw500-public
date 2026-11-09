# OpenMitraStar Lyoko Next software platform

Date: 2026-09-05

## Result available now

`work/lyoko-web-next` is a host-built, router-served control UI. Node.js,
TypeScript and Vite are build dependencies only; the router receives static
HTML, CSS and JavaScript.

- Preact `10.29.8` and Signals `2.11.2`.
- TypeScript `7.0.2` and Vite `8.2.2`.
- Production JavaScript: `32,751` bytes raw, `11,235` bytes Brotli.
- Production CSS: `8,382` bytes raw, `2,407` bytes Brotli.
- White CGI-inspired default theme, optional dark Lyoko mode, and six functional
  views with desktop and 390-pixel mobile navigation.
- Same-origin `/api/v1`, no CDN, remote fonts, analytics, service worker,
  `eval`, HTML injection or Node runtime on the device.
- Build, strict type check, bundle budgets and both npm vulnerability audits:
  PASS with zero reported vulnerabilities.

The UI remains a standalone portable artifact. It is not yet included in an
`mtd4` candidate and does not change the installed F314 rootfs.

The packaged F314 compatibility run uses live emulator data from the current
status, firmware, hardware, capability and dual-radio endpoints while treating
the absent future F317 optimization endpoint as an isolated optional feature.
The same adapter also accepts the exact F317 `lyoko.api.optimization/v1` fields
without enabling automatic application.

The current integration check inventories the original and rebuilt SquashFS
entirely on native Linux storage, including directories, uid/gid, permissions,
symlink targets, hardlinks and file hashes. It verifies the overlay's actual
bytes against its manifest and changes metadata only on added files/directories.
Two independent rebuilds pass for each pinned base:

| Base | Rebuilt bytes | Rootfs headroom | Rebuilt SHA-256 |
| --- | ---: | ---: | --- |
| F314 | 3,727,360 | 860,160 | `8f6f88186b408192d029fccff3300ec8527df2373f289e2771244cd00898f60f` |
| F317 | 3,792,896 | 794,624 | `5af267627b225401f55901dee94108bc9e9b8c8c5c95ce59825eaa4649116751` |

Only the internal dashboard, `web-next.env` and the two hashed assets change;
one asset directory is added. All 68 existing directories on F314 and 70 on
F317 retain their metadata. Authentication/API, radio-control files and F317
radiod components retain their native metadata and hashes. Evidence lives in
`outputs/frontend/lyoko-web-next-f314-f317-contract-20260905/`:
`rootfs-integration-native-f314.json` and `rootfs-integration-native-f317.json`.

These v2 native reports supersede the earlier v1 reports for metadata claims.
The v1 comparison of protected-file modes after extraction to NTFS reported
host-visible `0777`, not the actual SquashFS modes. The previous blanket
directory chmod has been removed. Sixteen behavioral tests cover valid deltas,
private/sticky directories, owner/mode drift, links, tampering and extra paths.

This proves packaging and preservation, not complete product equivalence.
The prototype still lacks the classic console's transaction/control parity,
and the existing CGI session code has not yet been executed with this UI in an
authenticated runtime test. Keep the classic CGI as the product until those
gates pass; do not deploy this prototype as a replacement merely because it fits.

## Recommended target architecture

### Web and control plane

Keep the static Preact application. On HGW, first integrate it with the existing
authenticated `/api/v1` implementation so the UI change can be measured without
replacing the service manager or radio stack. The next service-plane target is
the small OpenWrt family `uhttpd + ubus + rpcd + ucode + UCI`, cross-compiled for
the exact ARC700 ABI and introduced one component at a time. The Askey OpenWrt
port can use that family natively through its own MIPS adapters.

Use Server-Sent Events or bounded NDJSON for live telemetry. They are easier to
bound and recover than a permanent WebSocket session on this memory budget.

### Packages and updates

OpenWrt 25.12 uses `apk`. The Askey target should follow it natively. HGW should
keep the already proven signed `lyoko-pkg` format until an ARC700 `apk-tools`
build has measured binary size, peak RAM, signature verification and power-loss
behavior. Package semantics may be shared; package binaries and ABI metadata may
not be copied between MIPS and ARC700.

### TLS and sessions

Benchmark minimal TLS 1.3 builds of wolfSSL and Mbed TLS against the exact ARC700
toolchain. Select only after measuring text size, handshake peak RAM, steady RAM
and handshake time. Keep same-origin secure cookies, strict CSP, CSRF tokens,
session rotation, bounded login attempts and no remote assets.

### Password storage and SSH

Argon2id is the target password KDF, but its memory cost must be calibrated on
the physical router. Do not copy a desktop memory profile onto a system with
roughly 32 MiB free. Until a profile passes concurrent radio and management
load, preserve the proven authentication path, rate limiting and Ed25519-only
SSH rather than weakening the KDF silently.

### Boot and filesystem

Bootbase and its environment remain unchanged. Normal writes remain exclusive
to `mtd4/linux_live`; `mtd3/linux_safety` stays the recovery branch. Compare
SquashFS XZ and Zstandard only with exact image size, cold-boot time and peak-RAM
measurements. Current XZ remains authoritative until another compressor wins all
required gates and still fits the slot.

### Radio portability

Portable code consists of the `lyoko-radiod` decision engine, board-profile
schema, plan/apply/readback/rollback state machine, DFS event schema and replay
tests. Each board supplies its own adapter, proprietary-radio API, firmware,
calibration and addresses. ARC700 modules, MIPS modules, MMIO values and
calibration are never transferable artifacts.

## Integration gates

1. Package the exact `dist/` assets beside the current authenticated F314 UI.
2. Verify file hashes and native metadata against F314 and F317: **offline PASS**.
3. Port classic CGI controls and transactions, verify authentication/session
   expiry behavior, and test API error states before accepting UI replacement.
4. Measure cold load, warm load, router RSS and API latency on physical F314.
5. Build a versioned `mtd4` successor after parity and reproducibility pass.
6. Preserve exact F314 rollback and run dual-radio traffic plus management soak.

The software stack does not bypass the current physical dependency: F319 still
requires the FTDI cable physically bound to the HGW before claim/map/unload.
