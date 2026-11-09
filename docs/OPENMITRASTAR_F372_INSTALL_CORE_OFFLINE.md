# F372 install state-machine core — offline qualification, 2026-10-21

`tools/f372_install_executor.py` implements the bounded F372 candidate / exact
F365 return state machine. This document describes offline qualification only.
There is no reviewed physical launcher or production backend, and physical GO
is not admitted. No device access, UART opening, network change, TFTP exposure,
flash, reboot or radio mutation was performed for this work.

## Immutable scope and evidence

- Source SHA-256: `38d36343aca72aff0f58be0def83ae98d10bb53896764293659e418eeea3ecdf`.
- Tests: [final 23-test receipt](../outputs/preflight/f372-core-tests-20261021T214200Z-r7-cached/result.json),
  SHA-256 `57da84f69fccb53f02fe2c4844198a87f037a12f9a6782bfaeb13bbe5e98d8b9`.
- [Default CLI and invalid-command smoke](../outputs/preflight/f372-core-localchecks-20261021T215650643897Z/result.json):
  file-only contract validation; three forbidden commands rejected before
  forwarding any effect.
- The original [F372 preparation](../outputs/preflight/f372-install-20261021T195348642022Z/plan.json)
  remains unchanged, SHA-256
  `a502abe660e7da3e3d561d3f8995ac0d43701cb683e3b03d919d5234e97c25c1`,
  status `PASS_OFFLINE_CONTRACT_PHYSICAL_NO_GO`.

The 23 tests passed with synthetic host, UART and gate receipts. The original
F365 `write_image` and response parser were exercised with transfer/domain/
readback effects replaced. State-machine tests use synthetic writer operations
with the original mutation receipt parser. Original source hashes and image
contracts were validated from actual files before and after the campaign;
repeated old-source/plan checks inside fake cases used that validated snapshot.
This is not a physical writer or recovery qualification. Earlier failed and
deliberately stopped test results remain in their original output directories.

## Behavior and adapters

`run(plan, out, verified_admission, *, host_factory, uart_factory,
server_factory, writer=None, admission_verifier, postboot_gate=None, clock)`
returns a result dictionary in a new empty evidence directory. Defaults refuse
before constructing any effect. The CLI accepts only `--plan` and
`--plan-sha256`; there is no `--execute` option.

Admission requires separately supplied typed `VerifiedAdmission` and
`AdmissionDecision` identities, binding exact plan/scope, live boot, lease,
nonce digest, expiry, source pins and seven hashed evidence references:
authorization, recovery, executor review, host lease, UART nonce, transport
review and live boot. The independent verifier owns each receipt's semantics
and human provenance; structure alone never supplies authorization or GO.
The private effect plan extends the original frozen sources with new executor
and postboot pins. The exact old campaign supplies unchanged journal acceptance
for the F365 host adapter. Original plans and images are not rewritten.

Reusable `Host` and `Uart` adapters require explicit effect backends. The UART
adapter routes the old capture's COM3 assignment to reviewed COM4 using a
supplied serial object; it selects no native serial factory. The host references
the original F365 identity/configuration/read-only helpers, and uses a supplied
platform/transport backend. No firmware or configuration backup is created.

The original F365 domain/readback/flash/write/boot functions remain unchanged.
Only physical `mtd4/linux_live`, offset `0x7e0000`, prefix `0x5e0000`, may be
erased; only the exact 5,382,144-byte candidate or return image may be written.
Protected partitions and store are readback checks. Logical Linux MTD numbers
and full-slot checksum models never become write artifacts. Invalid geometry
is refused before calling the supplied UART effect.

Each run permits one controlled SSH reboot, one exact F372 install, and at most
one exact F365 return. Current F367r9 with active F365 radio modules in RAM is
accepted by identity binding; no `rmmod` or radio cessation is introduced.
Protected/store/full-current-R9 CRC readback precedes installation. A candidate
is kept only after its new boot and the source-bound F372 postboot control gate.
`PASS_F372_CONTROL_ONLY` never means client, traffic, cold-boot or release PASS.

Transfer failure before erase stops with baseline flash unchanged. Ambiguous
erase/write receipt or write in flight stops with quarantine retained. Candidate
failure can return to F365 only after the candidate writer was fully confirmed,
helpers are contained, admission still passes, and a fresh Bootbase prompt is
already present. Missing prompt stops; no implicit serial reset, power cycle,
second reboot or automatic retry is performed. No path releases the parent
quarantine or external lease. Counts distinguish attempts from actual mutation
commands, and arbitrary backend exception text is excluded from error fields.

## Physical gates still missing

Injected factories are not independently admitted production backends. A future
reviewed launcher must verify their code provenance and enforce one-shot nonce/
lease consumption across separate output directories. The core prevents reuse
of the same evidence directory and bounds each run, but does not create or
consume an external physical claim. No synthetic receipt may confer real GO.

Exact owner scope/provenance, fresh manual mtd3 recovery PASS, live COM4/PnP/
nonce/retained-parent binding, transport exposure/permission, executor review,
and fresh physical readback remain required. The preserved historical mtd3
record is still rootfs/management `NO_GO`; kernel Bootbase acceptance alone does
not establish recovery readiness. WPA2 client association, bidirectional
traffic, persistent repeated cold boot, soak and final release acceptance remain
unrun. F372 firmware itself remains uninstalled by this work.
