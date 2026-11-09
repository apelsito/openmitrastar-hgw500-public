from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "work/linux510-radio-port/realtek/netqueue-diag/om_netqueue_diag.c"
)


def test_netqueue_diag_is_target_gated_and_read_only():
    text = SOURCE.read_text(encoding="utf-8")
    for marker in (
        'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
        "netif_tx_queue_stopped(txq)",
        "test_bit(__QUEUE_STATE_FROZEN, &txq->state)",
        "netif_xmit_stopped(txq)",
        "qdisc_qlen(qdisc)",
        "dev_get_stats(om_netqueue_dev",
        "OMNETQ start",
        "OMNETQ queue=",
        "classification=READ_ONLY",
        "cancel_delayed_work_sync",
        "dev_put(om_netqueue_dev)",
    ):
        assert marker in text
    for forbidden in (
        "netif_stop_queue",
        "netif_wake_queue",
        "netif_tx_stop_queue",
        "netif_tx_wake_queue",
        "dev_queue_xmit",
        "ndo_start_xmit",
    ):
        assert forbidden not in text
