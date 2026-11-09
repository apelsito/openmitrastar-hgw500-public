# Pending R9 recovery: exact F365 return

Prepared offline on 2026-09-23. No device, SSH, ping, UART, TFTP, flash,
radio or watchdog operation was performed by this preparation. The live R9
recovery remains unproven; the owner power-cycle request was already sent once.
This document does not repeat that request or assert its completion.

The original R9 result remains immutable:
`/workspace/OpenMitraStar/f367-campaign/f367r9-campaign-20260922T224919Z-91a7595c/result.json`,
SHA256 `2ed7d2c75142a9ca3176302d4cb14c11d52d76dec056d6295a8ce7fd131b38d3`.
Its writer installed R9, but recovery failed before a serial reset/write. The
last observed R9 boot ID was `cf18e917-7a46-4a60-a352-eef2572adff7`.

## Concrete artifact

Plan: [plan.json](../outputs/preflight/r9-return-f365-20260923T081235Z/plan.json).
SHA256: `6cbc06e281b36dcdbe282c96a063b67424816d74b7ed10bb9c25929792594f5e`.
The plan binds 85 files, including the unchanged F365 writer, UART2 capture,
protected backups, images, manifests, SSH pin and focused test evidence.

Runner: [run_f367r9_return_f365.ps1](../tools/run_f367r9_return_f365.ps1).
Worker: [f367r9_return_f365.py](../tools/f367r9_return_f365.py).
Context/retirement contract:
[f367r9_return_context.ps1](../tools/f367r9_return_context.ps1).

The only writable image is the existing private F365 reference:

```text
/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f365-f364r3-temperature-data-device-bound\openmitrastar-linux510-f365-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin
bytes: 5382144
SHA256: 43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355
full-slot CRC32 with preserved store: 118901d4
physical mtd4 start: 0x007e0000
maximum erased prefix: 0x005e0000
store start, never erased: 0x00dc0000
store CRC32: 5d2ee646
```

This is an immutable local fallback reference, not a freshly obtained physical
dump. Before any erase the reused writer requires current Bootbase readbacks
of all protected regions, the exact store and the complete installed R9 slot
(`4fa4640f`). It then verifies RAM contents, Bootbase image acceptance, prefix
erase, preserved store, F365 full-slot CRC and byte-for-byte comparison, followed
by another protected/store readback. OEM and physical mtd0/1/2/3/5 stay protected;
logical mtd6 is never used as a physical partition. Persistent boot environment
writes are unavailable.

## Admission and retained ownership

Root remains the only physical operator. Execution requires root to supply a
freshly observed R9 boot ID, strictly different from the failed epoch. The
runner independently proves all admission conditions over pinned SSH while
holding a child lease under both original device mutexes. The retained parent
`outputs/locks/f301-physical-radio.lock` remains intact and open against writes.
Its owner PID/start identity and metadata hash must match the failed operation;
a dead PID alone never releases it.

Admission requires exact R9 version
`lyoko-foundation-6.11.8-f367r9-transition-observation-device`, kernel `#358`,
the F340 marker, no F336 RAM marker, boot state `ready`, inactive watchdog,
absence of qdrv/provider/wifi0/owner/socket/owner processes, unchanged journal
and active configuration, read-only storage views, healthy Ethernet and no fatal
markers. A disabled qualified SSH SysRq reboot path rejects admission.

Only after these checks may the existing UART nonce routine bind COM3 to the
authenticated device and exact R9 version. The worker repeats identity and
quiescence checks before its single qualified SSH reboot. Any image or epoch
difference aborts; it does not select a different recovery path automatically.

No AELITA access, radio trial, native acquisition, watchdog arm, serial BREAK,
serial SysRq fallback, blind reboot retry or second firmware write is exposed.
UART2's existing strict response cursors remain unchanged. The unrelated
continuous-epoch correction is not a dependency for this short recovery.

After complete F365 readback, new boot, platform27, watchdog, store,
configuration, Ethernet and containment PASS, the runner closes/removes only
its own child lease, keeps both mutexes, closes the parent's handle and moves
the complete parent directory to a verified sibling archive. Parent metadata
and the single-attempt claim remain byte-preserved. Mutexes are released only
after that move. Failure retains the quarantine and attempt claim; no retry is
started. An ambiguous write also prevents any automatic recovery write.

The protected mtd3 image is preserved, but this work does not claim a tested
mtd3 boot. Any later manual UART recovery remains a separate qualified root
operation; this runner does not attempt it.

## Offline verification and root entry point

- [Fault tests](../outputs/preflight/r9-return-tests-final-20260923T081222Z/result.json):
  16 tests PASS, covering wrong/old epochs, kernel identity, busy owners,
  unready boot, watchdog/store/configuration failures, physical CRC mismatch,
  no second write, ambiguous flash and containment/lease loss.
- [Synthetic Windows quarantine test](../outputs/preflight/r9-quarantine-test-final-20260923T081222Z/result.json):
  6 checks PASS. Separate child processes could not acquire either unique test
  mutex after retirement; parent/attempt bytes were preserved. No real device
  mutex or UART was used.
- [Offline wrapper result](../outputs/preflight/r9-return-f365-20260923T081235Z/wrapper-offline.json):
  Windows PowerShell 5.1 exit0, PowerShell parse PASS, no `-Execute`, parent
  still contains only its original `owner.json`, SHA256
  `37c47a29576b1da2743057d974e1ec3850965c98eef956ba04ff2973e21b1b48`.

The usable file-only command is:

```powershell
& "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -NoProfile -NonInteractive -ExecutionPolicy Bypass `
  -File '/workspace/user-home\Desktop\MitraStar\tools\run_f367r9_return_f365.ps1' `
  -PlanPath '/workspace/user-home\Desktop\MitraStar\outputs\preflight\r9-return-f365-20260923T081235Z\plan.json' `
  -PlanSha256 '6cbc06e281b36dcdbe282c96a063b67424816d74b7ed10bb9c25929792594f5e'
```

Root alone may append `-FreshBootId <the-real-fresh-R9-boot-id> -Execute` after
the required fresh observation. No example boot ID is a substitute for that
evidence. The runner rechecks every condition and freezes the plan/sources.
Actual boot, control-plane, physical return and final port acceptance are
**NOT RUN** by this offline preparation.
