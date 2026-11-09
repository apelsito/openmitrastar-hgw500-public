# OpenMitraStar F286 Full candidate

Date: 2026-09-03

## Purpose

F286 fixes the last false-negative observed in the F285 bounded Quantenna SSID
trial. The restore apply had already succeeded and verified, but the trial read
SSID/channel/bandwidth again during a transient convergence window and left the
watchdog armed. The watchdog later found the restored state as an exact no-op.

F286 polls the restored SSID, channel and bandwidth for up to 20 seconds before
accepting the restore or leaving the watchdog armed.

## Candidate

- Runtime: `lyoko-foundation-6.3.10-f286-qtn-restore-convergence-device`
- Candidate bytes: `5259264`
- Candidate SHA-256: `7f59bc0f05a9bc85bd8b6723d2198bd9c54b8e7c77e623cc929821036069430d`
- Full-slot CRC32: `c3f59e4d`
- Full-slot SHA-256: `dd9cc8fea9ff38300b4e30ddaa96ca94bc0737c5b073e1f28572455e6b08ddc3`
- Bootbase contract and slot fit: PASS
- Hardware boot: NOT RUN

## Scope

Only these SquashFS paths differ from F285:

- `/etc/openmitrastar/release`
- `/usr/sbin/om-qtn-material-trial`

Kernel, DTB, Realtek modules, Quantenna modules, firmware blobs, web/API,
network topology, radio defaults and the erased store tail are unchanged.

## Physical gate

F286 must not be described as installed or hardware-proven. After an explicitly
authorized mtd4 flash, run the material SSID transaction with AELITA association
and require:

1. target apply PASS;
2. AELITA 5 GHz WPA2/CCMP association plus DHCP and router ping PASS;
3. `restore-converged` and `restore-pass` markers;
4. exact final router and client restoration;
5. SSH alive and fatal count unchanged;
6. no writes outside physical `mtd4/linux_live`.
