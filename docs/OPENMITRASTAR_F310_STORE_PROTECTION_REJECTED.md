# OpenMitraStar F310 Store Protection Observer Rejected

Date: 2026-09-04

## Result

The packaged F295 store-protection observer is not safe to load on the physical
HGW-500BNA-QCv2 under Linux 5.10. Loading the module caused an ARC Machine Check
before any useful observer output was produced.

The module contains no write-enable, erase, program, protection mutation or MTD
registration path. No flash write occurred. Access happened without a proven
address-map/ownership/arbitration contract; that alone does not identify the
root cause. The 2026-09-07 F320 source review found a legacy/alias address
discrepancy and classified ECR `0x00200400` as kernel data memory error. See
`docs/OPENMITRASTAR_F320_SPI_CONTROL_READ.md`; the exact faulting access and
physical cause remain unproven.

The router was recovered through UART to the `topaz>` prompt and booted the
unchanged F310 image from `mtd4`. SSH, both radios and a zero-fatal fresh boot
were verified afterwards.

## Decision

- Do not load `qtn-topaz-store-protection-observer.ko` again.
- Keep the observer disabled and without autoload.
- Keep `lyoko_store` read-only and unmounted.
- Do not enable persistent package or configuration writes.
- A replacement must first prove SPI controller ownership and arbitration
  without touching the physical router, then ship as a new versioned `mtd4`
  diagnostic image.

Evidence:

- `outputs/certification/f310-store-protection-rejected-20260904/result.json`
- `outputs/preflight/f310-store-protection-probe-20260904T211740Z/uart/uart.log`
- `outputs/recovery/f310-store-machine-check-reboot2-20260904T213500Z/uart-to-topaz.log`
- `outputs/recovery/f310-store-machine-check-reboot2-20260904T213500Z/run-bootcmd.log`
