# Linux UART receive diagnosis after F323 prewrite aborts

F321 was recovered by the owner and passed the 27-check platform gate at
2026-09-11 18:08 UTC. F323 remains uninstalled. None of the three F323 attempts
reached an erase or flash-write operation; original STOP records are preserved.

## Scope

The new `tools/hgw_uart_rx_integrity_probe.ps1` obtains the shared F319 lease
and a fresh pinned SSH/UART nonce binding to the F321 HGW. It opens COM3 for
receive only, with handshake off and DTR/RTS/Break false. A separate SSH command
emits a finite 32,768-byte ACK/C pattern from the Linux console between unique
markers. The host sends no UART command, does not reboot and does not write
firmware or radio configuration. Capture stays in bounded memory; only counts,
hashes and sanitized states are retained. Sender termination, receiver closure,
post-SSH state and lease release precede publishing the final result.

This is a specific periodic-pattern receive window, not proof of host TX,
full duplex, Bootbase, YMODEM, a whole cable/adapter, or release completion.

## Observations

1. `outputs/uart-diagnostics/hgw-rx-20260911T183352Z/result.json` failed the
   exact-frame comparison: 34,040 bytes were received where 32,768 were expected.
   F321 remained reachable and no serial driver error event was reported.
2. `outputs/uart-diagnostics/hgw-rx-classified-20260911T184315Z/result.json`
   identified three `OMEMAC poll` markers inside the frame. There were 16,384
   ACK bytes, 16,391 C bytes and 990 other printable/whitespace bytes. The frame
   stayed FAIL: classification did not filter data or turn it into a pass.
   Concurrent kernel Ethernet diagnostic output contaminated this window;
   these results alone do not demonstrate electrical corruption.
3. `outputs/uart-diagnostics/hgw-rx-quiet-20260911T185337Z/result.json` reports
   `PASS_LINUX_UART_RX_WINDOW`. During this window only informational console
   display was temporarily restricted; kernel log storage was not cleared.
   The producer traps exit/signals to restore the prior printk tuple, and the
   host independently rereads it after the probe.

Quiet-window facts:

- Expected and received payload: **32,768 bytes**.
- Expected and observed SHA-256:
  `e714a1f99365917e72b4610bf3c91c4afdb253d3ab10e814480ba7c24f8063c7`.
- ACK bytes: 16,384; C bytes: 16,384; other payload bytes: zero.
- Serial error events: zero; no reconnection or capture gap was introduced.
- Original and restored printk tuple: **`7 4 1 7`**, including independent
  post-probe SSH verification.
- F321 postcheck: PASS; receiver and sender containment verified; lease released.
- No reboot, flash, radio change or raw serial recording.

## Interpretation and next decision

The clean Linux-to-host RX window is real but narrowly scoped. It does not
explain the non-protocol bytes seen during the earlier Bootbase transfers, and
must not justify another identical large UART upload. A previously completed
YMODEM load proved the exact F323 RAM CRC once, but installation remains unproved.

Keep F321 operational. The next transfer strategy should be validated separately
(for example, Ethernet for bulk data with a reviewed loader/recovery procedure),
with appropriate ownership, topology, privacy and authorization gates. The
existing owner authorization for the exact F323 image and controlled F321
recovery is retained; it is not blanket authorization for arbitrary network
exposure, transport changes, boot-environment changes or other firmware.
