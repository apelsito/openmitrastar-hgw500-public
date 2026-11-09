# F323: alternative bulk transfer preparation

## Current boundary

This is an offline transport preparation, not an installation or executor
approval. F323 remains uninstalled. The most recent physical recovery evidence
is F321 at 2026-09-11 18:08 UTC, with 27/27 platform checks; the quiet UART receive
window at 18:53 UTC also ended with F321 reachable and console settings restored.
No further device contact is implied by this document.

Do not repeat the three stopped bulk YMODEM attempts. One of them verified the
complete F323 image in RAM; none reached erase/write. Their original STOP
results remain unchanged. See `OPENMITRASTAR_UART_RX_DIAGNOSIS_2026-09-11.md`.

The firmware is unchanged: 5,361,664 bytes, SHA-256
`9d8dbd5bd9a6c372e95d8f6365396f8eb4695ab61848cd49341d76fee2153c11`.
Its exact installation and conditional F321 recovery already have owner
authorization in `outputs/authorizations/f323-20260911T153634Z/authorization.json`.
This does not authorize additional private-image network exposure, host firewall
changes or volatile Bootbase network settings. Do not ask again for the existing
firmware authorization; resolve only the additional network scope.

## Observed Ethernet path

Host-only observation at 2026-09-11 19:14:17 UTC:

- PC source: `192.168.1.249`, interface 15, `Ethernet`, Realtek Gaming GbE.
- HGW peer: `192.168.1.90`, direct `192.168.1.0/24` route.
- The same interface carries the PC default route via `192.168.1.1`.
- No UDP/69 listener was observed; this must be rechecked immediately before use.
- The network profile was `Public`; that label is not proof of Internet exposure.
- Isolation is **not demonstrated**. No address, route or firewall was changed.

Evidence:
`outputs/preflight/f323-ethernet-preparation-20260911T191417Z/network-readonly.json`,
SHA-256 `8f12a6cadb83d21ec50743563ed3858a2c210c1b99440bf3ee7857cf18e76582`.
Do not disconnect or readdress this Ethernet interface automatically: it is also
the PC uplink. Do not use the historical `.43` TFTP default.

## Scoped server and plan

`tools/f323_scoped_tftp.py` serves one hash-verified immutable file to one configured
client IP. It permits octet reads only, no directory listing or uploads. Its
listener and accepted transfer share one monotonic deadline, with bounded ACK
retries and no second transfer after success or failure. Rejected names and
packet contents are not copied into evidence. Valid RFC2347 option pairs are
ignored with DATA1/512-byte fallback; malformed, duplicate or oversized requests
are rejected. ACKs outside the attempt deadline cannot advance the transfer.

`tools/prepare_f323_ethernet_plan.py` has **no execute mode**. Its output remains
`NO_GO_NETWORK_SCOPE_AND_EXECUTOR_REVIEW_PENDING`. Unit/loopback tests do not
qualify Bootbase Ethernet, the firewall path or a physical firmware write.

The combined focused run at 2026-09-11 19:34 UTC passed **122/122 tests**, with no
failures, errors or skips: 90 server cases and 32 plan/authorization cases. It
includes a complete 5,361,664-byte synthetic loopback transfer with exact content,
SHA-256 and 10,473 blocks including the final empty block verified. The actual
F323 payload was not served, even on loopback. The file-only plan revalidated
sealed local firmware inputs without executing the old writer.

Evidence is under
`outputs/preflight/f323-ethernet-preparation-20260911T191417Z/plan/`:
`result.json`, `plan.json`, `component-tests.xml` and four exact source snapshots.
The plan hash is
`4a9ee50e03a1276eb7bda253ccb77f412bb72856e48db60e8391e6bcca6841fc`;
the JUnit hash is
`b58b0563fe777c1d45cb7903d60cdb4ae5c533b8e9fa4471fc8dcf72781ba88c`.
These qualify the components only, not an Ethernet flash executor. The plan
binds the prior owner authorization by exact hash instead of merely asserting it.
Its listener-only firewall proposal explicitly leaves the ephemeral UDP data
return path for executor review.

### Protocol and writer handoff core, 20:01 UTC

`tools/f323_ethernet_ram_gate.py` and `tools/f323_ethernet_handoff.py` now implement
the protocol and handoff with injected adapters. **They have no physical CLI or
native adapters.** A new focused run passed **113/113 tests** (67 protocol cases,
46 handoff/evidence cases), with synthetic responses, callbacks and JSON/text
fixtures only. No socket, serial port, child process or real image was opened
by that test run. Earlier server tests and firmware builds were not repeated.

The protocol requires exact peer/image scope and a confirmed guard before each
command. One TFTP load must pass decimal/hex byte count, `filesize`, `iminfo`,
RAM CRC and closed-server checks. The handoff refuses to call the writer if RAM,
loader closure or the fresh guard fails; uncertain helper termination retains
the lease even if the first guard itself failed. It never retries or starts
recovery. The outer physical cycle must still decide postgate recovery.

The backend is unchanged, including its historical `candidate_transport=uart-ymodem`
label. That label is a fixed string in its **preloaded-RAM branch**, not proof of
bulk transport. The new evidence records `ram_load.transport=ethernet-tftp`
separately from UART-controlled flash and requires both Skip flags. It preserves
the raw backend log and independently binds the Ethernet/RAM evidence; it does
not invent YMODEM logs. `ethernet-server-result.json` is the same sanitized server
summary bound inside `ethernet-ram-result.json`; raw packet contents are excluded.

The new verifier also checks exact ordered erase/write dimensions, full-prefix
comparison and existing physical proof markers. Expected local SHA-256 remains
distinct from observed CRC; hardware SHA-256 remains unmeasured. The handoff
compares the same RAM bytes whose file hash was checked, not a later unchecked
read of the file.

Evidence:
`outputs/preflight/f323-ethernet-handoff-20260911T200026Z/result.json`,
`qualification.xml` and six source snapshots. Qualification SHA-256:
`8e2ec28de22a5dfc2690b7aebf95a55cff4cd1b7d1acdb4e4ebe360610e888b1`.
The status is `PASS_OFFLINE_PROTOCOL_AND_HANDOFF_NO_GO_PHYSICAL`. At that checkpoint
the bounded native adapters and parent integration were still missing; the next
section records the subsequent adapter work. The full executor is not reviewed.

### Native adapters and composition, 20:48 UTC

The native adapters and their composition are implemented:

- `tools/f323_ethernet_uart.py`: inert construction, guarded COM3 opening,
  one clean prompt probe, exact RAM-only command vocabulary, shared write/drain
  deadlines, bounded fresh RX and no raw UART logging.
- `tools/f323_ethernet_guard_process.py`: bounded inherited-context checker,
  exact source/output checks and explicit tracking of owned process handles.
- `tools/f323_ethernet_server_process.py`: one guarded child process running a
  checked server snapshot, exact ready/terminal events, no firmware copy and
  completion proved by the process handle rather than a PASS file alone.
- `tools/f323_ethernet_native_loader.py`: composes these stages and independently
  closes server, UART and guard helpers on every path. Defaults are inert; no
  CLI, reboot, firewall mutation or flash is provided.

The final combined run passed **111/111 tests**: 34 fake-UART, 21 fake-guard-process,
39 server-process and 17 composition cases. One server test runs a real synthetic
loopback lifecycle. No native UART factory, HGW, real firmware payload or LAN
listener was used. Independent static review found no component-level blockers.

Evidence:
`outputs/preflight/f323-ethernet-native-20260911T204832Z/result.json`,
`qualification.xml` and 14 source snapshots. Qualification SHA-256:
`c3f00631b8f36389432c85037dc916a3e3dcc56d40f54f9ff4a2ec492421d6fe`.
The status is `PASS_OFFLINE_NATIVE_ADAPTERS_NO_GO_PHYSICAL`, not full-executor
qualification. No earlier test/attempt result was replaced.

The child always reports `writer_ready=false`: it cannot witness its own exit.
`ram_handoff_ready` only describes checked RAM and local cleanup. The reviewed
parent must independently prove loader exit and no remaining Job descendants
before opening the writer. It must bind an actual owner network authorization;
passing a boolean to a library does not create authority. Parent promoter,
network/firewall integration and conditional F321 restoration still need their
scope-specific implementation/review after the network decision.

## Owner availability and restart boundary

The owner reported being away during the status request, then replied `ya estoy`
to the request to notify their return. The current availability update is
`outputs/coordination/hgw-owner-return-20260911T214920Z.json`, recorded at 21:49 UTC.
It supersedes the earlier away report; immutable qualification records retain
the availability that existed when they were produced. Return home does not
prove UART ownership/binding or authorize the separate proposed network exposure.
The exact F323/F321 firmware authorization remains unchanged.

The owner subsequently explicitly approved the temporary plaintext private-image
TFTP transfer on the observed shared LAN, with limited temporary firewall and
volatile Bootbase network settings. The approval is recorded in
`outputs/authorizations/f323-ethernet-20260911T215738Z/authorization.json`, SHA-256
`827f7d628cd89344e10fe8d7be39dd7b657f57291a35c45788b5e3f536bceaa4`.
The original F323/F321 approval remains valid; neither approval should be requested
again. Finalize and qualify the parent integration for this exact scope, without
another firmware build or a fourth identical bulk UART attempt.

The latest actual device observation is the owner-requested, pinned read-only
SSH check at **2026-09-11 20:44:24 UTC**: exit 0, F321 build `ad60c8e1e49dfbbf`,
Linux `5.10.260-openmitrastar-radiohw`, uptime 9,793.19 seconds and confirmed SSH
helper exit. It did not run another platform/radio suite or touch UART/flash.
F323 remains uninstalled. Resume hardware work only after the now-authorized
complete executor is qualified and fresh physical identity/ownership
checks pass. If recovery availability changes again, stop before reboot/flash.

The real image contains private device identity. TFTP has no transport encryption
or client authentication. An IP filter is not proof of isolation or a substitute
for owner consent to this temporary plaintext transfer. Prefer an isolated path
if the owner does not accept that exposure on the currently observed LAN.

## Required executor work after the network decision

The existing F323 UART review cannot qualify an Ethernet executor. In particular,
the old F321 backend has a dormant three-attempt TFTP branch, and its writer
verification expects UART-specific evidence. Do not enable it merely by changing
a transport flag. A new reviewed adapter must preserve all existing guards and:

1. Revalidate the exact source/interface/route, UDP occupancy, current F321 and
   sealed image/recovery inputs; acquire the live exclusive lease and prove the
   authenticated UART board binding before any UART transmission or reboot.
2. Never change host addresses/routes, disable the firewall, stop another owner,
   save Bootbase environment or change boot selection. Limit any separately
   authorized firewall rule to this run, program, peer, address and interface;
   record its identity and remove only that rule in confirmed cleanup.
3. Set only volatile `ipaddr=192.168.1.90` and `serverip=192.168.1.249`, if
   separately authorized. Preserve all protected/current-slot prewrite checks.
4. Start the one-file server just before the transfer, after slow prewrite
   checks, and require its exact ready event. Do not spend its 300-second global
   lifetime waiting for reboot or flash CRC scans. Use one transfer attempt;
   do not inherit the dormant three-attempt retry loop.
5. Require terminal server success, exact RAM byte count, `iminfo` and expected
   RAM CRC `81cec636` before entering the authorized mtd4 writer. Host-side TFTP
   success alone is not evidence that Bootbase accepted the image.
6. Keep write scope at mtd4 offset `0x007e0000`, prefix erase `0x005e0000`,
   slot `0x007a0000`. Preserve mtd0/mtd1/mtd2/mtd3/mtd5 and the store tail;
   logical mtd6 is not a physical write target.
7. Prove process/socket/firewall cleanup even on pre-erase failure. Stop on any
   uncertain writer or child-process state. Only a verified F323 write followed
   by a failed postgate permits one separately scoped exact F321 transfer under
   the same held lease; never chain F314 automatically.
8. Qualify Ethernet-specific transcript/result verification and conditional
   recovery with offline failure tests, then perform the physical platform/UI
   gates and real-browser retest. Neither TFTP nor this UI-only image establishes
   client traffic, DFS/CAC, persistent storage or final release acceptance.

The historical proven fallback remains exact F314 restoration to mtd4. A working
mtd3 boot is not demonstrated; merely retaining an image does not prove recovery.

No LAN listener, firewall change, UART action, reboot or flash was performed by
this preparation. Network scope is now authorized; qualification of the complete
Ethernet executor remains pending.
