# OpenMitraStar F291 rejected experiment

Date: 2026-09-04

F291 tested a ten-second memory window for RX faults. A full RX DMA restart was
allowed only when `NO_RX_DESC`, `RX_STOPPED` or `RX_MISSED` had been observed
within that window.

The image built correctly and passed Bootbase transfer, complete readback,
protected-partition checks and the initial platform gate. Two physical Realtek
runs completed successfully. Before run three, however, Ethernet and SSH became
unreachable while Linux continued running over UART with a frozen RX packet
counter and no recovery attempt.

This proves that a fixed ten-second fault-memory window is insufficient. The
F288/F290 fallback remains required. F291 was rejected and the exact F290 image
was restored through Bootbase TFTP.

Decision: `REJECT_F291_KEEP_F290`.

Evidence:

- `outputs/f3-certification/f291-rejected-20260904/result.json`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f291-device-bound/flash-one-shot-20260903T235340Z/result.json`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f290-device-bound/flash-one-shot-20260904T000933Z/result.json`
- `outputs/postflash/f290-device-20260904T000924Z/status.json`
