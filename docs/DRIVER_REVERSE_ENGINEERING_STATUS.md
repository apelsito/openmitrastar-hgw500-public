# Driver Reverse Engineering Status

Date: 2026-07-27

This is the current truth table for OpenMitraStar driver reversing. "Reversed"
does not mean "we have strings". It means we understand the boot contract,
entry points, data structures, firmware loading path, runtime control surface,
and what must be preserved or rewritten for Linux 5.10.

## Executive Status

| Component | Current status | Practical meaning |
| --- | --- | --- |
| Bootbase / BootExtension | Partially reversed | Command table, state machine and network paths are mapped enough for recovery planning, not enough for arbitrary patching. |
| Flash layout / boot env | Operationally understood | Physical 16 MiB layout and env variants are documented; recovery pack exists. |
| qdrv / Quantenna 5 GHz | ABI and firmware-loader contracts started | We have source-level GPL material and offline ABI checks, but not a Linux 5.10 port or clean replacement. |
| QCSAPI userspace | Usage mapped, not protocol-complete | Rootfs calls are visible; RPC protocol and full command catalog still need systematic extraction. |
| Quantenna on-chip firmware | Structural inspector exists | MuC/DSP/AuC images can be validated offline; instruction-level firmware behavior is not fully reversed. |
| Realtek 2.4 GHz | Identified, not reversed | Runtime module role is known; Linux 5.10 compatibility path is not proven. |
| Direct Ethernet / Arasan EMAC | 5.10 RAM-rescue driver compiles and links | EMAC1/IRQ20 direct DMA, NAPI, RX/TX and skb shadow rings are integrated; exact initramfs passes SSH in QEMU, while first hardware packet remains unproven. |
| HBM/TQE/switch acceleration | Architecture mapped, not safe to enable | Requestors and pool model are known; ownership/coherency is not proven. |
| SPI flash driver | Hazard identified | OEM cache contract is known; 5.10 write path must stay disabled until proven. |
| Topaz irqchip | First 5.10 implementation exists | This is the most advanced 5.10 platform piece, but hardware validation waits for UART. |

## qdrv / Quantenna 5 GHz

What we have:

- GPL source tree indexed under `work/sources/Quantenna-GPL`.
- `drivers/qdrv/*` source visible in the GPL tree.
- Offline ABI contract:
  - `QDRV_ABI_CONTRACT.md`
  - `tools/qdrv_abi_contract/qdrv_abi_contract.c`
  - `tools/qdrv_abi_contract/qdrv_abi_expected.h`
  - `tools/test_qdrv_abi_contract.py`
- Firmware image validator:
  - `QDRV_FW_INSPECT.md`
  - `tools/qdrv_fw_inspect.py`
  - `tools/test_qdrv_fw_inspect.py`
- Runtime load path documented in `RADIO_STACK_2026_RESEARCH.md`.

What is actually understood:

- `qdrv` is not just a netdev driver. It is the host-side control plane for
  Quantenna firmware, shared memory, MuC/DSP/AuC image loading, bridge/VAP
  behavior, stats, and hardware control.
- Firmware loading uses command writes through `/sys/devices/qdrv/control`.
- The production load chain is:
  `qtn_debug -> qtsens -> pm_interval -> wlan -> fwt_if -> fwt_ctrl -> auc_fw -> qdrv -> wlan_xauth -> wlan_ccmp -> wlan_tkip`.
- Known firmware blobs include:
  - `qtn_driver.qtn_ruby.0.bin`
  - `auc_driver.nomu.0.bin`
  - `auc_driver.default.0.bin`
  - `rdsp_driver.0.bin`

What is not done:

- No Linux 5.10 `qdrv` port.
- No clean-room `qdrv` replacement.
- No proven compatibility shim for the OEM module.
- No full shared-memory state machine documentation.
- No live trace from a recovered unit after the current brick.

Decision:

- Production firmware should keep OEM `qdrv` and wrap it.
- Linux 5.10 should not claim radio support until UART, IRQ, PCIe/shared memory,
  firmware loading, calibration, and control API are all proven.

## QCSAPI Userspace

What we have:

- Rootfs contains `call_qcsapi`, `qcsapi_rpcd`/`qserver` style services and many
  scripts invoking QCSAPI.
- Indexed search currently sees more than 100 `qcsapi`/`call_qcsapi` rootfs
  usages in the local OpenMitraStar/OEM-derived tree.
- `RADIO_STACK_2026_RESEARCH.md` captures live read-only radio state from the
  previous working firmware.

What is not done:

- Full command catalog extracted from binaries.
- RPC protocol documented packet-by-packet.
- Replacement `libopenqcsapi` implemented.
- Live `strace`/`ltrace` capture from the recovered device.

Decision:

- First build a wrapper API that shells out to known-good `call_qcsapi`.
- Replace the binary RPC layer only after command behavior is recorded and
  replayable.

## Bootbase / BootExtension

What we have:

- Bootbase and BootExtension disassembly artifacts:
  - `work/bootbase-decoded.disasm.txt`
  - `recovery/bootbase-analysis/bootextension-mtd0-bias-7fff4000.disasm.txt`
- Command table extracted:
  - `recovery/bootbase-analysis/bootextension-command-table.md`
  - `recovery/bootbase-analysis/bootextension-command-table.csv`
- Network and recovery notes:
  - `recovery/bootbase-analysis/bootbase-network-xrefs.md`
  - `recovery/bootbase-analysis/bootbase-recovery-state-machine.md`
  - `recovery/bootbase-analysis/qtn-netboot-readonly.md`

What is understood:

- `ATGU` returns to U-Boot command line mode.
- `ATTF`/`TFTP` share the same handler.
- `ATUR`, `ATUW`, `ATUB`, `ATLC` are write-oriented and should not be touched
  while bricked unless the path is fully proven.
- The Ethernet heartbeat window after the failed Linux handoff is Bootbase
  behavior, not evidence of a working OS.

What is not done:

- No bootloader patching.
- No arbitrary command injection path proven over Ethernet.
- No confirmed UART transcript from the currently bricked state.

Decision:

- Treat Bootbase as recovery surface, not as a playground.

## Direct Ethernet / Arasan EMAC

What we have:

- OEM source path: `work/sources/Quantenna-GPL/drivers/ruby/arasan_emac_ahb.c`.
- 5.10 contract header:
  `work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h`.
- Inert Linux 5.10 driver skeleton with coherent descriptor rings:
  `work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac-skeleton.c`.
- Architecture notes in `docs/OPENMITRASTAR_PLATFORM_DOSSIER.md`.
- Operational RAM-rescue implementation:
  `work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c`.
- Board-specific RAMSSH DT and build gate:
  `docs/RAMSSH_RESCUE_GATE_20260813.md`.

What is understood:

- EMAC0 base: `0xed000000`.
- EMAC1 base: `0xe8000000`.
- Descriptor is 16 bytes:
  `status`, `control`, `bufaddr1`, `bufaddr2`.
- The OEM driver relies on explicit cache maintenance and uses `bufaddr2` to
  retain skb ownership metadata.

What is not done:

- No TX/RX proof on hardware.
- No PHY polling or link renegotiation; the first rescue image preserves the
  fixed 1 Gbit/s RGMII state established by Bootbase.

Decision:

- EMAC direct path is the first Linux 5.10 networking target.
- HBM/TQE stays off until direct EMAC works.

Compile result:

- `CONFIG_QTN_TOPAZ_EMAC_SKELETON=y` in the engineering profile.
- The skeleton builds into
  `outputs/kernel-port/linux-5.10.260-topaz-engineering-NO-GO.vmlinux`.
- It prepares 256 TX descriptors and 1024 RX descriptors via the Linux DMA API,
  but does not write descriptor base registers, set RX OWN bits, request IRQs,
  enable MAC RX/TX, or start DMA.
- Final engineering hashes after adding the skeleton:
  - config: `e08210e62d809c5ab88c53250552cdd955cbb16fe5ef046e453dd352e740fd1e`
  - vmlinux: `f2de7c8aacfee1b76201ea87828178a13c7e4c01bc84f3fe3d66ceb7e744d5b8`
  - uImage: `77a5a7ffe6b064ccabe6b22b94c86058950f81d04d1fb0a2fc852a7c467d0670`
- The DT node exists but is `status = "disabled"` to avoid colliding with the
  read-only MDIO probe over the same EMAC0 MMIO aperture.

RAMSSH update (2026-08-13):

- A separate DT enables only EMAC1 at `0xe8000000`, direct ARC IRQ 20.
- The driver uses coherent descriptor rings and standard streaming DMA maps;
  CPU pointers never enter hardware descriptors.
- Bootbase RGMII/PHY state is inherited and no switch/PHY reset is issued.
- `CONFIG_MTD` and `CONFIG_BLOCK` are disabled in this profile.
- The exact initramfs passed a fresh key-only SSH session in QEMU.
- The artifact remains named `RAM-ONLY-NO-GO` until RX/TX is observed on the
  physical board through a UART-controlled, non-persistent boot.

## HBM / TQE / Switch

What we have:

- OEM source paths:
  - `work/sources/Quantenna-GPL/drivers/topaz/hbm.c`
  - `work/sources/Quantenna-GPL/include/qtn/topaz_hbm_cpuif.h`
  - `work/sources/Quantenna-GPL/drivers/topaz/switch_tqe.c`

What is understood:

- HBM is a shared packet-buffer pool system, not a normal private DMA ring.
- TQE uses CPU interface rings, interrupts, NAPI-like behavior and HBM buffers.
- Requestors include LHOST, MuC, EMAC0, EMAC1, WMAC, TQE, AuC, DSP and PCIe.

What is not done:

- No safe ownership model for Linux 5.10.
- No coherency proof.
- No pool guard validation on hardware.

Decision:

- HBM/TQE is late-stage acceleration, not recovery networking.

## SPI Flash

What we have:

- OEM SPI partition source:
  `work/sources/Quantenna-GPL/drivers/ruby/spi_flash.c`.
- Recovery pack and analyzer:
  - `recovery/scripts/build_spi_recovery_pack.py`
  - `recovery/scripts/analyze_spi_read.py`

What is understood:

- Physical partitions are `mtd0..mtd5`.
- `mtd6` is logical overlap and must be excluded from physical image assembly.
- OEM write path uses non-cached mappings because dirty ARC cache lines can
  corrupt flash writes.

What is not done:

- No Linux 5.10 write-safe SPI driver proof.
- No hardware validation from current brick.

Decision:

- Linux 5.10 SPI is read-only until cache/write semantics are proven.

## Realtek 2.4 GHz

What we have:

- Runtime identification in `RADIO_STACK_2026_RESEARCH.md`.
- Module stack observed around `rtl8192cd` and companion WLAN modules.

What is not done:

- No source-level compatibility audit.
- No Linux 5.10 port.
- No cfg80211/mac80211 migration plan.

Decision:

- Do not let Realtek block recovery.
- Treat it as phase after OEM owner-mode firmware is stable.

## Next Reverse Engineering Tasks

P0 after hardware recovery:

1. Capture UART boot log.
2. Boot known-good OEM slot.
3. Dump loaded modules, module parameters, `/proc/iomem`, `/proc/interrupts`,
   `/proc/mtd`, `/sys/devices/qdrv/control` behavior and QCSAPI process tree.
4. Run QCSAPI command inventory live.

P1 driver work:

1. Extract full `call_qcsapi` command table from binary/source.
2. Trace `call_qcsapi` to daemon with `strace`.
3. Build a QCSAPI wrapper matrix: command, arguments, output shape, failure
   mode, owner-API endpoint.
4. Convert Arasan EMAC descriptor contract into a minimal Linux 5.10 driver
   skeleton with TX/RX disabled until UART RAM shell is proven.

P2 research:

1. Map qdrv shared-memory structures from GPL source to the ABI contract.
2. Identify exact firmware blob load destinations and ownership.
3. Build HBM/TQE diagrams from source and live registers.
4. Compare OEM qdrv path with mainline qtnfmac expectations.
