# F337: OEM rootfs selection and a direct read-only boot

Prepared 21 September 2026, offline only. No SSH, UART, reset, TFTP, flash,
protected-partition access or hardware configuration was performed by this
analysis. The current F321 recovery result remains the operational baseline.

## Result and evidence

`outputs/preflight/f337-oem-readonly-20260921T123912Z/result.json` passes all
23 local checks. It establishes an intact OEM kernel/rootfs and a concrete
way to select its rootfs without replacing `mtd3`. This is **offline PASS**;
an OEM shell boot, strict read-only runtime and return to F321 remain untested.
There is no hardware executor in F337.

Reproduce the analysis with the offline-only
`tools/audit_f337_oem_readonly_boot.py --output <new-result.json>`.
It refuses to overwrite an existing result. It does not enumerate devices or
start network processes. The adjacent disassemblies are from the exact OEM
kernel, not a newly compiled approximation.

## What the failed boot actually proves

The preserved log `outputs/uart-live/boot-safety-after-recovery-20260817.log`
records a valid image checksum, transfer to OEM Linux 2.6.35.12, the six
physical partitions, and then:

```
VFS: Cannot open root device "(null)" or unknown-block(3,2)
Please append a correct "root=" boot option
```

Its command line contains no `root=`. No logical rootfs partition is created.
`setup_arch` in the exact OEM kernel sets the fallback `ROOT_DEV` to HDA2,
which explains device 3:2. The old audit's proposed requirement for a new DTB
was not supported by this evidence: this kernel receives ATAGs and the failure
is root-device selection, not an observed corrupt SquashFS or a missing DTB.

The original and preserved current safety dumps differ at just byte `0x6b`:

| Input | SHA-256 | BE32 header field at `0x68` |
|---|---|---|
| Original July safety dump | `81bbb0098f66c453c3282185ac337761a89d174950b341c6c5a6572ba4034719` | 5 |
| Preserved safety, verified by current backup chain | `f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1` | 1 |

The official b24 webformat SHA-256 is
`f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f`.
The original safety dump equals that file plus erased `FF` padding. All bytes
from payload offset `0x2000` onwards are identical in both safety dumps.
Both the uImage header CRC and vendor payload CRC pass. No correction to the
header or to flash is proposed.

LZMA decoding the preserved safety payload produces 3,750,104 bytes with SHA-256
`139ee3f292553ea2c3e6bd96fdeb3943246849b9cb1deda2f3f0824c59f11686`.
Those bytes equal the complete `.kernel` section of
`work/mission-state/w3-offline/oem-b24-vmlinux.elf` at `0x8493a000`.

## The vendor selector that the GPL source omits

The exact OEM `add_mtd_partitions` at `0x84a85060` adds more behavior than the
published generic GPL file:

1. Partitions named `linux_safety` and `linux_live` have their 220-byte image
   header read. The BE32 word at offset `0x68` is retained for selection.
2. `find_rootfs_header` (`0x84a842fc`) searches each slot at erase-block
   boundaries for SquashFS magic. It does not use Bootbase's selected slot.
3. `0x84a8531c..0x84a85382` selects the higher signed header value; ties select
   live. The all-ones field is the sentinel for unavailable. A selected live
   image without a discovered rootfs does **not** fall back to an intact
   safety rootfs.
4. Only if the chosen rootfs has positive size does
   `0x84a85392..0x84a853ba` allocate the logical `rootfs_live` view and set
   `ROOT_DEV` to that new MTD index.

The F159 physical backup used here has safety priority 1 with SquashFS at
`0x130000`, and live priority 5 without SquashFS on any erase-block boundary.
It exercises precisely the no-rootfs condition above. This explains why an
OEM kernel booted from safety can fail after installing a differently laid
out Linux 5.10 image in live. The exact live bytes present at the August 17
panic were not established; this report does not invent that historical
snapshot. The parser behavior and the F159 reproduction condition are proven
separately from the recorded panic.

The `rootfs_live` name is misleading: in the original dump it equals
`mtd3[0x130000:]`. It is a logical view, not a seventh physical flash region.
No concatenation including logical mtd6 is a valid raw 16 MiB SPI image.

## Direct mapping without changing OEM bytes

The physical safety slot is `0x040000..0x7e0000`. Its SquashFS begins at
`0x040000 + 0x130000 = 0x170000`; the remaining view is `0x670000` bytes.
The OEM kernel has command-line MTD partition parsing and SquashFS/LZMA built
in. Give it a single explicitly read-only view named `oemroot`:

```
console=ttyS0,115200n8 earlyprintk=1 hw_config_id=65535 root=31:0 rootfstype=squashfs ro init=/bin/sh ip=off mtdparts=spi_flash:0x670000@0x170000(oemroot)ro
```

This is 157 bytes including NUL, below the OEM ARC 256-byte command-line limit.
The name matches neither `linux_safety`, `linux_live` nor `uboot`, so it avoids
the vendor slot selector and its implicit rootfs allocation. The sole exposed
MTD is the rootfs window. `prepare_namespace` applies explicit `root=31:0`
after initialization. **During this proposed boot, Linux mtd0 means this
temporary rootfs view; it does not mean the physical baseline mtd0/uboot.**
Do not reuse an index-based flash/hash script within this altered view.

The review-only Bootbase sequence is:

```
spi_flash read 0x00040000 0x83000000 0x007a0000
iminfo 0x83000000
setenv bootargs console=ttyS0,115200n8 earlyprintk=1 hw_config_id=65535 root=31:0 rootfstype=squashfs ro init=/bin/sh ip=off mtdparts=spi_flash:0x670000@0x170000(oemroot)ro
bootm 0x83000000
```

Commands must be sent individually with observed successful completion and
readback before advancing. Replace the volatile bootargs completely; appending
to unknown existing bootargs can preserve conflicting `rw`, `root=` or
`mtdparts=` values. No `saveenv`, header edit, erase, write or image repacking
is required. This proposed list is not a consumed hardware approval or an
already executed test.

Do not substitute `ATGO`, `bootselect` or `qtnboot`. The decoded Bootbase's
`bootselect` calls `saveenv` if `bootm` returns, and `qtnboot` can copy safety
over live. A kernel panic after control transfer is not detected by either
normal fallback policy.

## Read-only audit, including limitations

The MTD command-line parser maps `ro` to `mask_flags |= MTD_WRITEABLE`.
`allocate_partition` removes those flags from the slave. The exact OEM
`part_write` (`0x84a83d80`) and `part_erase` reject a non-writable slave before
calling the physical operation. The root filesystem itself is SquashFS.
Other flash regions are not exposed as partitions by this proposed table.

The ARC `setup_arch` does clear `MS_RDONLY`, but **before** `start_kernel`
parses the final arguments. The later `ro` handler restores the read-only
mount flag. This ordering was checked in the actual binary; it is not a reason
to modify the OEM kernel. The MTD flag and actual `/proc/mounts` remain separate
required observations.

The Bootbase executable in the current protected dump decodes byte-identically
to `work/bootbase-decoded.bin`, SHA-256
`20ab45412b973478aa49a3daa31851a49f0deeaa09d07213479b0c3ee7af5f07`.
Its Linux handoff `0x8802cbc4..0x8802cd16` emits CORE, CMDLINE and HWID ATAGs,
then enters Linux. It does not contain the newer GPL `arclinux.c` protection
tag/unprotect sequence. That generic source must not be mistaken for this
Bootbase binary. The OEM SPI driver's protection-setting path is conditional
on the missing protection ATAG; the preserved boot log takes the no-protection
branch. SPI controller clock/mapping setup is volatile hardware initialization,
not a flash-array write.

`init=/bin/sh` bypasses the OEM BusyBox init table on successful execution.
That table otherwise remounts `/` writable, installs the MiniFO overlay,
runs `mount_data_partition` (JFFS2 on physical data), runs `mount -a`, configures
hotplug/networking, and starts `rcS`. `rcS` loads bootcfg, can reset MRD on
invalid identity, writes configuration and executes every S-script. None of
those scripts belongs in the first F337 boot. The OEM `/bin/sh` symlink resolves
to its original BusyBox; no login shell, profile or user startup script is
requested. `CONFIG_BLK_DEV_INITRD`, automatic IP configuration and devtmpfs are
disabled, so there is no compiled early-userspace initramfs to run first.

There is an inherited limit: OEM `init_post` tries normal `/sbin/init` if the
requested shell cannot execute. Consequently shell arguments alone are not a
formal guarantee that services cannot start under every failure. The future
physical preflight must isolate upstream connectivity and reject any normal
init/service marker. No radio stack or daemon is loaded before PID1, mount
and MTD checks pass. The first F337 boot is shell/recovery validation only;
loading OEM radar would be a separately reviewed subsequent step.

## Future physical acceptance and exact return

Use a new campaign with current pinned F321 identity, protected hashes, exact
Bootbase executable, a fresh device/UART lease and continuous bounded UART.
The stable F321 write/readback evidence and existing owner authorization can
be reused only through their normal current-state gates. No old F303 or consumed
F334/recovery nonce is reused.

Before running anything beyond the OEM shell, verify PID1 is the requested
shell, exact command line, only `oemroot` at the intended extent with write bit
clear, root SquashFS read-only, and no JFFS2/MiniFO, OEM init daemons or network
service. Mount only proc/sysfs and, if needed, tmpfs; do not run `mount -a`,
`rcS`, init, bootcfg, hotplug or data-partition helpers. Never test the write
barrier by attempting a flash write.

The return must restore the saved volatile F321 boot arguments before directly
reading/validating/booting live if a reset does not already restore them. The
runner must prove F321 identity and compare protected partitions after return
under the normal mapping. A shell prompt is not recovery PASS. Automatic
recovery from a frozen OEM kernel is not established; root is independently
qualifying the physical watchdog path before another acquisition campaign.

No replacement of safety firmware is needed by this mapping solution. A generic
`bootm kernel initrd` fallback is **not supported** by the OEM config: initrd and
MTD RAM are disabled, and the compiled block RAM disk is only 2 MiB. If a fully
RAM-backed root becomes necessary, qualify a separate RAM-only loader/kernel
adapter with bounded RAM placement and the exact original SquashFS bytes; do
not repair or repack mtd3 or silently claim the original kernel accepts an
external initrd. That alternative has not been constructed by F337.
