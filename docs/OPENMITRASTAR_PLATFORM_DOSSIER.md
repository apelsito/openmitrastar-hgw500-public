# OpenMitraStar Platform Dossier

This dossier is the working contract for the MitraStar HGW-500BNA-QCv2
project. It is not a generic router plan. It is the specific architecture model
we use before touching UART, SPI flash, Linux 5.10, Ethernet, or the radio
stack.

## Objective

Make the device recoverable, inspectable, and owner-controlled without losing
the factory calibration data or the ability to boot known-good OEM firmware.

The project has two tracks:

1. Recovery and production firmware: keep the OEM kernel/driver ABI where it is
   needed, expose clean owner controls, remove opaque web limitations, and keep
   rollback paths.
2. Modern kernel research: build a Linux 5.10 ARC700 platform port in small
   hardware-proven stages, starting with UART and RAM-only initramfs.

The production track wins whenever the device must stay recoverable. The modern
kernel track is allowed to be aggressive only when booted from RAM or written to
a known non-critical slot after SPI recovery is proven.

## Top-Level Mental Model

This device is not "a normal OpenWrt router with weird WiFi". It is a Quantenna
Topaz/ARC board with a proprietary radio/control stack and a very opinionated
memory map.

Key layers:

- Bootbase/U-Boot-compatible loader owns early recovery, slot selection, and
  network boot behavior.
- ARC700 Linux host runs the OEM firmware and board services.
- The 5 GHz Quantenna FullMAC radio uses proprietary host driver, userspace
  QCSAPI tools, and on-chip firmware blobs.
- The 2.4 GHz Realtek radio uses vendor driver integration.
- Ethernet can run through a direct EMAC path or through the Topaz accelerated
  HBM/TQE/switch path.
- Calibration, MACs, and factory data live outside the firmware slots and must
  be preserved verbatim.

Any firmware that ignores these layers is a brick candidate.

## Flash and Boot Contracts

Physical SPI flash is 16 MiB.

| MTD | Offset | Size | Name | Contract |
| --- | ---: | ---: | --- | --- |
| mtd0 | 0x000000 | 0x020000 | uboot | Compare-only unless proven corrupt |
| mtd1 | 0x020000 | 0x010000 | uboot_env | Writable only after env CRC/model checks |
| mtd2 | 0x030000 | 0x010000 | uboot_env_bak | Same as mtd1 |
| mtd3 | 0x040000 | 0x7a0000 | linux_safety | Firmware slot |
| mtd4 | 0x7e0000 | 0x7a0000 | linux_live | Firmware slot |
| mtd5 | 0xf80000 | 0x080000 | data | Factory/calibration data; preserve verbatim |

`mtd6` is a logical overlap view into the rootfs area of a Linux slot. It is
not a physical flash region and must not be used to assemble a full SPI image.

Boot selection:

- `bootselect=1` means `linux_safety`.
- `bootselect=0` means `linux_live`.
- Environment writes are allowed only when the env image has a valid CRC and we
  know exactly which slot is intended.

Recovery rule:

- Restore the damaged Linux slot first.
- Do not write `mtd0`.
- Do not write `mtd5`.
- Do not write full-chip images unless the write window and layout are proven
  byte-for-byte against two identical reads.

## CPU, RAM, and Kernel Port Contract

Observed platform target:

- CPU family: ARC700 class, family `0x33`.
- Endianness: little-endian.
- Clock: 500 MHz core, with UART divisor still to be confirmed live.
- MMU: ARC MMU v2, 8 KiB pages, 128 JTLB entries.
- UART: `0xf0000000`, `115200n8`.

Modern kernel target:

- Linux 5.10.260 is the practical research baseline.
- Linux 6.x is not the first target because upstream ARC MMU v2 support was
  removed and would require a separate resurrection project.

RAM contract for the current hardware stage:

- Linux-visible RAM starts at `0x8493a000`.
- Linux-visible RAM ends at `0x88000000`.
- Size is `0x036c6000`.

The lower DDR area is not free RAM. It is shared or reserved for board
subsystems such as PCIe BDA, DSP, MuC, AuC, HBM, FWT/TQE, and firmware-owned
regions. A modern kernel that claims all DDR is expected to corrupt something.

First modern-kernel boot target:

- Exact RAM DT.
- ARC timers.
- Topaz interrupt controller.
- DW APB UART.
- Static initramfs.
- No SPI writes.
- No MTD.
- No Ethernet.
- No radio.

The first victory condition is a RAM-only shell over UART, not a full distro.

## Interrupt Controller Contract

Topaz has a second-level interrupt controller behind ARC parent interrupt
vectors.

Known parent aggregation:

- Parent 24: GPIO group.
- Parent 25: UART/timer style group.
- Parent 26: misc group.
- Parent 27: additional platform group.

Known MMIO base:

- SYSCTL / interrupt controller: `0xe0000000`.

Known IRQ facts from the current 5.10 port:

- Child IRQ mask accepts hwirqs 0..21 and 24..31.
- hwirqs 22 and 23 are invalid/reserved.
- EMAC0 interrupt is 19.
- EMAC1 interrupt is 20.
- HBM interrupt is 21.
- TQE interrupt is 5.

The irqchip is a gating dependency. UART, Ethernet, and later platform drivers
must not each invent their own interrupt interpretation.

## SPI and Cache Contract

The OEM SPI flash driver documents an ARC cache hazard:

- Reads can use a cached mapping.
- Writes use a non-cached mapping.
- Dirty partial cache-line behavior can corrupt SPI flash writes if the mapping
  and flush strategy are wrong.

For Linux 5.10:

- Do not blindly port the old SPI write path.
- Use Linux MTD/SPI-NOR APIs where possible.
- If a raw MMIO SPI path is required, prove cache attributes and write
  granularity before enabling erase/write operations.

Until that is proven, Linux 5.10 images are read-only or RAM-only on hardware.

## Ethernet Contract

There are two Ethernet paths.

Direct EMAC path:

- OEM source name: `ruby/emac.ko` / Arasan EMAC AHB.
- MMIO bases: EMAC0 `0xed000000`, EMAC1 `0xe8000000`.
- Descriptor shape is four 32-bit words:
  - `status`
  - `control`
  - `bufaddr1`
  - `bufaddr2`
- Descriptor size: 16 bytes.
- OWN bit: bit 31.
- RX FIRST: bit 30.
- RX LAST: bit 29.
- EOR: bit 26.
- CHAINED: bit 25.
- Buffer size mask: bits 11:0.

OEM direct driver behavior that matters:

- Uses explicit cache maintenance before RX/TX.
- Stores skb pointers in `bufaddr2` because DMA ignores the second buffer
  length in this usage.
- Uses IRQ/NAPI.

Linux 5.10 direct EMAC target:

- Reimplement around the Linux DMA API.
- Keep descriptor format compatible.
- Prove one RX packet and one TX packet before adding switch integration.

Accelerated path:

- Switch base: `0xe1000000`.
- HBM base: `0xe1020000`.
- TQE base: `0xe1030000`.
- TQE LHOST CPU IF: `0xe1034000`.

HBM/TQE are not a normal netdev DMA ring. They are shared low-DDR packet pools
and a forwarding engine used by multiple requestors:

- LHOST
- MuC
- EMAC0
- EMAC1
- WMAC
- TQE
- AuC
- DSP
- PCIe

Accelerated Ethernet is a late-stage target. Enabling it before proving HBM
ownership, bus address conversion, cache coherency, and pool guards is how we
turn a boot bug into memory corruption.

## Radio Contract

The 5 GHz radio is the hard part.

Production track:

- Keep OEM `qdrv.ko` and the matching kernel ABI.
- Keep Quantenna firmware blobs extracted from the OEM filesystem.
- Keep `qcsapi_sockrpc`, `call_qcsapi`, and `libqcsapi` behavior observable
  until a replacement is proven command-by-command.
- Build owner-facing control on top of known-good QCSAPI behavior first.

Research track:

- Study mainline `qtnfmac` for QSR1000/Topaz compatibility.
- Preserve OEM blobs as local-only artifacts.
- Treat calibration as externally owned until proven otherwise.
- Do not mix qtnfmac migration with production recovery images.

The 2.4 GHz Realtek stack is a separate compatibility problem. It should not
block recovery or the first owner-mode firmware, but it must be handled before
claiming a full custom router firmware.

## Calibration and Factory Data Contract

`mtd5` is the device identity partition.

Expected contents:

- MAC addresses.
- Radio calibration.
- Regulatory/factory configuration.
- Device-specific vendor state.

Rules:

- Preserve `mtd5` byte-for-byte in every recovery pack.
- Back it up redundantly before any hardware write operation.
- Never synthesize calibration data.
- Regulatory experiments modify policy/configuration only, not power
  calibration tables.

## Recovery Pack Contract

The current recovery tooling should be treated as the authority for SPI-level
operations:

- Build a physical 16 MiB reference from verified physical partitions only.
- Exclude `mtd6`.
- Analyze new CH341A reads before writing.
- Detect which slot differs.
- Recommend partition-level restore, not blind full-chip flashing.

Artifacts:

- `recovery/spi-recovery/hgw500_physical_16m_reference.bin`
- `recovery/spi-recovery/hgw500_flashrom.layout`
- `recovery/spi-recovery/SHA256SUMS.txt`
- `recovery/scripts/analyze_spi_read.py`
- `recovery/scripts/build_spi_recovery_pack.py`
- `recovery/CURRENT_BRICK_RECOVERY_PLAN.md`

## Beast Roadmap

Stage 0: Recoverability

- UART capture.
- Two identical SPI reads.
- Analyzer result.
- Restore only the damaged Linux slot.
- Confirm bootselect and env CRC.
- Power-cycle after flash operations if reboot behavior is partial.

Stage 1: Owner-mode OEM-based firmware

- Keep OEM kernel and radio ABI.
- Clean web/API surface.
- Expose real radio state, passphrases, channels, power, MACs, service state,
  and logs.
- Keep rollback slot discipline.

Stage 2: Instrumentation

- Dump QCSAPI command catalog.
- Trace `call_qcsapi` to `qcsapi_sockrpc`.
- Map live radio process tree and module parameters.
- Preserve all findings as ABI/API contracts.

Stage 3: Linux 5.10 RAM-only shell

- Boot only from UART/TFTP/RAM.
- Exact DT RAM.
- UART console.
- irqchip.
- initramfs shell.

Stage 4: Linux 5.10 read-only platform bring-up

- Timers.
- GPIO.
- Read-only SPI identification.
- No erase/write path until cache contract is proven.

Stage 5: Direct Ethernet

- Port Arasan EMAC logic to Linux DMA API.
- Prove TX/RX.
- Add NAPI.
- Keep HBM/TQE disabled.

Stage 6: Storage writes

- Enable SPI-NOR writes only after mapping/cache proof.
- Use partition guards and layout checks.
- Never write `mtd0` or `mtd5` from an experimental image.

Stage 7: Accelerated networking

- HBM pool ownership.
- TQE CPU interface.
- Switch path.
- VLAN/FWT/DPI integration only after direct EMAC is stable.

Stage 8: Radio modernization

- QCSAPI clean-room wrapper.
- Optional qtnfmac research branch.
- LuCI/custom UI integration.
- Full calibration-preserving firmware release.

## Current Hard Decisions

1. We do not try to "just boot OpenWrt" again. The SoC memory ownership and
   ARC MMU constraints make that reckless.
2. We make the OEM-based owner firmware the first useful product.
3. We make Linux 5.10 a hardware research target with gates, not the immediate
   production recovery path.
4. We treat SPI writes as surgical partition operations.
5. We preserve the data partition as if it were irreplaceable, because it is.

