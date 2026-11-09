# OpenMitraStar Linux 5.10 SSH emulation gate

Date: 2026-08-13
Result: PASS
Scope: isolated QEMU validation only. No router access, reboot, flash write, or host network reconfiguration.

## Proven path

- Linux 5.10.260 boots as ARC700.
- The validation CPU reports ARC MMUv2 with 8 KiB pages and a 128x2 JTLB.
- The kernel enables the matched MMU and reaches a native static PID 1.
- VirtIO MMIO networking is available at `0xf0100000`, IRQ 31.
- The guest configures `eth0` as `10.0.2.15/24`.
- QEMU exposes guest TCP 22 only on host loopback `127.0.0.1:2222`.
- Dropbear accepts the lab-only Ed25519 key.
- A command executed over OpenSSH returns `OPENMITRASTAR_SSH_OK`.

## Reproduce

From PowerShell in `/workspace/user-home\Desktop\MitraStar`:

```powershell
wsl.exe -d podman-mem9-tidb -- sh /workspace/user-home/Desktop/MitraStar/work/ssh-emulation/build-dropbear-lab.sh
wsl.exe -d podman-mem9-tidb -- bash /workspace/user-home/Desktop/MitraStar/work/ssh-emulation/build-ssh-lab.sh
wsl.exe -d podman-mem9-tidb -- bash /workspace/user-home/Desktop/MitraStar/work/ssh-emulation/run-ssh-gate.sh
```

Expected final output:

```text
OPENMITRASTAR_SSH_OK
OPENMITRASTAR_SSH_GATE_PASS
```

For a persistent loopback-only lab:

```powershell
wsl.exe -d podman-mem9-tidb -- bash /workspace/user-home/Desktop/MitraStar/work/ssh-emulation/manage-ssh-lab.sh start
wsl.exe -d podman-mem9-tidb -- bash /workspace/user-home/Desktop/MitraStar/work/ssh-emulation/manage-ssh-lab.sh status
wsl.exe -d podman-mem9-tidb -- bash /workspace/user-home/Desktop/MitraStar/work/ssh-emulation/manage-ssh-lab.sh stop
```

Connect with the lab-only client key:

```powershell
wsl.exe -d podman-mem9-tidb -- ssh -i /home/user/openmitrastar-ssh-lab/client_ed25519 -p 2222 -o IdentitiesOnly=yes -o UserKnownHostsFile=/home/user/openmitrastar-ssh-lab/known_hosts root@127.0.0.1
```

## Artifacts

- `outputs/emulation/openmitrastar-linux-5.10.260-arc700-ssh.vmlinux`
  - SHA-256: `764f7d3e70da92c45b2f0f5daed8bfc494c8bcdb17be84f0d8f6c81ce3b116fb`
- `outputs/emulation/openmitrastar-linux-5.10.260-arc700-ssh-initramfs.cpio`
  - SHA-256: `f850b20eb50c5f9ae617a7b49237784d59f35fa8d918115afa42a15116d59eec`
- `outputs/emulation/qemu-ssh-gate.serial.log`
- `outputs/emulation/qemu-ssh-gate.ssh.log`

## Boundary

This gate validates CPU userspace, MMU, initramfs, TCP/IP, VirtIO and SSH in the QEMU twin. It is not a flashable hardware image and does not yet validate Bootbase packaging, Ethernet MAC hardware, Quantenna 5 GHz, Realtek 2.4 GHz, calibration data, or the physical board.
