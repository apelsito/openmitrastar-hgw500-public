# OpenMitraStar F270 Full current state

Date: 2026-09-03

- Runtime: `lyoko-foundation-6.1.3-f270-qtn-step-path-fix-device`
- Candidate bytes: `5255168`
- Candidate SHA-256: `1fb6c76b17ed0b05676a014f03d4821fe6e1186992ffee22396327937c312d5e`
- Full-slot CRC32: `9615e7d3`
- Full-slot SHA-256: `7810fbd052fe3ff6e56fdd9eb177caeadd49ff2822ccb8806c19a237c639e804`
- Bootbase contract and slot fit: PASS
- Kernel, Kconfig, DTB, Realtek and Quantenna modules: byte-identical to F269
- Hardware boot: PASS
- Bootbase TFTP write/readback: PASS
- Platform gate: PASS
- Signed volatile package lifecycle: PASS

F270 is installed in physical `mtd4/linux_live`. It changes only
`/usr/sbin/om-qtn-step` plus release identity. It replaces
the invalid `/sbin/ifconfig` default with the verified `/bin/ifconfig` BusyBox
applet. Offline tests prove two consecutive probes can run and leave no stale
lock.

The physical step runner is `tools/run_f270_qtn_step_gate.py`. It requires the
exact ACK, pinned SSH identity and live COM3 capture. Steps after
`interface-up-same` additionally require `--allow-management-loss`.

Physical same-value probes:

- `rf-write-same`: PASS with UART begin/pass markers and SSH preserved.
- `interface-up-same`: PASS with UART begin/pass markers and SSH preserved.
- lock removed after each execution: PASS.
- 2.4 GHz and 5 GHz remain `ap-ready`; fatal count remains zero.

Evidence:

- `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f270-device-bound\flash-one-shot-20260903T102952Z\result.json`
- `outputs/postflash/f270-device-20260903T102941Z/`
- `outputs/postflash/f270-qtn-step-rf-write-same-20260903T103310Z/result.json`
- `outputs/postflash/f270-qtn-step-interface-up-same-20260903T103315Z/result.json`
- `outputs/postflash/f270-package-20260903-123341/status.json`
