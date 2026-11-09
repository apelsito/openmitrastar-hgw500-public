# F355 final software lifetime handoff

Status: **PASS_OFFLINE_PINNED_LIFETIME_COHERENT_CLOSURE**.
No hardware access, target module load, radio reset, flash or Wi-Fi test occurred.
F353's missing hardware epoch remains unresolved; F344 remains immutable.

The authoritative final result is:

`/workspace/OpenMitraStar-build/f355/f355-qualified-20260921T170051Z/result.json`

SHA-256: `ecfed10d5377cdc8a770c331236e83c371fc7f9d359c5624d0b6f7e8d264fc39`.

The final qdrv is:

`/workspace/OpenMitraStar-build/f355/f355-qualified-20260921T170051Z/modules/qdrv.ko`

696,932 bytes; SHA-256:
`f91c4f28bda8093a57ae74320ae31393597c3f88d6539317fb37a54b214e5155`.

The directory contains all 26 coherent modules, load order, final source diff,
Module.symvers and a snapshot of the detailed lifetime contract. All 1,089
imports were audited for ownership, dependencies and GPL-only/taint constraints.
The 16 F344 parameters and beacon preflight implementation profile are preserved.
Only nine source files differ from F344; no wire header or reset implementation
was changed. The full closure build is reproducible; the final qdrv refinements
were built twice, reusing the other 25 identical, already-rebuilt modules.

The pin rule is deliberately stricter than "hardware has definitely started":
the first matched, policy-admitted command other than `get` or `stop` pins qdrv.
This includes `set` and the separately named `read` command. Read-only sysfs
observations and the `get` path do not themselves pin it. A handler argument
failure does not release a pin already acquired. No command provides an unpin.

The software tests pass 1,371 lifetime/refcount/init checks, including eight
initializer failures and 256 two-thread races; 26 actual procfs lifecycle
checks; 18 release-order contracts; and expected compilation rejection when
CONFIG_MODULE_FORCE_UNLOAD is defined. The refcount tests execute extracted
Linux 5.10 logic with explicitly fake kernel services, not target hardware.

Detailed contract: `docs/OPENMITRASTAR_F355_QDRV_LIFETIME.md`.
Previous findings: `docs/OPENMITRASTAR_F353_RADIO_EPOCH_AUDIT.md`.

Intermediate closure `f355-closure-20260921T164514Z` predates the final sysfs
waiter/put_device refinements. Use the qualified directory above, whose final
closure binding is `f355-final-closure-20260921T165428Z`. Earlier failing test
harnesses are preserved; they were corrected without weakening the assertions.
The inherited `F338-source-binding.json` is unchanged provenance metadata,
not compiled source or the authority for final F355 hashes.

Bulky outputs reside on D:. The C: >500 MiB guard passed throughout final
qualification. Production integration, hardware validation and Wi-Fi acceptance
remain separate; Wi-Fi/RF/client execution is USER_DEFERRED.
