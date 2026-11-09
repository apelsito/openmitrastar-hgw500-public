# OpenMitraStar F177 package manager candidate

Date: `2026-09-01`

F177 introduces `lyoko-pkg`, a small package manager designed for the actual
HGW-500BNA constraints rather than importing APT or full OpenWrt userspace.

Commands:

```text
lyoko-pkg list
lyoko-pkg status
lyoko-pkg verify NAME
lyoko-pkg install NAME
lyoko-pkg remove NAME
lyoko-pkg list-installed
lyoko-pkg exec NAME COMMAND [ARGS...]
```

Safety model:

- bundled standard `.ipk` files from the immutable SquashFS feed;
- architecture, kernel ABI, libc ABI, platform and SHA-256 validation;
- feed signature verified during image composition;
- volatile installs under `/run/lyoko-packages` by default;
- optional external-storage root only when explicitly selected later;
- no network fetch, mount, MTD, boot environment or `/persist` writes;
- package maintainer scripts are not executed;
- runtime install remains physically unvalidated.
- bundled archives live under `/usr/share/lyoko/feed/archives`; this avoids the
  case-insensitive `Packages`/`packages` collision on Windows build hosts.

Bundled packages:

- `lyoko-sysinfo 1.0.0-1`
- `lyoko-netdiag 1.0.0-1`

The manager completed list, verify, install, execution and remove in a WSL
sandbox. Physical ARC700 validation remains `NOT_RUN`.

The exact F177 Foundation source is frozen under
`versions/lyoko-foundation-1.3-f177/`; later UI work continues in
`versions/lyoko-foundation-1.4-dev/`.

The host-side updater verifies the pinned Ed25519 feed before uploading a
selected package over authenticated SSH to `/run`:

```powershell
python tools\lyoko_pkg_remote.py install lyoko-netdiag `
  --execute --ack OPENMITRASTAR_LYOKO_PKG_VOLATILE_INSTALL
```

This provides an apt-like update/install path without giving the router an
unverified downloader or permitting persistent flash writes.

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f177-lyoko-package-manager-from-f176/build/openmitrastar-linux510-q3-persistent-f177-lyoko-package-manager-from-f176-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `5,107,712` bytes
- SHA-256: `4d33edee7536268d6dfb230485239c9ddad2bca8dd3df17eb236e30653aabd86`
- Candidate CRC32: `8d599acb`
- Full-slot CRC32: `1256e21a`
- Full-slot SHA-256:
  `6a3a7e1de7c8eb4d71c8dd6d32d557007bbc9891334e83988e03c35245d14848`
- Bootbase and slot-fit: PASS
- Repeated build SHA-256: identical
- `lyoko-pkg`: mode `0755`
- `pkgbox`: `238,624` bytes, ARC700 static ELF, mode `0755`
