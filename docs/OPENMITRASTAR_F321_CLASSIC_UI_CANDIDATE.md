# F321 classic Lyoko UI over F314: candidate and installation

Candidate prepared on 2026-09-07 UTC and installed during the authorized
2026-09-07/08 UTC cycle. Independent pinned SSH and HTTP checks passed again on
2026-09-11. The original candidate manifest and execution result are preserved.

## Recorded installation and independent checks

Physical cycle: `outputs/flash-watch/f321-direct-20260907T235105Z-b42111c6`.
The exact candidate below was written to physical `mtd4/linux_live`.
`writer/backend.log` and `writer/bootbase-flash-uart.log` record:

- The prewrite F314 full-slot CRC32 `d6b13baa`, followed by erasure confined to
  the first `0x5e0000` bytes of mtd4 and erased-prefix CRC32 `aa86bf2e`.
- A `5,337,088`-byte write, full-slot CRC32 `6ed8e483` and
  `Total of 5337088 bytes were the same` from the RAM/flash comparison.
- Matching before/after CRCs for mtd0, mtd1, mtd2, mtd3 and mtd5; unchanged
  `bootcmd=bootselect` and `bootselect=0`; a boot read from physical mtd4 at
  `0x007e0000` followed by Linux startup.

The full-slot SHA-256 in the artifact table is computed from the local padded
image. No hardware SHA-256 was measured; the physical readback evidence is the
full-slot CRC32 and exact comparison of every candidate byte.

The original `result.json` remains `STOP_NO_AUTOMATIC_RETRY`. After the flash
and readback, the host parser treated the Linux warning
`pci 0000:00:00.0: BAR 0: failed to assign [io  size 0x0100]` as a Bootbase
failure. The same warning is present in the successful F314 recovery transcript
at `outputs/recovery/f321-prewrite-20260907T233941Z/uart.log`. No second flash
or automatic restoration was performed to turn that result into a PASS.
The exact 20 reviewed sources and review manifest used by the physical cycle
are preserved in its `executor-source-snapshot` directory.

Independent device checks on 2026-09-08 established platform PASS (27 checks)
and authenticated HTTP PASS (10 checks) under
`outputs/postflash/f321-independent-20260908T0010`. The original UI result there
is retained as FAIL: its only reported failures reject the legacy
`application/x-javascript` MIME type, while installed file hashes and frontend
bundle identity passed. The host verifier was corrected without altering the
sealed firmware or reflashing the router.

Fresh checks at 2026-09-11 09:13 UTC are recorded under
`outputs/postflash/f321-independent-20260911T091309Z`:

| Evidence | Recorded result |
| --- | --- |
| `platform/status.json` | PASS, 27/27: pinned SSH, exact F321 release, Linux 5.10, boot-ready state, storage boundaries, both radio control planes, APIs, authentication boundaries and bounded fatal search |
| `ui/result.json` | PASS_UI_FILE_API_AND_PUBLIC_HTTP: 12 installed file hashes, exact frontend identity and 13 public HTTP/MIME/authentication checks |
| `authenticated-http/result.json` | PASS_AUTHENTICATED_HTTP_SESSION, 10/10: login, cookie attributes, exact dashboard and frontend bundle, session API, logout and rejection of the expired session |

The file-only result
`outputs/postflash/f321-acceptance-20260911T091500Z/result.json` reports
`PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION`. It verifies the sealed candidate,
all 20 executed snapshot files against review `467dab55...`, the physical
write/readback/boot transcript and the three dated postboot gates. It preserves
the original promoter STOP and is not a new hardware operation or a release
qualification. The UART network-ready marker was not observed before the
parser abort; subsequent readiness is supported by the independent SSH gate.

The observed release is `lyoko-foundation-6.8.5-f321-classic-ui-f314-device`,
build `ad60c8e1e49dfbbf`, on Linux `5.10.260-openmitrastar-radiohw`.
These reports establish installation, boot from mtd4, management/control-plane
readiness and the HTTP session flow. Repeated cold boots, on-device browser
JavaScript, HTTPS/TLS, fresh 2.4/5 GHz client association and bidirectional
traffic, long soak and CAC/DFS RF acceptance remain separate physical gates.
F321 does not complete the wider Linux 5.10 or Lyoko Full Liberation mission.

A later physical-browser smoke test on 2026-09-11 proved JavaScript mount,
live-data navigation, classic branding and login/logout, but found the
config-store status 502 and legacy DFS alias defects. Their source corrections
and static build are offline only, not changes to this sealed image. See
`docs/OPENMITRASTAR_F321_BROWSER_ACCEPTANCE.md` for evidence and the required
versioned integration/physical retest. Browser integration is not fully accepted.

## Selected baseline

The pinned SSH observation at `2026-09-07T22:32:41Z` reported:

- `OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device`
- `OPENMITRASTAR_BUILD_ID=a2775c160f5a9b21`
- Linux `5.10.260-openmitrastar-radiohw`.

Evidence: `outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9/device-identity-readonly.json`.
This is a release observation, not a whole-flash readback. The selected input is
the exact local F314 image with SHA-256
`a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11`.

An earlier F319-derived F321 preparation remains untouched in the private
`f321-device-bound` directory with candidate hash `0b089e13bd6660922640aa6107318cd2d4cdf78ccf75d5bea0cf462093a28064`.
It is superseded for this UI-only campaign by the F314-derived candidate below.
It was not installed and does not establish that F319 is currently running.

## Exact candidate

Private directory:
`/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f321-f314-device-bound`.

File:
`openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.

| Property | Value |
| --- | --- |
| Candidate bytes | `5,337,088` |
| Candidate SHA-256 | `eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18` |
| Full physical slot bytes | `7,995,392` |
| Full-slot SHA-256, local expected only | `076afb4ba70b511947d1bd6f78eb5b3b62378889a4e20930a7b5c8022589cbc8` |
| Full-slot CRC32, expected and physically observed | `6ed8e483` |
| Bootbase contract | `PASS` |
| Rootfs offset within mtd4 | `0x180000` |
| Rootfs window | `0x460000` |
| Remaining rootfs space | `823,296` bytes |
| Reserved store begins | slot offset `0x5e0000`, still erased |
| Product release | `lyoko-foundation-6.8.5-f321-classic-ui-f314-device` |
| Firmware build ID | `ad60c8e1e49dfbbf` |
| UI package build ID | `72dd5d1877544af9` |

The UI package is
`outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9` with manifest SHA-256
`4c2a8b9536e28a55fc051a66f7a98df85b0417b90a3274d9f9d3c0c040a8626e`.

## Change boundary

The only rootfs changes are the packaged classic TSX presentation, its asset
identity, the exact hash-pinned frontend API identity transform and the F321
release record. The authenticated `/dashboard.cgi` entry, session handling,
credentials, radio controls, native kernel, DTB, calibration-dependent inputs
and storage modules remain identical to F314. Metadata is compared after
native Linux extraction, including owner/group, modes, symlinks and hardlinks.

No F319 SPI probe, F320 read probe, F315/F316 native radar module or the separate
`lyoko-dfs-contract-v1` control overlay is added. This firmware continues to use
the existing F314 DFS boundary. UI visibility of CAC/DFS does not enable RF
transmission or establish detector acceptance.

## Offline verification

- Build: `outputs/preflight/f321-classic-ui-20260907T223713Z/result.json`.
- Independent reproducibility build: `outputs/preflight/f321-classic-ui-20260907T223823Z/result.json`.
- Exact final-path Bootbase and file-only review:
  `outputs/preflight/f321-f314-review-20260907T2239/plan.json` and
  `outputs/preflight/f321-f314-review-20260907T2239/bootbase-contract.json`.
- `tools/test_f321_classic_ui_candidate.py`: 12 passing tests covering pinned
  lineage, release changes, manifest identity, protected files and radio/module
  exclusion.
- Both builds produced identical rootfs, complete webformat, kernel, DTB,
  configuration and debug sidecars. The private directory includes the complete
  source/target inventory, package manifest, `SHA256SUMS` and `known_hosts.f321`.

Recheck without replacing the original candidate:

```powershell
python tools/build_f321_classic_ui_candidate.py `
  --base f314 `
  --package outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9 `
  --package-manifest-sha256 4c2a8b9536e28a55fc051a66f7a98df85b0417b90a3274d9f9d3c0c040a8626e `
  --baseline-observation outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9/device-identity-readonly.json `
  --verify-reproducible
```

`tools/preflight_f321_classic_ui.py` is file-only and has no execute mode.
Each invocation requires a new output directory and explicit candidate and
package hashes. It does not acquire UART, connect to the device, reboot, start
TFTP or alter runtime state.

## Recovery and physical decision

The rollback artifact remains the exact F314 image in the private
`f314-device-bound` directory: SHA-256
`a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11`,
full-slot CRC32 `d6b13baa`.

The production file-only recovery-proof reader revalidated the historical
Bootbase self-restore at
`outputs/recovery/f319-f314-rehearsal-detached-20260907T111355Z/run/result.json`,
including the underlying transcript digests. This does not prove recovery from
a hard CPU lockup or partial erase. It does not establish a working
`mtd3/linux_safety` rescue rootfs.

Decision at packaging: **NO GO for physical execution**. The immutable manifest
retains `candidate_eligible=false`, `flash_supported=false` and
`release_eligible=false`. The later owner-authorized installation above used a
separately reviewed F321 promoter/rollback contract, exact candidate binding,
fresh identity/UART ownership, backup/readback evidence and the F314 recovery
contingency. Those records do not rewrite the packaging decision or authorize
a different artifact. No protected partition, logical mtd6 or boot environment
was a write target.

The installed F321 evidence above qualifies boot, pinned SSH, authenticated
HTTP/API and both radio control planes. Client/traffic and CAC/DFS hardware
validation remain separate campaigns. F322 prepares a disarmed F315 shadow
provider over this UI offline; it is not installed and has no DFS TX authority.
See `docs/OPENMITRASTAR_F322_SHADOW_CANDIDATE.md`.

## Reviewed installer used by the recorded cycle

The executor-review blocker was closed offline on 2026-09-07 UTC. The sealed
candidate manifest above remains unchanged. The separate review manifest is
`outputs/preflight/f321-executor-uart-final-20260907T234646Z/executor-review.json`, SHA-256
`467dab559f828594d9d94c8146259158a10a83a107f94c4cef9bbb5095c7c174`.
It binds the exact candidate, 20 executor/dependency files and the focused test
report. These hashes provide integrity checks; they are not signatures or user
approval. Its `physical_authorization` and `hardware_actions_performed` fields
are both false.

Entrypoints:

- `tools/promote_f321_mtd4_direct.ps1`: exact F314 to F321.
- `tools/rollback_f321_to_f314_mtd4.ps1`: exact F321 to F314.
- `tools/f321_mtd4_bootbase_flash.ps1`: isolated hardened backend; original
  F45/F319 promoters, backend, recovery scripts and acknowledgements are intact.
- `tools/f321_mtd4_one_shot.py`: UART-only wrapper of the unchanged F45 runner,
  selecting `tools/f321_uart_ymodem_load.py` for the RAM transfer.
- `tools/post_flash_f321_ui_gate.py`: pinned SSH hashes for the UI, API and
  release, exact frontend bundle metadata, public asset bytes/MIME types and
  anonymous dashboard/API rejection. This gate does not perform an authenticated
  HTTP browser session or a physical client traffic test.

Both entrypoints default to file-only dry-run. The following is the historical
review invocation for the sources used by the recorded physical cycle:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/promote_f321_mtd4_direct.ps1 `
  -ExecutorReview outputs/preflight/f321-executor-uart-final-20260907T234646Z/executor-review.json `
  -ExecutorReviewSha256 467dab559f828594d9d94c8146259158a10a83a107f94c4cef9bbb5095c7c174
```

Subsequent host-verifier fixes change source hashes. The historical review
therefore must not qualify modified current sources; its exact inputs remain
in the execution snapshot above. A future hardware action needs a review of
its actual executor. Fixing a verifier does not require another F321 flash.

The recorded `promote-plan.json` and `rollback-plan.json` in the same directory
both report `executor_review_verified=true`, `physical_ready=false` and
`hardware_actions_performed=false`. Missing or changed review evidence is a
hard refusal in execute mode. Separate, explicit user authorization is bound to
`OPENMITRASTAR_F321_MTD4_EB8E23AC` for promotion, including the documented exact
F314 restoration contingency. Standalone restoration has the distinct
`OPENMITRASTAR_F321_ROLLBACK_TO_F314_A0C7350A` acknowledgement. Merely knowing or
printing either string does not constitute authorization.

The authorized cycle takes the exclusive physical lease, revalidates historical
F314 recovery evidence and binds pinned SSH identity to the actual COM3 console
with a fresh nonce before reboot. Transport is fixed to UART/YMODEM with an
already acquired Bootbase prompt. There is no TFTP fallback, SPI probe load or
radio-setting operation. Only the first `0x5e0000` bytes of physical
`mtd4/linux_live` may be erased; the reserved store and protected partitions
remain outside that erase.

Before writing, the backend rereads current and protected flash regions and
checks their CRCs against the pinned local backup/image. It rejects errors even
when the same UART response contains a successful prompt, requires the exact
erase acknowledgement, and verifies the erased prefix's `aa86bf2e` CRC before
writing. Afterwards it requires the full-slot CRC and an exact, nonzero byte
count from `cmp.b`, then persistent boot, pinned SSH, the existing platform
gate and the new UI/API gate. A SHA-256 shown for the full slot is explicitly
the expected hash of the local padded image, not a SHA-256 computed on hardware;
the observed physical evidence is CRC32 plus the full candidate-prefix compare.

Automatic F314 restoration is allowed only after a complete, independently
checked writer PASS followed by a failed postflash gate, while the same live
lease and original physical binding remain held. Timeout, missing markers,
partial/ambiguous writes or unproved process termination stop the cycle without
retry or automatic restoration. Native helper descendants run in a Windows
Job Object before hardware helpers start; containment failure prevents a second
writer and keeps the hardware lease. A hard CPU lockup can still require the
owner's manual power cycle; this is not a guarantee of unattended recovery.

`qualification.xml` records **50 passing focused tests**. They cover zero/short
byte comparisons, error-plus-prompt, erase failure, absent markers, ACK refusal,
dry-run behavior, rollback sequencing, containment failure, LF-only SSH stdin,
UI/API hash drift and anonymous access. The UART cases also cover a stuck TX
queue, short/expired writes, bounded prompt retries, no `loady` without a prompt,
and propagation of a write timeout through the real YMODEM sender without
retrying that failed write. The local timeout test launched and
terminated a disposable Python child and confirmed its PID was absent; it did
not use hardware. Typical UART installation is approximately 10–20 minutes per
image, with another transfer if restoration is needed; the flash helper timeout
is 1,800 seconds and the platform readiness window is 360 seconds.

The F321 loader starts its prompt deadline before the first TX and uses the
remaining budget for that write. It sends at most three additional blank CR
probes, only before `loady`. Each write shares a deadline with TX queue drain;
it does not call the vendor's unbounded `flush()`. Failed/partial writes are
propagated through the YMODEM wrapper instead of being swallowed and retried.

During the transfer, each real YMODEM ACK callback appends and closes one JSON
line in the attempt's `writer/uart-ymodem-progress.jsonl`. Records contain UTC
and monotonic time, `phase`, `acked_bytes` and `total_bytes`. They prove sender
progress only; the separate final RAM validation status and flash/backend
evidence remain mandatory. Read the file contents to observe progress; cached
directory metadata for an open log is not evidence of absent RX or TX. These
timeout/observability changes do not establish a hardware failure in the
interrupted attempt. Earlier executor reviews remain immutable historical
evidence and do not validate the changed executor sources.
