# F367 controlled AP DFS52/20 candidate

2026-09-22. **PASS_OFFLINE_F367_AP_DFS_IMAGE**. The next uncertainty is the
physical CAC/client/evacuation/NOP gate. This is not a claim of RF conformity,
weather-channel support, completed DFS certification or release acceptance.

The prerequisite is the accepted R3 native pipeline and exact F365 return:
`outputs/acceptance/f366r3-acquisition-addendum-20260922T114659Z/result.json`,
SHA-256 `9201514a074decb9987cdaa174f25c19739ddc083e9a842179fec77cc633fb87`.
Its20 observations and338 advancing jobs prove native acquisition at36/80
with callback authority0. The original parser-failure result remains intact.
F367 construction verifies that addendum and every linked evidence hash.

## Immutable artifact

Private directory: `f367-f365-ap-dfs-device-bound/`.
Image: `openmitrastar-linux510-f367-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.

| Property | Value |
| --- | --- |
| Bytes | 5,455,872 |
| Image SHA-256 | `447f94aa1be95b1ba52a47d206978bc8a359e3c57e7435d475a3e49b9cb28aa0` |
| Manifest SHA-256 | `a335d25b1717a9e672684c41636293b73fea1937f56a6f1747486a78d406a8dc` |
| Product | `lyoko-foundation-6.11.0-f367-ap-dfs-device` |
| Build ID | `358284466b286751` |
| Prefix CRC32 | `28b8f386` |
| Full-slot CRC32 | `6f77010f` |
| Full-slot SHA-256 | `0b688309d272e1d4a312f22725b27ad20466b591b257b4ad6130e943e86eb2d9` |
| Bootbase / slot fit | PASS / PASS |
| Headroom before journal | 704,512 bytes |

Authoritative private result:
`analysis/f367-fullimage-20260922T122243Z/result.json`.
It contains the exact18 runtime path/hash bindings, the complete `campaign`
contract and the recovery/journal evidence for the root executor.

Recovery is exact F365, 5,382,144 bytes, SHA-256
`43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
full-slot CRC32 `118901d4`. The preserved sequence2 journal is CRC32 `5d2ee646`.
The kernel, DT, Ethernet, existing watchdog, inactive temperature diagnostics,
2.4 GHz files, identity and calibration remain exact F365 inputs. No protected
partition, boot environment or hardware was changed by this offline work.

## Functional boundary

Normal boot leaves5 GHz pending, with no radio acquisition or watchdog arm.
The explicit activation reuses the accepted R3 bootstrap atAP36/BW80, including
the exact EU command and OEM radar filter setter235/80. `qtn_radar_f367` uses
the original F338 userspace engine and the same UAPI device
`/dev/om-radar-f338`. Original acquisition, preprocessing, classifier and GPL
postfilter algorithms are unchanged.

F367 grants callback authority in its proof-bound native build. It permits only
AP52/BW20 for the first DFS gate, with non-DFS36 as escape. No STA, repeater,
OCAC or weather-channel operation is enabled in this profile.

The driver maintains a1,800-second startup DFS quarantine while36 remains
usable. This is our conservative local policy because NOP is not persisted;
it is not a new normative requirement. No event is backdated and no CAC/NOP
clock is renewed by the watchdog heartbeat.

`PREPARE52` rechecks actual kernel quarantine/NOP, role and ES region, then
requires a confirmed TX-off command before the controller applies mode20,
filter235/20 and channel52. Provider channel and bandwidth are published in
one request generation. Old transactions are retired; READY and CAC refer to
the coherent new generation.

A full70-second CAC is mandatory, with uninterrupted native detector
continuity. The implementation checks both the original tick policy and a
monotonic minimum; its timer has one conservative extra tick. Loss of readiness
invalidates admission and a return requires a new full CAC. Quick timers,
instant completion, mutable DOTH/test bypasses and administrative NOP clearing
cannot reopen TX in this candidate.

A radar event stops TX, records a1,800-second NOP for52 and invokes the existing
CSA machinery toward36. The NOP record remains observable for52 after escape;
re-entry requires expiry and a fresh CAC. The strict native callback wrapper
rejects a mismatched request/channel/width into a latched failure instead of
attributing it to a different context. Failed channel commands also latch
closed admission. F355 permanently retained ownership remains unchanged.

Software injection is explicitly labelled `SOFTWARE_INJECTION`; it exercises
the control path and does not prove RF radar detection. Provider callbacks have
a separate count and `NATIVE_PROVIDER` marker. Unexpected native events must
remain visible in the physical record.

## Runtime contract

```text
om-f367-control activate TOKEN32
om-f367-control status
om-f367-control enter-dfs
om-f367-control software-radar
om-f367-control stop
```

`activate` returns after bootstrap. The supervisor and keeper have closed SSH
stdio and ignore HUP before exec. The keeper continues independently, reporting
HEALTH under a short shared phase lock. Native startup phases remain bounded;
operational phases are at most60 seconds and use distinct sequence numbers.

The separate `/usr/sbin/om-watchdog-supervisor-f367` has a90-minute absolute
session limit, at most128 phases, a5-second HEALTH lease, wire version2 and
schema `openmitrastar.f367-supervisor-state/v1`. HEALTH cannot extend either
the current phase or total deadline. Its kernel/hardware support is the exact
F358 support. The original supervisor remains installed separately, and the
shared owner namespace prevents a second watchdog owner.

An `enter-dfs` request while quarantine or NOP is active returns16 with
`OMF367_REJECT ... mutated=0`. It neither changes the deadline nor faults or
ceases the healthy session. The kernel independently revalidates before any
mutation. Errors after starting a transition cause ABORT and CEASE. `stop`
does not unload dirty modules; the owner retains its FD for watchdog reset and
root performs the bound F365 return.

The read-only kernel parameter `openmitrastar_dfs_state` supplies cached RAM
state. `om-f367-status` combines it with allowlisted provider counters into
`openmitrastar.f367-state/v1`, including:

- `monotonic_ms`, quarantine start/deadline/remaining;
- channel/filter/phymode, ES/EU/DOTH/TPC and request/provider generations;
- waiting detector, active CAC, valid continuity, CAC start/deadline/remaining;
- NOP target52, start/deadline/remaining even when the current channel is36;
- TX admission, TX-off command acknowledgement and latched control/TX faults;
- separate provider, job/error, software injection and native callback counters.

`tx_stop_command_confirmed` is command evidence, not independent RF silence.
The status explicitly retains `rf_silence_proven=false`. READY0 is expected on
36/quarantine; active counted CAC requires READY and generation continuity.
The keeper ceases on faults, stalled engine progress or invalid counted CAC.
Numeric state parsing accepts only fixed keys and decimal values.

## Offline evidence

- Components:
  `/workspace/OpenMitraStar-build/f367-functional/f367-functional-components-20260922T120217Z/result.json`.
  qdrv695,212 bytes, SHA-256
  `186c60df3a565c0b622519585e2a4ef4f308c07cae41c501bb413c48eb6da5aa`;
  provider71,028 bytes, SHA-256
  `05ea135ef8977f84a35ad5a52601c88f4400e973c098857173ac0292e0ceb488`.
  Two identical builds, 41 installed modules and1,979 resolved imports pass
  dependency, export ownership, GPL-only/taint and protected lifetime/function
  checks. Original OEM engine SHA-256 remains
  `737cbdfeb429caba42929374c4a22eab549791c6af42fb3149c5ad64c048c85b`.
- Affected functional checks:
  `outputs/preflight/f367-functional-20260922T120620Z/result.json`.
  Actual C executes20,000 concurrent coherent-pair reads,10,000 transitions
  and26 control/policy/snapshot cases. Simulated clocks cover exact quarantine,
  CAC, generation loss, NOP rejection/expiry, fresh CAC and ABORT; they do not
  stand in for elapsed physical CAC/NOP.
- Runtime:
  `outputs/preflight/f367-runtime-20260922T121726Z/result.json`.
  Twenty-four checks run the actual helpers and actual v2 IPC with explicitly
  fake watchdog/radio backends, including HEALTH during a six-second startup
  phase, detached activation, unchanged NOP rejection, correct setter order
  and FD-held CEASE.
- Supervisor:
  `outputs/kernel-port/f367-supervisor-20260922T115143Z/result.json`;
  SHA-256 `ecd861a42812a8516f81e38fdad081089639f77a61c56335bf6c1110a926a477`,
  33,720 bytes. Its builder owns the separate bounded-policy/IPC qualification.
- Full image: two independent repacks, exact kernel sidecars, complete
  inventories/catalogues, Bootbase and stale-qdrv-hash checks pass.

The physical sequence is bootstrap, quarantine, enter52/20, CAC and AELITA
traffic, labelled software radar, escape36/NOP1800, denied early re-entry,
fresh CAC and client traffic after expiry, then CEASE and exact F365 return.
Real RF waveform/sensitivity testing and complete release acceptance remain
outside the claim of this candidate.
