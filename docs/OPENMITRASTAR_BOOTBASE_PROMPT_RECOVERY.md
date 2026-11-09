# HGW-500BNA Bootbase prompt recovery after a pre-erase TFTP abort

Checkpoint: 2026-09-19 UTC. Target: HGW-500BNA-QCv2 A2, COM3, 115200 8N1.

An empty command line is not a harmless prompt probe in this U-Boot. It repeats
the last repeatable command. After `tftpboot`, sending CR alone or Ctrl-U followed
by CR can start another TFTP transfer. If the host server has already closed,
the router waits for the transfer instead of returning a prompt. This incident
did not establish a dead UART: an explicit Ctrl-C recovered the prompt, and the
unchanged F321 installation subsequently passed its platform gate.

## Confirmed command semantics

The local Quantenna U-Boot sources explain the failure mechanism:

| Source | Relevant behavior |
| --- | --- |
| [common/main.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/common/main.c), lines 460-488 | `readline()` returning zero preserves `lastcommand`, sets `CMD_FLAG_REPEAT`, and calls `run_command(lastcommand, flag)`. |
| [common/main.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/common/main.c), lines 1012-1032 | CR completes the input line. Ctrl-U erases the current input but does not clear command history; Ctrl-U plus CR therefore produces an empty line. Ctrl-C returns an interrupted input result. |
| [common/cmd_net.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/common/cmd_net.c), lines 46-55 | `tftpboot` is registered with its repeatable flag set to `1`. |
| [net/tftp.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/net/tftp.c), lines 617-646 | A new transfer prints its server, filename and load address, then `Loading: *\b`. The backspace is a progress decoration. |
| [net/tftp.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/net/tftp.c), lines 560-576; [net/net.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/net/net.c), lines 581-615 | Timeout can restart the network attempt; waiting a little longer does not necessarily produce a prompt. |
| [net/net.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/net/net.c), lines 500-506 | Ctrl-C during the network loop calls `eth_halt()`, prints `Abort`, and returns an error to the command interpreter. |

This is command-interpreter behavior, not an established difference between
PowerShell `SerialPort.ReadExisting()` and pyserial. Changing the host serial
library while retaining an empty-line probe does not correct it.

At this checkpoint, [BoundedUartChannel.acquire_prompt](../tools/f325_ethernet_uart.py)
at lines 189-198 still sends `b'\x15\r'`. That probe must not be reused to recover
a console after a repeatable command. A fresh boot with empty history and a
console after a successful TFTP are different states.

## Physical evidence and its limits

The exact F325 Ethernet attempt
[f325-ethernet-20260919T004201Z-f14674b0](../outputs/flash-watch/f325-ethernet-20260919T004201Z-f14674b0/result.json)
stopped before the flash writer. Its
[RAM result](../outputs/flash-watch/f325-ethernet-20260919T004201Z-f14674b0/writer/ethernet-ram-result.json)
reports `failed_stage=tftpboot`, `error_code=transfer_count` and `flash_writes=0`.
The failure was the host parser's transfer-count format; the server separately
recorded all 5,320,704 payload bytes acknowledged with zero retransmissions in
[its completion event](../outputs/flash-watch/f325-ethernet-20260919T004201Z-f14674b0/writer/tftp-process/child.stdout.jsonl).
Transfer completion is not a RAM CRC, flash or boot acceptance.

The earlier
[unsuccessful prompt recovery](../outputs/recovery/f325-preerase-normalboot-20260919T0047/result.json)
ran at 00:45:51-00:46:09 UTC. It received 403 bytes, including one `0x08`, but
no prompt, and sent no boot command. That response is consistent with a repeated
TFTP start and its `Loading: *\b` decoration. The report preserves byte metadata,
not the complete response text; do not present an invented transcript as evidence.

The successful
[recovery result](../outputs/recovery/f325-preerase-normalboot-20260919T0051/result.json)
ran at 00:49:26-00:49:29 UTC; the directory suffix is an evidence label, not its
execution start time. It records:

- One Ctrl-C byte without CR at stage `interrupt-preerase-ram-wait`.
- `abort_seen=true` and `prompt_seen=true` in the 39-byte response.
- The guarded `bootcmd=bootselect` contract and observed `bootselect=0`.
- A normal `boot` command sent, with `flash_writes=0` and
  `boot_environment_saved=false`.
- `ram_crc32_observed=null` and `ram_candidate_verified=false`. The diagnostic
  image in RAM was not qualified or booted.

The recovery report deliberately retains `NORMAL_BOOT_REQUESTED_UNVERIFIED`.
The separate
[platform result](../outputs/recovery/f325-preerase-normalboot-20260919T0051/platform-after-uart-boot/status.json)
at **00:51:13 UTC on 2026-09-19** passes all **27/27** checks, including pinned
SSH identity, release, kernel, boot readiness, both radio control planes,
management bridge and bounded fatal-marker search. Its
[device output](../outputs/recovery/f325-preerase-normalboot-20260919T0051/platform-after-uart-boot/router.stdout.log)
identifies `lyoko-foundation-6.8.5-f321-classic-ui-f314-device`, build
`ad60c8e1e49dfbbf`, and Linux `5.10.260-openmitrastar-radiohw`.

Together these records establish recovered F321 boot and platform readiness.
They do not establish F325 installation, repeated cold boot, client traffic,
DFS/CAC acceptance, or successful boot of `mtd3/linux_safety`.

## Restricted recovery procedure

**Ctrl-C is permitted by this procedure only after evidence establishes a
pre-erase abort and an outstanding RAM-transfer wait. Never use it when a flash
erase/write may be active or the writer's state is ambiguous.** A missing prompt
alone does not establish that precondition. This document does not authorize
device access or replace applicable owner authorization and hardware guards.

1. Bind the intended board and COM3 adapter, establish exclusive ownership, and
   inspect the exact attempt's writer, RAM, helper-containment and cleanup
   records. Require zero flash writes and no reached flash-writer phase.
2. For that proven RAM-transfer wait, send **one byte `0x03` without CR or LF**.
   Read the bounded response and require a fresh Bootbase prompt; record whether
   `Abort` was observed. Do not send empty lines or Ctrl-U plus CR to provoke a
   prompt, and do not repeatedly retry an unclassified console operation.
3. Issue a nonempty `printenv bootcmd bootselect` command. Validate the preserved
   normal boot command and the expected selector against the known-good image
   for this exact unit. In this incident they were `bootcmd=bootselect` and
   `bootselect=0`; the digit alone is not a general proof of a safe image.
4. Request the validated normal `boot`, preserving the selector. Do not call
   `bootm` on the unverified diagnostic image in RAM. Confirm the command's
   transmission, then independently verify pinned SSH, the installed image,
   kernel and platform readiness.

The current narrowly bound implementation is
[recover_f325_preerase_boot.ps1](../tools/recover_f325_preerase_boot.ps1):
lines 5-15 validate the exact clean pre-erase attempt, lines 43-50 acquire the
guard and send Ctrl-C without CR, lines 51-55 validate the boot-selection
contract, and lines 60-67 request normal boot. It is a hardware recovery script,
not a read-only status command. Its separate RAM CRC observation does not
qualify an image when `ram_candidate_verified=false`.

This recovery did not require a power cycle, cable/electronics work, an erase,
or a firmware write. It used no `setenv` or `saveenv` and did not alter the
preserved boot selection. Do not add reset-line pulses, UART reconfiguration,
TFTP restarts or boot-environment writes merely to obtain a prompt.

## Separate TFTP autostart concern

The completion path in
[net/net.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/net/net.c),
lines 546-559, reports the byte count, sets volatile `filesize` and `fileaddr`,
halts Ethernet and returns. The caller in
[common/cmd_net.c](../work/volatile-loader/build/Quantenna-GPL/u-boot-2009.06/common/cmd_net.c),
lines 220-245, can subsequently call `bootm` when `autostart` is exactly `yes`,
or execute a script when the compiled feature and `autoscript=yes` apply.
Future RAM-transfer preflight must inspect these settings instead of assuming
that the command name means load-only. This is distinct from empty-line
repetition; it was not established as the cause of this recovery incident.
