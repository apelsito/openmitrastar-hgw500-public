# OpenMitraStar F264 Full candidate

## Purpose

F264 is the direct Full Lyoko successor to the physically installed F263.
It changes only background-process standard input handling:

- Realtek hostapd starts with stdin connected to `/dev/null`;
- Quantenna hostapd starts with stdin connected to `/dev/null`;
- the automatic transaction rollback watchdog starts with stdin connected to
  `/dev/null`.

This prevents long-lived child processes from retaining an SSH channel after
`apply_config` has returned.

## Artifact

- Runtime identity: `lyoko-foundation-6.0.1-f264-full-device`
- Bytes: `5246976`
- SHA-256: `8b53dd2bf6a73f84e2b320a8b067f536bdd74c95da22e598a66ccc60954a84f3`
- Full-slot CRC32: `06ad1b30`
- Full-slot SHA-256: `237fce09b47bc19f719f668af3f0188bb621e33f60bc1b675d00cd83207b67f4`
- Candidate eligible: `true`
- Flash supported: `true`
- Normal write target: physical `mtd4/linux_live` only

Private artifact:

`%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f264-device-bound`

## Delta

Only these rootfs paths differ from F263:

- `etc/lyoko/frontend.env`
- `etc/openmitrastar/release`
- `usr/sbin/om-config-transaction`
- `usr/sbin/om-qtnctl`
- `usr/sbin/om-rtlctl`

Kernel, Kconfig, DTB, qdrv, wlan, firmware blobs, web assets, package manager,
API, bridge topology and partition layout are byte-identical to F263.

## Validation

- Bootbase contract: PASS
- Slot fit: PASS
- Store tail remains erased: PASS
- Full Foundation plus F264 tests: 40/40 PASS
- Hardware boot: NOT RUN

## Promotion

The currently installed F263 full-slot identity is pinned as:

- CRC32: `34b37586`
- SHA-256: `541d740e411bdf471948a034c977b08267a39df075d2ab27c36ef555045bea6c`

Dry-run:

```powershell
.\tools\promote_f264_mtd4_direct.ps1
```

The router is currently unreachable after the F263 radio transaction test.
A physical power cycle is required before promotion. After recovery, run the
dry-run and require router SSH, COM3 and wired TFTP to pass before execution.
