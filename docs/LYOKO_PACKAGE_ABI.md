# Lyoko package ABI v1

Lyoko adopts the standard OpenWrt `.ipk` container without claiming binary
compatibility with arbitrary OpenWrt feeds.

Required package identity:

```text
Architecture: arc700_uclibc_lyoko_v1
X-Lyoko-Kernel-ABI: 5.10.260-openmitrastar-radiohw
X-Lyoko-Libc-ABI: uclibc
X-Lyoko-Platform: hgw-500bna-qcv2
```

The current implementation provides:

- deterministic standard `ar` IPK generation;
- deterministic `control.tar.gz` and `data.tar.gz` payloads;
- strict architecture, kernel, libc and platform validation;
- bounded decompression and member-count limits;
- path traversal, duplicate path, symlink, hardlink and device rejection;
- rejection of setuid, setgid and sticky package entries;
- deterministic `Packages` and `Packages.gz` indexes;
- Ed25519 repository signatures and package hash verification;
- atomic host-side extraction into a staging tree for future SquashFS builds.

F195 adds experimental dynamic installation into `/run/lyoko-packages` only.
It uses the embedded immutable feed, validates the package SHA-256, inspects the
archive before extraction and activates the package through a same-filesystem
rename. Network download and persistent installation remain disabled.

F203 adds bounded package-manager semantics without adding network or flash
authority:

- immutable catalog `update` verifies every package hash and the index SHA
  declared by the build-signed signature metadata;
- `search`, `info`, `depends` and `plan` provide read-only discovery;
- dependencies are exact package names only, with a maximum depth of 16;
- missing dependencies and dependency cycles fail closed;
- installing a package installs its dependencies first;
- removing a package required by another installed package is rejected.

Repository signatures are verified during the reproducible firmware build.
Starting with F205, the target also verifies the Ed25519 signature over the
immutable `Packages` index before every catalog-dependent command, then checks
the selected package SHA-256. The verifier is a static ARC700 binary derived
from Dropbear 2026.94. Only the raw public key and signature are bundled.

An ARC700 `pkgbox` is provided as the runtime container toolbox. It
contains `ar`, `tar`, `gzip`, `gunzip` and `sha256sum`, but deliberately omits
network downloaders, mount commands, reboot commands and flash utilities. It is
present in F195 but package execution remains volatile and experimental until
the physical gate passes.

Current verified toolbox:

- Path: `outputs/packages/lyoko-pkgbox/lyoko-pkgbox`
- Size: `238,624` bytes
- SHA-256: `8d89cb0f592157045e3b2fa6296fea849b676bc5c90b8e008f9b8cd34896f607`
- Feed public key ID: `01ed300cc2b2a01d`
- Private key location: intentionally outside the workspace and never bundled
  into firmware.

Example package:

```powershell
python tools\lyoko_ipk.py build packages\lyoko\lyoko-sysinfo outputs\packages
```

Build the target-side toolbox without touching hardware:

```powershell
.\tools\build_lyoko_pkgbox.ps1
```

Production feed private keys must never be stored in firmware, source control
or handoff bundles. Tests generate ephemeral keys and retain no private key.

The local production key is initialized outside the workspace with:

```powershell
python tools\init_lyoko_feed_key.py
python tools\build_lyoko_package_feed.py `
  --private-key "$HOME\.openmitrastar\keys\lyoko-feed-ed25519.pem" `
  --output-dir outputs\packages\lyoko-v1
```

Only `lyoko-feed-ed25519.pub` is suitable for inclusion in firmware.
