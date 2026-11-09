# OpenMitraStar F277 Full candidate

Date: 2026-09-03

## Offline image

- Runtime: `lyoko-foundation-6.3.2-f277-qtn-mode-plan-fix-device`
- Candidate bytes: `5259264`
- Candidate SHA-256: `da49978c362df08dda35f7c666f250cc182114c01504845240237e3570a2b2c5`
- Rootfs SHA-256: `7592c46cf9ed39a3cb6b966d31df8d93bf361257723cd0b8aed059adb28afcb8`
- Full-slot CRC32: `b1fa61ae`
- Full-slot SHA-256: `825cdc0aceabda3fb86b3c12aa31fd835fe6a291bd04f82ef97135971fab8915`
- Bootbase contract and slot fit: PASS
- Kernel, DTB and kernel config: byte-identical to installed F276
- Hardware boot: NOT RUN

## Single change

F277 changes only `/usr/sbin/om-qtnctl` plus the release identity. It reads the
actual Quantenna WEXT mode and compares that exact value with the mode required
by the requested channel and bandwidth.

The planner takes one WEXT mode snapshot and derives the current bandwidth
from it. It therefore cannot compare a bandwidth from one read with a mode
from a later read, and it removes one unnecessary driver query per plan.

This corrects the planning distinction between:

- a channel change that also requires a PHY mode/extension-position write;
- a channel change that can preserve the current mode;
- an exact no-op that must not stop hostapd-qtn or issue WEXT/MuC commands.

The authenticated plan API inherited from F276 remains present. Dynamic
Quantenna mutation remains disabled by default and F277 executes no new radio
operation during boot.

## Validation

- `om-qtnctl` POSIX shell syntax: PASS.
- Native Quantenna plan/rollback tests: 5 PASS.
- F277 builder, artifact and promoter contract tests: 3 PASS.
- Combined test gate: 8 PASS.
- F277 UART/SSH step-gate tests: 3 PASS.
- `SHA256SUMS`: PASS for every packaged artifact.
- Guarded promotion dry-run: PASS; router SSH, local TFTP address and COM3 are
  currently visible.
- `lyoko_store` range remains erased and outside the candidate.
- Physical flash and radio mutation: NOT RUN.

The first generated image was rejected before use because its copied builder
still selected F275 as the binary base. The final hash above was rebuilt from
the exact F276 device-bound artifacts and supersedes that discarded output.

## Next physical boundary

F276 remains installed and stable. F277 may be promoted to physical
`mtd4/linux_live` through the normal guarded TFTP pipeline, but the next
Quantenna operation, `mode-write-same`, must only run with UART capture and
physical power-cycle recovery available.

Prepared command:

```powershell
.\tools\promote_f277_mtd4_direct.ps1
```

The dry-run is the default. Execution requires the exact acknowledgement
embedded in the script and must not be started unattended while physical
recovery is unavailable.

After F277 is installed, the isolated mode probe is:

```powershell
python .\tools\run_f277_qtn_step_gate.py --step mode-write-same
```

Its default invocation is also a dry-run. Execution additionally requires
`--execute`, the exact ACK, `--allow-management-loss` and
`--physical-recovery-ready`. The gate captures UART, verifies both AP states,
compares the live Quantenna mode before and after, requires an unchanged fatal
count, and never retries or attempts automatic recovery.
