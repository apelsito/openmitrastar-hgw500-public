# OpenMitraStar F227 Candidate

Date: 2026-09-02

F227 converts the existing signed `lyoko-pkg` CLI into a bounded package
management surface for the Lyoko web console.

## Artifact

- Bytes: `5210112`
- SHA-256: `b0334ab00df708771d55a86d7e67e213d61a0765a81844350a2f11efe2d47734`
- Full-slot CRC32: `b52b86bc`
- Full-slot SHA-256: `d063eb7b3f087fcdbbff1ed0c7a10fc85a96f752e0d324cf474d37a4df822fc4`
- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f227-device-bound`

## Package Contract

- One authenticated endpoint: `GET/POST /api/v1/packages`.
- POST operations: `plan`, `install` and `remove` only.
- No package execution, uploads, arbitrary repositories, URLs or alternate
  installation roots are exposed over HTTP.
- Installation remains volatile under `/run/lyoko-packages`.
- Network fetching and persistent installation remain disabled.
- The runtime verifies the immutable feed with Ed25519 before advertising its
  package catalog.
- Package names reject `.`, `..`, leading punctuation, separators and names
  longer than 63 characters.
- Mutations use a global fail-fast lock.
- Plans are limited to eight packages and 4096 KiB installed size.
- Installation requires at least 8192 KiB free plus three times the planned
  installed size.
- Install and remove use different explicit confirmation values.

The web mutation feature gate is present but set to `0` by default. The UI can
inspect and plan packages, but hardware installation remains disabled until its
dedicated physical gate is executed. The gate uses the ephemeral
`/run/openmitrastar/features/package-api-v1` override and restores the disabled
state afterwards.

## Evidence

- Foundation, API and package-manager tests: 25 PASS.
- SHA256SUMS: PASS.
- Emulator catalog, plan, install, refresh and remove: PASS.
- Physical gate dry-run: `tools/run_f227_package_api_physical_gate.py` PASS.
- Kernel, config and DTB: byte-identical to F225/F222.
- No router, UART, radio or flash operation occurred.

F227 remains hardware `NOT_RUN`; its persistent web-mutation feature flag is
disabled.
