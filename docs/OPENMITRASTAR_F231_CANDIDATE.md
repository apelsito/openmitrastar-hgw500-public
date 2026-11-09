# OpenMitraStar F231 Candidate

## Purpose

F231 extends F229 with a truthful 5 GHz control contract. The installed F222
runtime has the Quantenna status tools required for observation, but neither
`/usr/sbin/qcsapi` nor `/usr/sbin/call_qcsapi` is present. F231 therefore keeps
5 GHz status, clients and diagnostics readable while refusing configuration
changes until a compatible control backend exists.

## Artifact

- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f231-device-bound`
- Bytes: `5214208`
- SHA-256: `d305221d6b60aac224fda793debeaa1dbd2cfd6f6722e746aead3b87a13fe111`
- Full-slot SHA-256: `537df76d9ce0a829b6e0c19779b0c06ccbcdbfedf3367904ba7831be94c902f4`
- Rootfs SHA-256: `5bb679159b01143905918d68a2336e2e8e199a3195a2c963d5c07d2d2104565c`

## Contract

- The control backend is selected consistently by `om-radioctl` and
  `om-config-transaction`.
- Without the backend, SSID, channel and bandwidth report `writable=false`.
- Direct 5 GHz staging fails with `control-backend-unavailable`.
- Controls start disabled in HTML and are enabled only after a successful,
  writable contract response.
- 2.4 GHz, package management, hardware inventory, SSH identity, storage and
  both radio binaries are inherited unchanged from F229.

## Status

Offline source/API tests and browser validation pass. Hardware validation is
`NOT_RUN`; F222 remains installed.
