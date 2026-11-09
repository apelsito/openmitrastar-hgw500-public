# OpenMitraStar F233 Experimental Candidate

## Purpose

F233 replaces the unavailable OEM QCSAPI control path with a bounded Lyoko
backend built from the Quantenna tools already proven on Linux 5.10:

- `iwconfig-qtn`
- `iwpriv-qtn`
- `hostapd-qtn`
- `hostapd-cli-qtn`

The OEM `call_qcsapi` path is not used. Earlier F73 evidence showed that binary
and its original uClibc closure terminating with `SIGSEGV` on the Linux 5.10
runtime.

## Supported Surface

- SSID: validated ASCII subset, 1 to 32 characters.
- Channel: 36, 40, 44 or 48 only.
- Bandwidth: 20, 40 or 80 MHz.
- Region: fixed to ES.
- DFS: still blocked.
- Security: existing protected WPA2 secret is reused and never returned.

Application uses `validate -> stage -> apply -> verify`. The native backend
restarts only the Quantenna hostapd process, restores RF/interface state,
checks SSID/channel/bandwidth plus bridge membership, and allows the transaction
layer to reapply the captured snapshot on failure.

## Artifact

- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f233-device-bound`
- Bytes: `5214208`
- SHA-256: `16f90110a788b06b9f236afa2a419b8f5dd35d422668da273faaaac0d28dce04`
- Full-slot SHA-256: `e2ebaff8a5ab049d74dbffff13838856e1d3cc51c0dc7b49f510d73460cf0d17`
- Rootfs SHA-256: `e6628d5acde7507e534f7f98cddfa91777fbb41f7c77c60e639b4f54ab9f7831`

## Status

Offline API, transaction, backend and browser gates pass. F233 remains
`PRIVATE_DEVICE_BOUND_EXPERIMENTAL_DO_NOT_FLASH`, hardware `NOT_RUN`.
