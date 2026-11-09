# F301 store-protection observer probe

Date: 2026-09-04

## Scope

`tools/f301_store_protection_probe.ps1` retargets the F296 physical observer
gate to the exact F301 image installed in `mtd4/linux_live`.

The gate does not flash firmware and contains no persistent write operation.
The module is loaded from the read-only SquashFS into kernel RAM, reads the
JEDEC ID, status register, SCUR and the 28 DPB values covering `lyoko_store`,
and is then removed.

## Fixed identity

- Runtime: `lyoko-foundation-6.6.1-f301-f300-capability-truth-device`
- Firmware SHA-256:
  `4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262`
- Observer SHA-256:
  `2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8`
- Vermagic: `5.10.260-openmitrastar-radiohw mod_unload ARC700`

The local gate verifies the exact binary, its six-symbol import allowlist, the
F295 build manifest, the F301 packaged hash and the original C source. The
runtime gate verifies the same module hash and exact kernel release before
`insmod`.

## Fail-closed exclusion

Execution is refused when any of these is present:

- the shared `outputs/locks/f301-physical-radio.lock`;
- a running F301 sequential soak process;
- a running F301 multicast/IGMP process;
- an F301 soak checkpoint with `status=IN_PROGRESS`;
- an error while inventorying those conditions.

The execute path acquires the same shared lock atomically and repeats campaign
detection before opening SSH or UART. Test-only state-path overrides and process
inventory suppression are rejected in execute mode.

## Read-only proof

The pinned source and module contract demonstrate:

- only JEDEC, status, SCUR and DPB read commands;
- no write-enable or write-disable command;
- no page-program or erase command;
- no DPB/protection mutation command;
- no MTD registration or unregistration;
- all module parameters are read-only;
- no autoload and feature state disabled.

During a future authorized run, the gate additionally compares the exact
`/proc/mtd` contents and SHA-256 of every registered MTD block before and after,
checks the fatal count, removes the module and verifies that the observer
feature remains disabled.

## Validation

- Focused and inherited tests: 50/50 PASS.
- PowerShell parser: PASS.
- Hardware actions during implementation: zero.
- Dry-run evidence:
  `outputs/preflight/f301-store-protection-probe-20260904T130201Z/plan.json`
- Dry-run local contract: PASS.
- Current execute decision: BLOCKED because the F301 six-hour soak is active.

Future execution, only after all campaign locks are clear:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File tools\f301_store_protection_probe.ps1 `
  -Execute `
  -Ack OPENMITRASTAR_F301_STORE_PROTECTION_READONLY_2F00A2DB
```
