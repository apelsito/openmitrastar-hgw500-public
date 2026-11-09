# OpenMitraStar F245 package catalog candidate

F245 advances the package surface without changing the kernel, radio drivers,
DMA, bridge topology, MTD layout or storage policy.

## What changed

- Foundation 4.9 package catalog with local search and a metadata inspector.
- Signed catalog entries expose version, ARC700/uClibc ABI, installed size and
  direct dependencies.
- The UI requests the exact dependency plan from `lyoko-pkg` before install.
- Authenticated read-only package queries:
  `search`, `info`, `depends`, `plan` and `update`.
- `update` verifies the immutable in-firmware feed. It does not access a
  network repository.

## Security contract

- Ed25519 feed verification and package SHA-256 verification remain mandatory.
- Package arguments use the existing strict package-name grammar.
- Query output is bounded and validated before JSON serialization.
- Install/remove remain CSRF-protected, confirmation-gated and disabled unless
  the volatile runtime feature gate is active.
- No maintainer scripts, HTTP exec, uploads, alternate install roots, network
  fetches or persistent package writes are introduced.

## Artifact

- Bytes: `5238784`
- SHA-256: `64ca0dae2f5dc49896bc228aa4d901a79a00a52d5d5fb5d6ef03569abfb4052b`
- Rootfs SHA-256: `653769991d82a8250cc9ac2f4ae3aac4a872b932c90ffbed0e28668929a20e24`
- Full-slot SHA-256: `ef6338d6f1d0d1f9812b66cd0daff876955581740bacea203701ac5be357267d`
- Hardware state: `NOT_RUN`
- Classification: offline hold, not authorized for flash.

Only these rootfs paths differ from F243:

```text
etc/lyoko/frontend.env
etc/openmitrastar/release
usr/libexec/openmitrastar/om-api-v1
usr/share/openmitrastar/web/dashboard.html
www/app.css
www/app.js
```

Offline evidence: 29 Foundation tests PASS, 35 combined F243-F246 regression
tests PASS, SHA256SUMS PASS, SquashFS package assets PASS and browser search,
selection, plan and catalog verification PASS with no console errors.
