# OpenMitraStar Linux 5.10 ARC700 QEMU Status - 2026-08-12

## Current Result

The ARC700 Linux 5.10.260 validation kernel now boots far enough in the
patched QEMU ARC700 model to exercise timer IRQs, page release paths, and ARC
compact entry/return code for repeated 600s validation windows without
`guest_errors`.

The 8250 console is now wired through QEMU `-serial stdio`. Linux reaches
`console [ttyS0] enabled` and then starts `/init` from the built-in validation
initramfs. A rebuilt validation kernel now includes `/dev/console` and
`/dev/null` in the initramfs, so the earlier `Warning: unable to open an
initial console` is gone.

This is a strong QEMU milestone, but it is still not a flashable firmware gate:
the image is a validation kernel and still depends on board-emulation bridges
that are not valid for the physical MitraStar flash layout.

Latest validated artifacts:

- QEMU binary: `/home/user/qemu-arc-legacy-build/qemu-system-arc`
- Kernel: `outputs/kernel-port/linux-5.10.260-qemu-arc700-base80000000-console-validation.vmlinux`
- Kernel SHA-256 after reproducible rebuild:
  `c5c576d17ad10a8f5e836df5c110839543508b736c19052d3d67628b4afef621`
- Command wrapper: `tools/run-openmitrastar-qemu-arc700-validation.ps1`
- Rebuild script: `tools/build-openmitrastar-qemu-arc700-console-kernel.sh`
- QEMU patch artifact: `outputs/patches/qemu-arc700-openmitrastar-20260812.patch`
- Linux 5.10.260 ARC patch artifact:
  `outputs/patches/linux-5.10.260-arc700-openmitrastar-validation-20260812.patch`
- Validation hashes: `outputs/hashes/openmitrastar-qemu-validation-20260812.sha256`

Latest validations:

- `outputs/emulation/qemu-wrapper-console-600.serial.log`: wrapper-driven 600s
  timeout after the reproducible rebuild, real serial bootlog visible, reaches
  `console [ttyS0] enabled` and `Run /init as init process`.
- `outputs/emulation/qemu-wrapper-console-600.log`: wrapper-driven 600s timeout,
  0-byte `guest_errors`.
- `outputs/emulation/qemu-irqlev-600a.log`: 600s timeout, 0-byte `guest_errors`.
- `outputs/emulation/qemu-irqlev-600b.log`: 600s timeout, 0-byte `guest_errors`.
- `outputs/emulation/qemu-irqlev-clean-240.log`: 240s timeout, but `guest_errors`
  contains invalid accesses around `0x5fa13f20..0x5fa13fe0`.
- `outputs/emulation/qemu-txfail-300.log`: 300s timeout with
  `OPENMITRASTAR_TXFAIL_PC=1`, 0-byte `guest_errors`.
- `outputs/emulation/qemu-clean-nodiag-600a.log`: 600s timeout, 0-byte
  `guest_errors`, with no transaction-failure instrumentation.
- `outputs/emulation/qemu-clean-nodiag-600b.log`: 600s timeout, 0-byte
  `guest_errors`, with no transaction-failure instrumentation.
- `outputs/emulation/qemu-clean-cmdlinefix-600a.log`: 600s timeout, 0-byte
  `guest_errors`, after fixing QEMU ARC cmdline propagation/copying.
- `outputs/emulation/qemu-clean-serial-120.serial.log`: 120s timeout, real
  serial bootlog visible on QEMU stdio.
- `outputs/emulation/qemu-clean-serial-600.serial.log`: 600s timeout, real
  serial bootlog visible, reaches `console [ttyS0] enabled` and `Run /init as
  init process`.
- `outputs/emulation/qemu-clean-serial-600.log`: 600s timeout, 0-byte
  `guest_errors`.
- `outputs/emulation/qemu-console-validation-120.serial.log`: 120s timeout,
  rebuilt initramfs with `/dev/console`, real serial bootlog visible, no
  `unable to open an initial console` warning.
- `outputs/emulation/qemu-console-validation-600.serial.log`: 600s timeout,
  rebuilt initramfs with `/dev/console`, real serial bootlog visible, reaches
  `console [ttyS0] enabled` and `Run /init as init process`.
- `outputs/emulation/qemu-console-validation-600.log`: 600s timeout, 0-byte
  `guest_errors`.

This is an emulation milestone, not a flashable firmware milestone.

## Reproducible rebuild path

Use this from the Windows workspace root:

```powershell
wsl -e sh -lc 'cd /workspace/user-home/Desktop/MitraStar && sh tools/build-openmitrastar-qemu-arc700-console-kernel.sh'
```

The script validates the expected ARC toolchain, extracts the known-good
validation `/init` from the backed-up no-console CPIO, regenerates a deterministic
initramfs list with `/dev/console` and `/dev/null`, rebuilds Linux 5.10.260 with
`ARCH=arc`, and copies the resulting `vmlinux` to the validated kernel artifact.

Run validation from the same root:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run-openmitrastar-qemu-arc700-validation.ps1 -TimeoutSeconds 600 -Tag wrapper-console-600
```

## Effective QEMU fixes in this milestone

- `hw/arc/arc_sim.c`
  - ARC RAM is mapped at `0x80000000`.
  - vmalloc validation RAM is mapped at `0x70000000`.
  - a separate low `openmitrastar.user-shadow` RAM window is mapped at
    `0x00000000..0x03ffffff` to keep early low user-memory accesses from
    corrupting high kernel RAM while full ARC MMU translation is still incomplete.
  - CPU `intv-base` is set to the high RAM base.
  - `machine->kernel_cmdline` is now propagated to `arc_boot_info`, matching
    `hw/arc/virt.c`, so QEMU `-append` is no longer silently ignored.
  - the QEMU 8250 UART is mapped at physical `0x90000000` and also aliased at
    Linux's observed ioremap/vmalloc address `0x70023000`, overriding
    `arc.vmalloc` for that MMIO window. This is what makes `-serial stdio`
    receive the kernel console.

- `hw/arc/boot.c`
  - ARC boot cmdline copying now includes the terminating NUL byte.

- `target/arc/irq.c`
  - ARC700 IRQ entry/return no longer uses the ARCv2 stack autosave model.
  - ARC700 interrupts use direct vector entries instead of ARCv2 pointer-table
    semantics.
  - ARC700 `AUX_IRQ_LEV` and `AUX_IRQ_LV12` are now wired into the IRQ model
    instead of `TO_IMPLEMENT`.
  - ARC700 interrupt entry now selects L1 vs L2 shadow registers instead of
    always saving into `ILINK1/status32_l1`.
  - low `INT_VECTOR_BASE` writes are guarded for this high-RAM validation board.

- `target/arc/helper.c`
  - ARC700 exceptions use direct 8-byte vector slots.
  - low vector base is repaired before exception dispatch.

- `target/arc/mmu.c` / `target/arc/mmu.h`
  - TLB probe command support was added.
  - unknown TLB commands are logged instead of aborting QEMU.

- `target/arc/semfunc_mapping.def`
  - non-short `extw` mapping is present.

## What was ruled out

- The earlier `__rb_insert_augmented` callback-null suspicion is not the primary
  blocker. Entry probes show `r2` carries valid callbacks such as `0x80066390`.
- ARC700 vma stack-frame load/store writeback was validated across the failing
  windows. Saved `blink` values were restored correctly.
- The serial callback path did not show `OMT-JMP-BAD` in the latest passing
  window.
- `ld.ab r14,[r13,-4]` at `free_unref_page_list+0x14` decodes correctly as
  `aa=2`, `src1=r13`, `src2=-4`, `dest=r14`; the invalid `0xfffffffc`
  pattern is a corrupted list pointer symptom, not a decoder misread of that
  instruction.

## Remaining technical debt

- The earlier clean run `qemu-irqlev-clean-240.log` showed invalid reads around
  `0x5fa13fxx`, but that class did not reproduce in two later 600s clean runs
  after removing the temporary transaction-failure instrumentation. Treat it as
  a stale but documented warning until longer clean runs prove otherwise.
- The low `user-shadow` RAM is a validation bridge, not a correct ARC MMU model.
  The real target is to replace this with proper ARC700 TLB/user-space
  translation.
- Serial output is useful now, but it depends on a hardcoded validation alias:
  `struct uart_port.membase` was observed at `0x70023000` while `mapbase` is
  `0x90000000`. This is acceptable for the current QEMU validation twin, not a
  complete ARC MMU implementation.
- The initramfs source now includes `/dev/console` and `/dev/null`. The original
  no-console CPIO was backed up at
  `/home/user/openmitrastar-build/qemu-arc700-base0-nozol-validation-initramfs.no-console-20260812.cpio`.
- The kernel command line currently contains duplicated early console arguments
  from the validation DTS plus QEMU `-append`. This is noisy but non-blocking:
  the 8250 driver still binds `ttyS0`, QEMU serial output is visible, and the
  wrapper validation reaches `/init` without panic or `guest_errors`.
- A same-size manual ELF/CPIO patch experiment adding `/dev/console` exited
  immediately and has been quarantined under
  `outputs/kernel-port/experiments-no-go/`. Use the rebuilt
  `console-validation.vmlinux` instead.
- The ARC cross compiler is available at
  `work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-gcc`.
  Kbuild was regenerated with `ARCH=arc` and the matching `CROSS_COMPILE`
  prefix after the accidental x86 Kconfig attempt.
- No physical router flashing is allowed from this state.

## Safe operating rule

Do not flash this kernel or any image derived from this milestone to the router.
This milestone is for QEMU-only validation.
