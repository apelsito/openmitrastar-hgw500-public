# F355 — retain qdrv after mutation admission

F355 adds a software lifetime barrier to the F344 driver. It prevents ordinary
module removal and base-resource release once qdrv has admitted an operation
that may modify state. This addresses the unsafe unload/error paths identified
by F353. It does **not** establish a new MuC epoch, implement hot restart or
prove hardware quiescence. F344's immutable component bundle is unchanged.

## Protection and exact boundary

The first matched, policy-admitted command other than `get` or `stop` obtains
one reference to `THIS_MODULE` using the real Linux `try_module_get()` API.
The reference is acquired before dispatching the command handler. This is
deliberately conservative: `set` preparation, and a handler that subsequently
rejects its arguments, also retain the reference. No F355 code releases it.
The system must reboot before qdrv can be unloaded after that point.

An unmatched/policy-rejected command does not reach the claim. An instance
used only for read-only control inspection has no retained reference and can
still unload. This distinction concerns lifetime, not RF state: admitting a
command is not proof that hardware initialization succeeded.

F340 enables CONFIG_MODULE_UNLOAD and disables CONFIG_MODULE_FORCE_UNLOAD.
In its Linux 5.10 `kernel/module.c`, `try_stop_module()` first releases the
base reference; a remaining reference causes `delete_module()` to return
before invoking `module_exit`. If unloading wins the race first, either
MODULE_STATE_GOING or a zero refcount makes `try_module_get()` fail, so the
handler is not dispatched. F355 contains a compile-time rejection of a kernel
with forced module unloading enabled. It does not claim to support that bypass.

The secondary guard inside `module_exit` protects object cleanup if it is
invoked improperly; returning from that callback cannot cancel forced module
removal. The kernel reference is the mechanism that protects module text.

## Initialization and failure handling

Control commands are rejected until the last successful module-init step.
No later module-init failure branch exists after that readiness commit, so an
initialization error cannot hand the kernel a failure after acquiring the
permanent pin. A command waiting for the control mutex rechecks readiness
after it obtains the mutex. During unload, control sysfs is removed/drained
before proc state and the device context are released.

The same patch corrects related initialization ownership:

- The output semaphore and context are initialized before publishing procfs.
- A PHY-stats creation failure after successful control init removes those
  proc nodes before the module's initialization failure returns.
- Proc teardown completes its semaphore drain despite signals.
- A failed `device_register()` is paired with `put_device()` because Linux
  initializes the device's kobject even when `device_add()` fails.

Core start independently checks/acquires the pin before `hal_reset()` and
records a single core attempt. A boot/clearsram failure is latched. Further
control mutations cannot retry over the partial context. Pure lifetime status
remains available. The error path no longer calls the unsafe general teardown.

After retention, `qdrv_soc_exit`, shared-parameter revocation, WLAN exit and
hostlink exit refuse release before their destructive operations. Resource
bits, `qw`, published shared DMA and callback targets remain owned. A second
shared-parameter publication is rejected instead of replacing the retained
allocation. Cleanup of an allocation that failed address validation before
publication is unchanged; it was never advertised to firmware or callbacks.

No AuC/DSP reset, wire-layout change, new firmware command or guessed hardware
acknowledgement is introduced. The existing F344 VAP workflow and its refusal
after a published CSA remain separate. This patch does not make a failed
radio operational; retained memory is an intentional consequence of lacking
a proved hardware teardown boundary.

## Observation

`/sys/devices/qdrv/lifetime_state` is read-only and reports readiness,
retention, whether core start was attempted, the boot-failure latch, reboot
requirement, `release_supported=0` and the first admitted operation name.
It contains no credentials, calibration, client addresses or MMIO contents.

An installer or diagnostic runner must not expect to reclaim this driver after
`set`, `clearsram` or `start`. It must preserve management and use its separately
qualified reboot/recovery contract. F355 supplies no reboot executor and was
not installed or loaded on the router.

## Offline verification

The tests execute the actual F355 adapter together with extracted Linux 5.10
`try_module_get`, `try_release_module_ref` and `try_stop_module` logic. Kernel
services, procfs, devices, DMA and callbacks are explicitly fake host fixtures.

- 1,371 checks cover module ownership, eight initializer failure points,
  late callback access after rejected teardown, shared-pointer retention,
  sysfs wait/close ordering and 256 two-thread claim-versus-removal races.
- 26 checks execute the actual proc init/exit bodies, including three creation
  failures and initialization before proc publication.
- 18 source-order contracts bind pinning, no implicit unpin, retry prevention,
  teardown guards, init unwind and unchanged wire headers.
- A negative preprocessing check verifies the forced-unload build rejection.
- The full 26-module closure was rebuilt twice against F340. For the final
  sysfs/init refinements, qdrv is rebuilt twice and the other 25 identical
  modules are reused only after their sources, headers and configuration match.
  Symbol ownership, GPL-only/taint rules, dependencies, parameter profile and
  paired binary identity are checked again for the final closure.

These are software/offline checks, not physical module-load, unload, radio,
traffic or recovery evidence. Wi-Fi/RF/client acceptance remains USER_DEFERRED.
Bulky build outputs are on D:, with the C: >500 MiB guard checked by the
builders and final qualification. The final timestamped qualification records
the exact module, closure, source/test hashes and immutable F344 binding.
