# OpenMitraStar F292 package runtime verification

Date: 2026-09-04

The signed Lyoko package lifecycle was repeated on the currently installed
F292 firmware without rebooting or writing persistent storage.

## Result

- Signed catalog update: PASS.
- Search, package information, dependencies and install plan: PASS.
- Volatile install of `lyoko-netdiag`: PASS.
- Execution from `/run/lyoko-packages`: PASS.
- Removal and runtime cleanup: PASS.
- Package API returned to disabled state: PASS.
- Persistent data partition hash before/after: identical.
- Fatal kernel/firmware markers: zero.
- SSH remained available after cleanup.

Evidence:

- `outputs/postflash/f292-package-lifecycle-20260904T022342Z/status.json`
- `outputs/postflash/f292-packages-current-20260904T020411Z/status.json`

This proves that the package subsystem is not merely inherited historical
functionality: its complete signed lifecycle works on the current physical
F292 image. Persistent package installation remains intentionally disabled.
