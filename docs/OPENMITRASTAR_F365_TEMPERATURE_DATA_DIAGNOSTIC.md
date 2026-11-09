# F365: cached DATA diagnostics for the temperature timeout

F365 instruments the existing sensor read path on F364r3. It does not change
the F339 conversion table, mask `0x1000`, 100 ms polling policy, or startup
writes `2`, `0xfffffffe`, `1`. The F339 core remains byte-identical, SHA-256
`cc86ae1c45828f66681d7eb8a78ea31955770d77135319e380e1987f5bb93a3c`.
Activation remains explicit and boot does not access the sensor registers.

The discriminating physical precedent is
`/workspace/OpenMitraStar/f363-temperature-activation/f363-sensor-20260921T214213Z-12cff874/result.json`:
the activation writes succeeded, the first `temp1_input` read failed with
`Connection timed out`, and the watchdog returned to the inactive F363r2
baseline with platform/store checks passing. This is timeout evidence, not a
valid temperature or proof of the sensor clock/conversion mode.

Source is `work/kernel-port/versions/f365-temperature-data-diagnostic/`.
The `sensor_read` callback still performs one DATA `readl`. It records that
already-obtained word in RAM. A wrapper records the operation, first and last
words, read count, final errno and elapsed monotonic microseconds. It uses two
monotonic timestamp calls per access wrapper; the original core timing logic
and its own clock calls remain unchanged. Elapsed time excludes waiting to
acquire the sensor mutex and can include scheduling delays during the read.

Two independent caches are protected by the existing sensor mutex:

- `diag_hwmon`: last `temp1_input` or `interval` access.
- `diag_legacy`: last access through `topaz_read_internal_temp_sens`, including
  the periodic qdrv consumer. It cannot overwrite a hwmon failure.

These attributes are under the existing `topaz_internal` hwmon node. Reading
either attribute only formats its RAM cache while holding the mutex. It does
not call the core, `readl`, `writel`, the clock, or activation. The module keeps
`MODULE_VERSION("363")` for the existing validated admission helper and adds
`MODULE_INFO(diagnostic_revision,"365")`. The latter is modinfo metadata, not
a new sysfs attribute. The diagnostic JSON schema identifies the live interface.

Each file returns one JSON line:

```json
{"schema":"openmitrastar.f365-temperature-access/v1","source":"hwmon","operation":"none","sequence":0,"complete":0,"errno":0,"read_count":0,"first_word":null,"last_word":null,"elapsed_us":0,"elapsed_valid":0}
```

This example is the initial unused cache, not a physical measurement.
`source` is `hwmon` or `legacy`; operation is `none`, `temp1_input`, `interval`
or `legacy`. Sequence and elapsed are unsigned 64-bit values, read count is
unsigned 32-bit, and complete/elapsed_valid are 0 or 1. Words are null when no
DATA read completed, otherwise fixed `0x` plus eight hexadecimal digits.
`errno=0` only denotes a successful access when `complete=1`; legacy still
returns its original table index to its caller. A negative errno does not
change the caller's output value. A backwards monotonic interval sets
elapsed_valid to 0 rather than claiming an elapsed measurement.

Before activation, periodic qdrv calls can legitimately leave the legacy cache
complete with `-ENODEV` and zero reads. Installation must not require an unused
legacy cache. No read of either diagnostic resets either cache. A later hwmon
access replaces the previous hwmon cache; therefore the physical runner should
capture diagnostics immediately after its selected read, including on failure,
without issuing an extra temperature read.

The instrumentation test extracts actual driver functions and compares their
sensor accesses/results with direct calls to the unchanged core using fake
MMIO. It covers timeout, successful polling, out-of-range data, first/last words,
output preservation, cache separation, default zero accesses and RAM-only
diagnostic formatting. The initial harness compile failure due to a missing
host typedef remains historical; the corrected run is
`/workspace/OpenMitraStar-build/f365/f365-diagnostic-tests-20260921T215128Z/result.json`,
`PASS_DIAGNOSTIC_NO_ADDITIONAL_SENSOR_IO`, with 2,082 assertions.
The full F339 conversion oracle is reused, not rerun.

No sensor validity, continuous conversion, calibration, fresh conversion per
read, RF acceptance, or CPU/bus-lock recovery claim follows from this change.
Kernel, qdrv and other modules are not rebuilt for F365. Only the replacement
sensor module and diagnostic userspace/catalog metadata belong to the new
image; all physical operations remain with the root operator.

## Qualified module

Result:
`/workspace/OpenMitraStar-build/f365/f365-diagnostic-module-20260921T215213Z/result.json`,
SHA-256 `afdb2cb55235344a7ba2780a3f66584e5ed0196f44914df4271b71d230ee2909`,
status `PASS_OFFLINE_CACHED_DATA_DIAGNOSTIC_MODULE`.

The module is `a/temp_sens.ko` in that directory, 11,528 bytes, SHA-256
`e3ab1338753f3af4713a1f4cebf4b5b9ed4998922e8bf1cdb7424491f54d5fd1`.
Two ARC builds are byte-identical. All 17 imports resolve against the pinned
kernel export table; the single legacy export, GPL license, hwmon dependency,
vermagic and version363 remain compatible. Kernel/qdrv were not recompiled.
The copied kernel build context was isolated from the canonical F363 context.

The image composer receives this immutable module result and the exact F364r3
result `analysis/f364r3-fullimage-20260921T212001Z/result.json`. A module PASS
does not itself establish a completed full image or physical diagnostic result.
