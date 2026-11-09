# F332 qdrv readiness, OCAC continuity and shutdown handshake

Prepared on 2026-09-21. This is an offline integration over the verified F334
qdrv profile. F334 firmware, its 86-source executor and the fresh recovery
runner remain unchanged. No router, UART, RF, TFTP or flash action was performed.

## Result

**Loadability blocker identified after the offline builds:** the pinned Linux
5.10 kernel's `kernel/module.c:1432` (`inherit_taint`) rejects a module that uses
GPL-only symbols and imports a proprietary module. The F332 provider imports
the proprietary OEM engines, while both the provider and qdrv use GPL-only
kernel symbols. Taint inheritance therefore prevents this bundle from loading;
successful compilation and symbol linking do not qualify a runtime deployment.
No license declaration or kernel enforcement may be changed to bypass this.
Keep this handshake as tested source for the next integration, with the exact
OEM engines moved behind a bounded userspace interface. No F332 firmware or
flash acceptance follows from this document.

`outputs/kernel-port/f332-qdrv-ready-20260921T122632Z/manifest.json` records:

- qdrv module: 684,836 bytes, SHA-256
  `db24f656c87c51d741bd541b0aff9682d25bc7eba0e4a17013b38a22720faf40`.
- Two complete Linux 5.10 ARC builds are byte-identical.
- All 14 F334 parameter names/permissions and the functional 48-byte beacon
  preflight implementation remain intact.
- Seven behavioral groups compile the exact readiness/OCAC helper used by
  qdrv. Three further cases compile the actual qdrv exit function.
- Fifteen source-order/lifetime checks and GCC static analysis pass.
- The module links to `qtn_radar_f332`, including the new scan-context,
  ready-generation and lifetime-drain APIs. The internal radar compatibility
  object is excluded.

Source: `work/linux510-radio-port/quantenna-f332-ready-handshake/`.
Builder: `tools/build_f332_qdrv_readiness.py`.

## CAC and restart behavior

The inherited qdrv path started its CAC timer before calling `radar_enable`.
That ordering is insufficient for a provider whose configuration and first
validated batch complete asynchronously.

F332 now requests the provider context first, keeps TX stopped, and requires a
nonzero stable `radar_ready_generation()` together with `radar_get_status()`
before starting CAC or using the existing available/OCAC-done path. The
`start_cac` entry itself also enforces this prerequisite.

A delayed-work retry checks every 50 ms for at most five seconds for the same
kind/channel/bandwidth. Repeated IRQs do not move that deadline or postpone an
already queued retry. Timeout stops retrying and leaves the service gate closed;
it does not shorten CAC or fabricate readiness. The delay is software scheduling,
not a hardware watchdog.

CAC stores the detector generation at its start. Completion requires that same
generation and channel to remain current. An interruption clears the old CAC
state and requires a complete new interval. PM resume and the existing
enable-detection helper reuse `qdrv_radar_on_newchan`; a still-valid generation
does not gratuitously reset a CAC already running. The inherited 70/600-second
timers and 1,800-second NOP duration are preserved.

## OCAC behavior

The tasklet publishes scan context before querying readiness, outside the
provider's OCAC lock. An unready event produces no FIFO record, dwell credit or
TSF-history update. Retry work never replays a prior interrupt's dwell or point.

An accepted OFF_CHAN event stores its detector generation and scan channel.
The following ON_DATA event can contribute dwell only if both endpoints were
ready for that same generation/channel. End-ready after start-unready is
rejected. Channel/generation changes reset accumulated credit; interrupted
intervals cannot become successful intervals later.

`array_ps` is read while holding the OCAC lock. Capacity is checked against the
actual ten-element array before every write. Overflow records no point/dwell,
breaks continuity and disables/clears scan context outside that lock. The
provider's later input check is not used as a substitute for caller bounds.

## Lifetime

The original tree defined `qdrv_radar_exit` but did not call it from SoC teardown.
The new tree calls it before stopping MuC or releasing shared/ic state.

Shutdown closes retry admission, joins delayed readiness work, disables and
synchronizes the OCAC IRQ/tasklet, joins the initialized MuC sampler, and drains
timers. A stopping guard prevents an in-flight completion from re-enabling TX.
After `radar_stop`, the process-context `radar_wait_stopped()` API must confirm
worker/callback/query lifetime drain before qdrv clears its context. A refusal
propagates to SoC teardown instead of freeing the context.

This follows the provider's precise contract: a drained lifetime may return
success while an engine cleanup fault remains separately latched and prevents
reuse. IRQ/self-wait refusal is not treated as successful drain. No hardware
quiescence or SRAM restoration is claimed by this software handshake.

Physical readiness timing, DFS RF decisions, actual CAC TX suppression, channel
evacuation and release acceptance remain untested by these offline results.
