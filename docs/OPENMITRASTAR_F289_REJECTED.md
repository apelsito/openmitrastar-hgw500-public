# OpenMitraStar F289 rejected experiment

Date: 2026-09-03

F289 restricted full RX DMA restart to periods with a persistent hardware RX
fault bit. The candidate built correctly, its binary contract passed and it was
written only to `mtd4/linux_live` with complete readback and protected
partitions unchanged.

The platform initially booted successfully. Before traffic testing, Ethernet,
SSH and the web became unreachable. UART remained alive and showed the RX
packet counter frozen while idle time increased, with no RX restart being
attempted. This directly contradicts the F289 hypothesis: on this Topaz EMAC,
the periodic stagnant recovery remains necessary even when no fault bit is
visible.

The exact F288 image was restored through Bootbase TFTP. Full-slot readback,
protected partitions and the post-flash platform gate passed.

Decision: `REJECT_F289_KEEP_F288`.

Evidence:

- `outputs/f3-certification/f289-rejected-20260903/result.json`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f289-device-bound/flash-one-shot-20260903T225131Z/result.json`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f288-device-bound/flash-one-shot-20260903T230137Z/result.json`
- `outputs/postflash/f289-device-20260903T230128Z/status.json`
