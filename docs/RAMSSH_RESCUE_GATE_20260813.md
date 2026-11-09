# OpenMitraStar Linux 5.10 RAMSSH rescue gate

Date: 2026-08-13

## Result

A board-specific Linux 5.10.260 uImage now exists for one narrow purpose:
boot from Bootbase/U-Boot RAM, bring up EMAC1, and expose a key-only SSH shell.

It is not a flash image. The profile cannot generate webformat artifacts and
the kernel configuration contains neither `CONFIG_MTD` nor `CONFIG_BLOCK`.

## Proven offline

- ARC700, little-endian, MMU v2, 8 KiB pages.
- Link/load address `0x8493a000`; entry point `0x84ab0000`.
- Exact high-DDR window `0x8493a000..0x88000000`.
- QHS860 board data decoded from the verified U-Boot environment:
  - EMAC0 and EMAC1 enabled;
  - PHY addresses 1 and 3;
  - RGMII timing `0x81828282`.
- Live OEM evidence identifies the working wired interface as EMAC1 / IRQ 20.
- The minimal direct-EMAC driver builds into the kernel with Linux DMA API,
  software-owned skb shadow rings, IRQ/NAPI, RX and TX paths.
- HBM, TQE, radios, MDIO writes, external-switch reset and flash are absent.
- The exact initramfs boots under QEMU, configures its requested address,
  starts Dropbear, accepts its dedicated key and returns:
  `RAMSSH_QEMU_GATE_OK`.
- UART always receives a rescue shell, including when Ethernet setup fails.

QEMU evidence:

- `outputs/emulation/qemu-ramssh-rootfs-gate.serial.log`
- `outputs/emulation/qemu-ramssh-rootfs-gate.ssh.log`
- `outputs/emulation/qemu-ramssh-rootfs-gate.guest-errors.log` (empty)
- final marker: `RAMSSH_ROOTFS_QEMU_GATE_PASS`

## Hardware boundary

QEMU cannot emulate the proprietary Topaz Arasan EMAC block. Therefore the
first real RX/TX packet and IRQ 20 remain hardware gates. The driver refuses
the takeover if Bootbase DMA does not reach the stopped state within 50 ms;
it does not force a reset in that failure path.

The hardware test must be performed only with a working UART prompt. It is a
volatile boot: a power cycle returns to the untouched OEM flash.

## Final artifacts

- `outputs/kernel-port/linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage`
- `outputs/kernel-port/linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.vmlinux`
- `outputs/kernel-port/linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.config`
- `outputs/kernel-port/linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.initramfs.cpio`
- `outputs/kernel-port/linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.sha256`

The private client key remains outside the workspace at:

```text
/home/user/openmitrastar-ramssh-keys/client_ed25519
```

## RAM placement proof

The uImage is `0x3ddb80` bytes. The proposed TFTP staging address is
`0x87000000`:

```text
TFTP source:        0x87000000..0x873ddb80
kernel destination: 0x8493a000..0x84d17b40
DDR end:            0x88000000
```

Source and destination do not overlap and both remain below the DDR end.

## First hardware test (not executed)

Serve the uImage by TFTP, interrupt autoboot over UART, then use only volatile
environment changes:

```text
topaz> setenv ipaddr <router-bootloader-ip>
topaz> setenv serverip <tftp-server-ip>
topaz> tftpboot 0x87000000 linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage
topaz> iminfo 0x87000000
topaz> bootm 0x87000000
```

Never run `saveenv`. Never invoke an update command. Expected serial markers:

```text
RAMSSH_INIT_START Linux 5.10 ARC700
RAMSSH_NET_OK eth0=192.168.1.200/24
RAMSSH_SSH_READY 192.168.1.200:22 key-only
RAMSSH_UART_SHELL_READY
```

Connect from WSL after the SSH marker:

```bash
ssh -i /home/user/openmitrastar-ramssh-keys/client_ed25519 \
  -o IdentitiesOnly=yes root@192.168.1.200
```

If Ethernet does not work, keep the UART shell for diagnostics. If the kernel
hangs, power-cycle the board; no persistent state was changed.

## Rebuild

```powershell
wsl.exe -d podman-mem9-tidb -- bash \
  /workspace/user-home/Desktop/MitraStar/tools/build_topaz_linux_510.sh ramssh
```

The build rejects `TOPAZ_PACK_FLASH_ARTIFACTS=1` for the `ramssh` profile.
