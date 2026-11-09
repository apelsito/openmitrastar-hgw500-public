# Quantenna 5 GHz TX route audit — 2026-08-23

This lane is an immutable copy of the v4 source used to audit the next TX
discriminator. No source behavior change is selected for the first v5 gate.

## Finding

`qdrv_wlan_init()` sets `QDRV_WLAN_FLAG_AUC_TX` by default. Consequently,
`qdrv_tx_sch_enqueue_to_node()` calls `qdrv_tx_to_auc()` and returns before
`qdrv_sch_enqueue_node()`. The observed `root_qlen=0` and absence of
`dequeue-ready`, `hardstart`, descriptor, mailbox and txdone markers are the
expected signature of that bypass, not proof that qdisc itself discarded the
packet.

`qdrv_tx_to_auc()` builds a TQE CPU-interface descriptor and calls `tqe_tx()`.
That function either reuses an HBM payload or copies into one, frees the skb,
then waits indefinitely in `topaz_tqe_cpuif_tx_nready()` before publishing with
`topaz_tqe_cpuif_tx_start()`. If a later AuC-specific trace is needed, the first
useful markers are: entry to `qdrv_tx_to_auc`, return from `tqe_tx`, HBM buffer
selection, before/after `tx_nready`, and before/after `tx_start`.

## Selected v5 discriminator

Use the existing private ioctl `iwpriv-qtn wifi0 auc_tx 0` while RF is closed.
This preserves the v4 RX alignment fix and forces the existing qdisc/MuC route,
whose full marker chain is already compiled into qdrv. Rollback closes RF and
wifi0 first, then restores `auc_tx 1`, because qdrv intentionally remains
loaded after stop.

Expected discriminating outcomes:

- `root_qlen>0` then `dequeue-ready` proves the scheduler accepted the packet.
- `hardstart` through `txdone` plus bidirectional traffic isolates the fault to
  the direct AuC/TQE path and supplies a reversible operational workaround.
- queue growth without `dequeue-ready` localizes the next fault to qdisc/quota.
- `hardstart` without `txdone` localizes it to the MuC descriptor/hostlink path.

This is RAM-only. It does not write flash, MTD, bootenv or boot selection.
