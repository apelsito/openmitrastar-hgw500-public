# F367r4: interpret the hostlink completion contract

2026-09-22. **PASS_OFFLINE_F367R4_HOSTLINK_ACK_IMAGE**.
Only `qdrv_hostlink.c` changes from the functional F367 source. The locked R3
shell, preamble protection, provider, kernel, engine, supervisor, CAC and NOP
policies are retained.

## Concrete contract

The shared header defines `QTN_HLINK_RC_DONE=1` and `QTN_HLINK_RC_ERR=2`.
`qdrv_send_ioctl_owned()` waits for one of those completion bits, then returns
the raw descriptor `ioctl_rc`. A completed value1 is therefore a DONE
acknowledgement, not a POSIX error or a pending response. The new F367 channel
guards and existing strict TX adapter expected zero success and misclassified
that return. The physical run advanced through core/VAP before reporting
`channel-command error=1` and `xmit-stop-unconfirmed rc=1`.

There is an important legacy exception: a dead-MAC early drop also returns1,
without publishing a descriptor. R4 distinguishes that branch inside the
producer; it does not blindly accept every integer1 at the consumer.

Only these three named functions opt into the normalized result:

| Function / command | Normalized contract |
| --- | --- |
| `qdrv_hostlink_setchan` /17 | DONE without ERR →0 |
| `qdrv_hostlink_setchan_deferred` /35 | DONE without ERR →0 |
| `qdrv_hostlink_xmitctl` /26 | DONE without ERR →0 |
| Dead MAC before publication | `-ENODEV`, no descriptor publication |
| ERR or missing completion bits | Failure |
| Allocation error or transport timeout | Existing negative failure retained |

The generic API and retained beacon path keep their original raw return
contract. Mailbox layout, wire constants, publication barriers, waiting
budgets, descriptor ownership and timeout behavior are unchanged. Deferred
command acknowledgement does not claim the radio has already switched;
the existing MuC switch events and admission state still govern that step.
Likewise, TX command acknowledgement is not independent RF-silence evidence.

New bounded numeric traces are `OMF367_HLINK_ACK` with command, raw return,
DONE/ERR and normalized result. The dead-MAC branch explicitly reports
`reason=mac-dead published=0`. They introduce no extra MMIO read.

## Qualification

`outputs/preflight/f367r4-hostlink-ack-20260922T150651Z/result.json`
passes23 checks using the actual producer and channel/TX consumer bodies.
Mailbox, IRQ, allocation and wait-clock boundaries are explicit fixtures.
Checks cover DONE1, ERR2/3, pending then completion, pending timeout,
allocation failure, dead MAC without publication, strict TX latching, and
unchanged raw legacy results. This replaces the previous assumption that a
fake zero return represented the real hostlink interface.

The component result is
`/workspace/OpenMitraStar-build/f367r4/f367r4-ack-20260922T150827Z/result.json`.
qdrv is695,704 bytes, SHA-256
`8d51d2952b2db5a45a556463ded715d4fdf7c543c141e3a0e94c836ccd906319`.
Two builds match exactly; 1,979 imports across41 installed modules and existing
parameter/lifetime checks pass. Provider and other binary qualifications are
reused by SHA; no unrelated bank is rerun.

## Immutable image

Private result: `analysis/f367r4-fullimage-20260922T151701Z/result.json`.
Private directory: `f367r4-f365-hostlink-ack-device-bound/`.

| Property | Value |
| --- | --- |
| Bytes | 5,459,968 |
| Image SHA-256 | `d8ea968d3bebfb81725a862b345a8c443b20f16501bfdb1db96435eb4903c805` |
| Manifest SHA-256 | `49212304d4ee05b3f9899ad6baedd1609dd1d17a41b785da8aba21618c98ef25` |
| Product | `lyoko-foundation-6.11.3-f367r4-hostlink-ack-device` |
| Build ID | `ddd82999d5cfadb4` |
| Prefix CRC32 | `7b848f5f` |
| Full-slot CRC32 | `f21df41c` |
| Full-slot SHA-256 | `7a861e7d969f41e8a840e508217da6c92e7503f1febf65dc9b50e1659dffcdb0` |
| Bootbase / slot fit / reproduction | PASS / PASS / two identical repacks |

The native helper instruction sequence is unchanged; its literal qdrv hash,
driver contract and catalogues bind the new module. Exact F365 recovery remains
full-slot CRC32 `118901d4`, with preserved journal CRC32 `5d2ee646`.
The root-owned physical bootstrap/CAC/client/NOP gate remains pending. No
hardware access or flash was performed by the implementation agent.
