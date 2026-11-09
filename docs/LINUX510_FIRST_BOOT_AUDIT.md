# OpenMitraStar Linux 5.10 first-boot audit

Date: 2026-08-14  
Scope: offline-only audit of the Linux 5.10.260 RAM image, QEMU integration
gate, Quantenna modules and Realtek rtl8192ee payload.  
Hardware access: not performed.  
Overall verdict: **NO-GO for the first physical RAM boot**.

## Findings

### [P0] The required QEMU stability gate is not 3/3

The current integration image can boot and accept SSH, but the normal
three-boot gate did not complete:

- boot 1 passed;
- boot 2 passed only after the first SSH attempt spent 90 seconds and the
  second attempt succeeded;
- boot 3 printed `RAMSSH_SSH_READY` and `RAMSSH_UART_SHELL_READY`, but Dropbear
  never printed `Not backgrounding` within the 180-second readiness window;
- the runner exited 1 and did not create `RESULT.txt`.

This is a real release-gate failure. It does not prove that the kernel is
broken, because a separate one-boot execution passed, but it proves that the
current boot/SSH path is not deterministic enough for a first hardware test.

Evidence:

- `outputs/emulation/radio-integration-qemu/boot-1.ssh.log`
- `outputs/emulation/radio-integration-qemu/boot-2.ssh.log`
- `outputs/emulation/radio-integration-qemu/boot-3.serial.log`
- absent `outputs/emulation/radio-integration-qemu/RESULT.txt`

Observed result:

```text
BOOT_1_PASS
BOOT_2_PASS
<boot 3 readiness timeout>
exit=1
```

### [P0] QEMU does not exercise the hardware path needed by RAMSSH

The QEMU guest uses:

- `qemu_arc700_validation` DT instead of `topaz_mitrastar_ramssh`;
- link/RAM base `0x80000000` instead of `0x8493a000`;
- VirtIO networking instead of the Topaz Arasan EMAC;
- 256 MiB instead of the board's conservative high-DDR window;
- `CONFIG_HARDENED_USERCOPY=n`, while the hardware images retain it.

The physical RAM image depends on a new direct-DMA EMAC driver, EMAC1 at
`0xe8000000`, core IRQ 20, fixed 1000/full and PHY/switch state inherited from
Bootbase. No emulator in this workspace models those registers, descriptor
semantics, interrupt routing or inherited PHY state.

Therefore QEMU proves the ARC userspace, initramfs, SSH packaging and payload
ABI. It does **not** prove the physical Ethernet path that is needed to regain
SSH after `bootm`.

### [P1] `RAMSSH_SSH_READY` is emitted before SSH is actually ready

`ramssh_init.c` forks Dropbear and immediately prints `RAMSSH_SSH_READY`; it
does not wait for the child to `execve()` successfully or bind TCP port 22.
The parent then replaces PID 1 with the UART shell.

This ordering produced a false-positive marker in QEMU boot 3: the serial log
claimed SSH was ready although Dropbear never reached its own startup marker.
The external runner correctly waits for both strings, but a human following
only the documented `RAMSSH_SSH_READY` marker could attempt SSH too early.

Required correction before GO: make readiness observable. The init process
must wait for a child-to-parent success signal or probe local TCP/22 before
printing `RAMSSH_SSH_READY`. A failed `execve()` must print an explicit fatal
marker and leave the UART shell available.

### [P1] Quantenna compiles, but runtime safety is not established

The Quantenna result is strong as a compile/ABI artifact:

- exactly 22 expected `.ko` files;
- expected and actual module lists are identical;
- all modules are ELF32 little-endian ARCompact/ARC700;
- exact vermagic is
  `5.10.260-openmitrastar-radio mod_unload ARC700`;
- `depmod -e -F System.map` produced zero unresolved-symbol bytes;
- OEM radio firmware is hash-pinned and calibration/MAC data is not packaged.

However, `build.log` contains 537 compiler warnings. Several are material
portability warnings around MMIO calls, including integer-to-pointer arguments
to `__raw_readl`, distinct pointer comparisons and format mismatches. There
are zero compiler errors and zero undefined references, but successful
linking does not prove safe register access on Linux 5.10.

This does not block the minimal RAMSSH image because that image does not load
the radio modules. It does block a later **radio GO** until module insertion
and initialization are observed over UART without panic, invalid MMIO or
calibration writes.

### [P1] The first RAM image is deliberately not the radio image

`linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage` contains the direct EMAC,
minimal userspace, UART shell and Dropbear. It does not contain or autoload the
22 Quantenna modules or the Realtek rtl8192ee stack.

This separation is correct for blast-radius control, but a successful first
RAM boot would prove only the base kernel, UART, EMAC and SSH. It would not yet
prove either radio.

### [P2] The RAM placement is internally consistent

No address collision was found in the proposed Bootbase/TFTP path:

```text
uImage total size:       0x003ddb80 (4,053,888 bytes)
uImage payload size:     0x003ddb40 (4,053,824 bytes)
TFTP staging:            0x87000000..0x873ddb80 (exclusive end)
ELF load address:        0x8493a000
ELF entry point:         0x84ab0000
ELF PT_LOAD filesz:      0x003ddb40
ELF PT_LOAD memsz:       0x00411008
aligned kernel _end:     0x84d4c000
declared RAM end:        0x88000000
```

The staging region does not overlap the destination, and the complete ELF
memory footprint remains below `0x88000000`.

This proves only placement. It does not prove Bootbase cache maintenance,
board clocks, interrupt routing or EMAC operation.

## Positive evidence

### Artifact integrity

All current manifests verified with `sha256sum -c`.

Key hashes:

```text
8893785f5a8644c21b494c71f385ee59c6ee8e19b53996036f7d8bc2d54b7391  RAMSSH uImage
a0c250c551afa6f850e58a0ff883d828ed513a45feb96ff6482e61ff8adfc81b  QEMU vmlinux
c03402f1760539d3aa8bbdda363c2d9b5b10ec76e930b61ff9404bf4f3baaf89  Quantenna overlay
cd5797511b2731afb40cebece01497e34a3449c836876764a9ab91318f813cff  Realtek overlay
```

The RAMSSH `dumpimage -l` result is:

```text
Image Type:   ARC Linux Kernel Image (uncompressed)
Data Size:    4053824 Bytes
Load Address: 8493a000
Entry Point:  84ab0000
```

### Flash exclusion

The physical RAMSSH config, hardware radio config and QEMU integration config
all contain:

```text
# CONFIG_MTD is not set
# CONFIG_BLOCK is not set
```

The two hardware configs contain:

```text
CONFIG_HARDENED_USERCOPY=y
```

The QEMU-only config explicitly disables hardened usercopy because of the
legacy ARC emulator path. This is an emulation exception, not a hardware
configuration change.

The RAMSSH initramfs contains no MTD tooling and exposes only one root account
with a dedicated authorized key. The produced artifact is a legacy uImage,
not a webformat image and not a partition image.

### Quantenna module set

```text
module files:             22
module manifest lines:    23 (header + 22 modules)
expected/actual diff:     0
depmod unresolved bytes:  0
qdrv vermagic:            5.10.260-openmitrastar-radio mod_unload ARC700
```

The firmware inputs are pinned as follows:

```text
e1fd397ef56b061af7c91cbd422973dcfcf1382933afa226f8f428dd315f65af  auc_driver.default.0.bin
c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6  auc_driver.nomu.0.bin
71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4  qtn_driver.qtn_ruby.0.bin
87c882910d87cd29ba2004c4154e9240291aaad6aedb0ff4d90c7a5570be79fd  rdsp_driver.0.bin
2263cc2407d6e0d1543aa55bd7d2b9b98598301c59b4d3dca40701132f044365  qtn_regulatory_db.bin
```

### Realtek target

The Linux 5.10 rtl8192ee module reports:

```text
firmware: rtlwifi/rtl8192eefw.bin
alias:    pci:v000010ECd0000818Bsv*sd*bc*sc*i*
vermagic: 5.10.260-openmitrastar-radio mod_unload ARC700
```

This proves that the build targets PCI `10ec:818b` and has the named firmware.
It does not prove that the board exposes that ID correctly or that RF
calibration/regulatory operation succeeds.

### QEMU result

A fresh one-boot default run passed completely:

```text
BOOT_1_PASS
RADIO_INTEGRATION_QEMU_STABLE_PASS boots=1 ssh=1 hardware_autoload=off
```

The subsequent required three-boot run produced two passes and one readiness
timeout. Consequently the current status remains NO-GO.

## Reproduction commands

Run from PowerShell in `/workspace/user-home\Desktop\MitraStar`.

### Verify manifests

```powershell
wsl.exe -d podman-mem9-tidb -- bash --noprofile --norc -lc `
  'cd /workspace/user-home/Desktop/MitraStar/outputs/kernel-port/radio-integration-qemu && sha256sum -c SHA256SUMS'

wsl.exe -d podman-mem9-tidb -- bash --noprofile --norc -lc `
  'cd /workspace/user-home/Desktop/MitraStar/outputs/kernel-port/quantenna-linux510 && sha256sum -c SHA256SUMS'

wsl.exe -d podman-mem9-tidb -- bash --noprofile --norc -lc `
  'cd /workspace/user-home/Desktop/MitraStar/outputs/kernel-port/realtek-rtl8192ee-linux510 && sha256sum -c SHA256SUMS'

wsl.exe -d podman-mem9-tidb -- bash --noprofile --norc -lc `
  'cd /workspace/user-home/Desktop/MitraStar/outputs/kernel-port && sha256sum -c linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.sha256'
```

### Verify uImage metadata

```powershell
wsl.exe -d podman-mem9-tidb -- bash --noprofile --norc -lc `
  'dumpimage -l /workspace/user-home/Desktop/MitraStar/outputs/kernel-port/linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage'
```

### Run the QEMU stability gate

```powershell
wsl.exe -d podman-mem9-tidb -- bash --noprofile --norc -lc `
  'cd /workspace/user-home/Desktop/MitraStar && bash work/ssh-emulation/run-radio-integration-gate.sh'
```

Success must create:

```text
outputs/emulation/radio-integration-qemu/RESULT.txt
```

with exactly:

```text
RADIO_INTEGRATION_QEMU_STABLE_PASS boots=3 ssh=3 hardware_autoload=off
```

## Exact GO/NO-GO criteria

### Gate A: immutable artifact integrity

GO only if all four current `sha256sum -c` invocations pass, `dumpimage -l`
accepts the uImage, and the hash served by TFTP is exactly the audited RAMSSH
uImage hash.

Current result: **GO**.

### Gate B: flash exclusion

GO only if the physical RAMSSH config retains both `CONFIG_MTD=n` and
`CONFIG_BLOCK=n`, the initramfs contains no flash writer, and no webformat or
partition image is used.

Current result: **GO**.

### Gate C: deterministic QEMU boot and SSH

GO only if one unmodified invocation of the default runner completes at least
3/3 boots, with zero SSH retries, three guest PASS markers, empty
`guest-errors.log` files, no panic/Oops/BUG, and a final `RESULT.txt`.

The `RAMSSH_SSH_READY` marker must be moved after a proven Dropbear bind or
equivalent child handshake. A marker emitted immediately after `fork()` is not
accepted as readiness evidence.

Current result: **NO-GO**.

### Gate D: physical recovery prerequisites

Before any `bootm`, GO requires:

- a live UART capture at 115200 8N1;
- a verified `topaz>` prompt and documented power-cycle recovery;
- no `saveenv`, flash command, update script or partition write;
- TFTP staging at `0x87000000` and successful `iminfo`;
- a second machine or terminal continuously recording UART;
- the ability to power-cycle immediately if the kernel hangs.

Current result: **not assessed in this offline audit**.

### Gate E: first physical RAM boot

The first physical boot is successful only if UART proves all of the following:

1. Linux reaches `/init` without panic or watchdog reset.
2. The Topaz EMAC probe succeeds and does not report DMA quiesce refusal.
3. IRQ 20 increments under traffic.
4. At least one RX and one TX packet complete.
5. Ping and key-only SSH work at the expected RAM address.
6. `uname -r` reports the audited 5.10 release.
7. `/dev/mtd0` and `/sys/class/mtd` are absent.
8. A power cycle returns the untouched OEM firmware.

Current result: **not executed; NO-GO until Gates C and D pass**.

### Gate F: radio enablement after base RAM boot

Radio validation is a separate phase. GO requires:

- UART remains available during every module insertion;
- the exact 22-module dependency order loads without unresolved symbols,
  Oops, MMIO fault or watchdog reset;
- Realtek enumerates as `10ec:818b`, requests
  `rtlwifi/rtl8192eefw.bin`, creates a PHY and performs RX/TX;
- Quantenna firmware loads from the pinned blobs without modifying mtd5;
- calibration and MAC data are consumed read-only from an explicitly audited
  source;
- regulatory domain and power limits remain OEM-safe;
- the material Quantenna compiler warnings are fixed or individually justified
  before treating qdrv as production-safe.

Current result: **compile/ABI GO, runtime NO-GO**.

## Final decision

| Component | Offline build | QEMU | Hardware | Decision |
|---|---:|---:|---:|---|
| Linux 5.10 ARC base | PASS | boots | not tested | conditional |
| RAMSSH initramfs | PASS | 1/1 PASS, 3/3 FAIL | not tested | NO-GO |
| Flash exclusion | PASS | PASS | not tested | GO invariant |
| Topaz direct EMAC | PASS | not emulated | no RX/TX proof | NO-GO |
| Quantenna 22 modules | PASS | payload/ABI only | not loaded | NO-GO runtime |
| Realtek 10ec:818b | PASS | payload/ABI only | not loaded | NO-GO runtime |

The build is close, but the correct next milestone is not `bootm`. It is a
deterministic 3/3 QEMU result with truthful SSH readiness. After that, the
first physical attempt can be a strictly volatile UART-observed RAM boot.
