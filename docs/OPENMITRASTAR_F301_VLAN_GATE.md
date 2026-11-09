# OpenMitraStar F301 VLAN 4090 Gate

Date: 2026-09-04

## Classification

- Design and tooling: READY OFFLINE
- Hardware execution: NOT RUN
- Router contact during preparation: NONE
- UART opened during preparation: NO
- Persistent writes: NONE
- MTD writes: NONE

## Audit Result

F301 has `CONFIG_VLAN_8021Q=y` and `CONFIG_PACKET=y`. Bridge VLAN filtering is
not compiled, so the gate must not turn `br0` into a VLAN-aware bridge. The
product BusyBox has `ifconfig` and `brctl`, but no `ip` or `vconfig` applet.

The previous network preflight therefore proved kernel support but could not
materialize a tagged interface safely. It also treated a second Ethernet path
as mandatory. This gate replaces that assumption with three independent
recovery layers:

1. a router-local timeout in `/run` that deletes `eth0.4090`;
2. a controller-side watchdog that restores the exact adapter VLAN property;
3. a UART Magic SysRq guardian pinned to the proven FTDI device, ready before
   any network mutation.

If any recovery layer is unavailable or another F301 soak, multicast, DFS or
VLAN campaign is active, the gate stops before creating a VLAN.

## Test Topology

```text
Controller dedicated Ethernet adapter
  VLAN 4090, 10.254.90.2/30
           |
           | tagged 802.1Q traffic
           |
HGW eth0.4090, 10.254.90.1/30
  not attached to br0

AELITA -> untagged TCP/22 management monitor
UART   -> verified SysRq help, then emergency reboot if rollback fails
```

The test uses Linux 802.1Q only. It does not enable the proprietary qdrv VLAN
path, `switch_vlan`, FWT or bridge VLAN filtering.

## Runtime Contract

- VLAN ID is fixed to `4090`.
- Router state exists only under `/run/openmitrastar/vlan4090`.
- `br0` membership, state, MTU, forwarding flag, route table, VLAN table,
  `/persist` mount flags and `/proc/mtd` hash are captured before and after.
- AELITA generates continuous untagged management traffic while the controller
  exchanges tagged UDP request/reply packets with the ARC700 endpoint.
- Recovery deadlines are ordered: router runtime rollback first, controller
  restore second and UART SysRq reboot last. A reboot clears all RAM-only VLAN
  state if network rollback cannot be confirmed.
- The Windows VLAN property and temporary `10.254.90.2/30` address are restored
  before the router watchdog and UART guard are disarmed.
- A mismatch after rollback is FAIL even if tagged traffic succeeded.

## Artifacts

- `tools/f301_vlan_endpoint.c`
- `tools/build_f301_vlan_endpoint.py`
- `tools/f301_vlan_controller.ps1`
- `tools/f301_vlan_uart_guard.ps1`
- `tools/f301_vlan_gate.py`
- `tools/test_f301_vlan_gate.py`
- `outputs/kernel-port/f301-vlan-gate/manifest.json`

## Future Physical Command

The controller interface must be named explicitly. The dry-run never opens
UART or contacts either machine.

```powershell
python tools\f301_vlan_gate.py `
  --execute `
  --ack OPENMITRASTAR_F301_VLAN4090_PHYSICAL `
  --controller-interface "<dedicated wired adapter>" `
  --uart-port COM3
```

The latest offline exclusion scan found no active soak, multicast, DFS or VLAN
runner. Execution still remains fail-closed until the controller adapter,
router/AELITA SSH and live SysRq round-trip are verified. The gate does not
flash firmware and never writes an MTD partition.
