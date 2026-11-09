#ifndef QDRV_ABI_V89_H
#define QDRV_ABI_V89_H

#include <linux/build_bug.h>
#include <linux/errno.h>
#include <linux/stddef.h>
#include <linux/types.h>
#include <qtn/qtn_cca.h>
#include <qtn/lhost_muc_comm.h>

/* Recovered v37.4.0.89 wire contract. Keep it versioned and unpublished. */
#define QDRV_V89_SAMP_TSF_SLOTS		10
#define QDRV_V89_SAMP_HOST_CONTROL	0x0010
#define QDRV_V89_SAMP_RUNTIME_APPROVED	0
#define QDRV_V89_VAP_PAYLOAD_SIZE	24
#define QDRV_V89_VAP_TRANSFER_SIZE	25
#define QDRV_V89_NAC_ENTRY_COUNT	128
#define QDRV_V89_NAC_RUNTIME_APPROVED	0
#define QDRV_V89_TXBF_RUNTIME_APPROVED	0
#define QDRV_V89_TXBF_LAYOUT_APPROVED	1
#define QDRV_V89_TXBF_ALGO_TAIL_OFFSET	0x1190
#define QDRV_V89_TXBF_OPAQUE_EXT_OFFSET	0x11a4
#define QDRV_V89_TXBF_MBOX_SIZE		0x11b0
#define QDRV_V89_DSP_QMAT_STATS_OFFSET	0x1070
#define QDRV_V89_MUC_DSP_RING_COUNT	32
#define QDRV_V89_MUC_DSP_SPECIAL_INDEX	0xff
#define QDRV_V89_MUC_DSP_SPECIAL_OFFSET	0x820
#define QDRV_V89_MUC_DSP_MBOX_SIZE	0x860
#define QDRV_V89_MUC_DSP_RUNTIME_APPROVED 0
#define QDRV_V89_SCS_OC_INFO_COUNT	32
#define QDRV_V89_SCS_HISTORY_COUNT	43
#define QDRV_V89_SCS_SCAN_CHANNELS	255
#define QDRV_V89_SCS_RUNTIME_APPROVED	0
#define QDRV_V89_SCAN_RUNTIME_APPROVED	0
#define QDRV_V89_SHARED_ALLOC_SIZE	0x77a0
#define QDRV_V89_PAIR_GATE_MAGIC	0x56383947U
#define QDRV_V89_AUC_DEFAULT_SHA256 "e1fd397ef56b061af7c91cbd422973dcfcf1382933afa226f8f428dd315f65af"
#define QDRV_V89_AUC_NOMU_SHA256 "c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6"
#define QDRV_V89_MUC_SHA256 "71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4"
#define QDRV_V89_DSP_SHA256 "87c882910d87cd29ba2004c4154e9240291aaad6aedb0ff4d90c7a5570be79fd"

#define QDRV_V89_NAC_PKT_CONTROL	0
#define QDRV_V89_NAC_PKT_DATA		1
#define QDRV_V89_NAC_PKT_MANAGEMENT	2

struct qtn_samp_chan_info_v89 {
	u32 freq_band;
	u32 samp_channel;
	u32 duration_msecs;
	u32 status;
	u16 control_flags;
	u16 control_reserved;
	u64 start_tsf;
	struct out_cca_info result;
	u32 type;
	u32 qosnull_txdesc_host;
	u32 qosnull_txdesc_bus;
	u16 qosnull_frame_len;
	u16 tx_node_idx;
	u32 qosnull_txtsf;
	u32 qosnull_nav;
	u64 tsf[QDRV_V89_SAMP_TSF_SLOTS];
};

struct qtn_remain_chan_info_v89 {
	u32 chipid;
	u32 data_channel;
	u32 off_channel;
	u32 flags;
	u64 start_tsf;
	u32 duration_usecs;
	u32 status;
	u8 peer_mac[6];
};

/*
 * Recovered from qdrv_wlan_get_nac_info() in the OEM .89 qdrv module.
 * Keep the timestamp split into wire words: this makes the 4-byte ARC ABI
 * alignment explicit and avoids importing host compiler u64 alignment.
 */
struct qtn_nac_mon_entry_v89 {
	u8 valid;
	s8 rssi_db;
	u8 channel;
	u8 packet_type;
	u32 timestamp_lo;
	u32 timestamp_hi;
	u8 mac_addr[6];
	u8 reserved[2];
};

/*
 * MuC reads/writes the first three halfwords.  Their wider policy semantics
 * and the final 28 bytes are intentionally left opaque until matching .89
 * headers are recovered.  The allocation and entry array are exact.
 */
struct qtn_nac_mon_info_v89 {
	u16 config_value0;
	u16 config_value1;
	u16 enabled;
	u16 reserved;
	struct qtn_nac_mon_entry_v89 entries[QDRV_V89_NAC_ENTRY_COUNT];
	u8 opaque_tail[28];
};

/*
 * Exact .89 algorithm-control suffix of qtn_txbf_mbox.  Existing .62.1
 * controls move by four bytes; the final twelve bytes are firmware-owned and
 * remain opaque.  This is a substructure contract, not the complete mailbox.
 */
struct qtn_txbf_algo_tail_v89 {
	u32 ranking_algorithm_to_use;
	u32 precoding_algorithm_to_use;
	u32 rank_criteria_to_use;
	u32 mu_prec_cache_max_time;
	s32 mu_rank_tolerance;
	u8 opaque_extension[12];
};

/* Exact bounded .89 sublayout; the word at mailbox+0x1074 has no recovered name. */
struct qtn_dsp_qmat_stats_v89 {
	u32 dsp_qmat_invalid;
	u8 opaque_after_dsp_qmat_invalid[4];
	s32 dsp_sram_qmat_num;
	u32 dsp_err_neg_qmat_num;
	u32 dsp_flag;
};

/*
 * .89 preserves the 32-entry circular ring and appends one cache-line-sized
 * special message slot selected by mailbox index 0xff.  It is not ring[33].
 */
struct qtn_muc_dsp_mbox_v89 {
	volatile u32 muc_to_dsp_mbox;
	volatile u32 dsp_to_muc_mbox;
	volatile struct qtn_rate_train_info ring[QDRV_V89_MUC_DSP_RING_COUNT]
		__attribute__((aligned(32)));
	volatile struct qtn_rate_train_info special_slot;
};

/*
 * Complete .89 TXBF wire image. The two byte-compatible regions retain the
 * proven .62.1 layout; only the inserted and appended opaque ranges differ.
 */
struct qtn_txbf_mbox_v89 {
	volatile u32 wr;
	volatile u32 muc_to_dsp_action_frame_mbox[12];
	volatile u32 muc_to_dsp_ndp_mbox;
	volatile u32 muc_to_dsp_del_grp_node_mbox;
	volatile u32 muc_to_dsp_gr_upd_done_mbox;
	volatile u32 muc_to_trig_mu_grp_sel_mbox;
	volatile u32 dsp_to_host_mbox;
	u8 v62_compatible_body_before_qmat[0x1028];
	struct qtn_dsp_qmat_stats_v89 qmat_stats;
	u8 v62_compatible_dsp_stats_after_qmat[0x10c];
	struct qtn_txbf_algo_tail_v89 algorithm_tail;
};

struct qtn_scs_oc_info_v89 {
	u32 off_channel;
	u32 off_chan_bw_sel;
	u32 off_chan_cca_busy;
	u32 off_chan_cca_sample_cnt;
	u32 off_chan_cca_try_cnt;
	u32 off_chan_beacon_recvd;
	u32 off_chan_crc_errs;
	u32 off_chan_sp_errs;
	u32 off_chan_lp_errs;
	u32 off_chan_cca_pri;
	u32 off_chan_cca_sec;
	u32 off_chan_cca_sec40;
};

struct qtn_scs_scan_info_v89 {
	u32 bw_sel;
	u32 cca_idle;
	u32 cca_busy;
	u32 cca_tx;
	u32 cca_intf;
	u32 cca_try;
	u32 cca_pri;
	u32 cca_sec;
	u32 cca_sec40;
	u32 bcn_rcvd;
	u32 crc_err;
	u32 lpre_err;
	u32 spre_err;
};

struct qtn_scs_info_v89 {
	u32 oc_info_count;
	struct qtn_scs_oc_info_v89 oc_info[QDRV_V89_SCS_OC_INFO_COUNT];
	u32 bw_sel;
	u32 cca_try;
	u32 cca_busy;
	u32 cca_idle;
	u32 cca_tx;
	u32 cca_interference;
	u32 cca_pri;
	u32 cca_sec;
	u32 cca_sec40;
	u32 beacon_recvd;
	u32 tx_usecs;
	u32 rx_usecs;
	struct qtn_scs_vsp_info scs_vsp_info;
};

struct qtn_scs_stats_history_v89 {
	struct qtn_scs_data_history lp_errs[QDRV_V89_SCS_HISTORY_COUNT];
	struct qtn_scs_data_history sp_errs[QDRV_V89_SCS_HISTORY_COUNT];
};

struct qtn_scs_info_set_v89 {
	u32 valid_index;
	struct qtn_scs_info_v89 scs_info[2];
	struct qtn_scs_scan_info_v89 scan_info[QDRV_V89_SCS_SCAN_CHANNELS];
	struct qtn_scs_stats_history_v89 stats_history;
};

struct qtn_scan_chan_info_v89 {
	u32 freq_band;
	u32 scan_channel;
	u32 dwell_msecs;
	u32 muc_status;
	u32 scan_flags;
	u8 opaque_at_0x14[4];
	u32 start_txdesc_host;
	u32 start_txdesc_bus;
	u16 start_node_idx;
	u16 start_frame_len;
	u32 prbreq_txdesc_host;
	u32 prbreq_txdesc_bus;
	u16 prbreq_node_idx;
	u16 prbreq_frame_len;
	u32 finish_txdesc_host;
	u32 finish_txdesc_bus;
	u16 finish_node_idx;
	u16 finish_frame_len;
	u64 tsf[SCAN_CHAN_TSF_LOG_NUM];
};

struct qdrv_v89_board_gate {
	s32 board_id, emac0, emac1, wifi_hw, rfic, calstate;
	s32 ext_lna_gain, ext_lna_bypass_gain, tx_power_cal;
	s32 min_tx_power, max_tx_power, allow_dram_sram_fallback;
};

struct shared_params_v89_wire {
	u8 v62_compatible_prefix[76];
	u32 fw_no_mu;
	u8 v62_compatible_body[308];
	u32 nac_mon_info_lhost;
	u32 nac_mon_info_bus;
	u8 opaque_tail[4];
};

struct qdrv_shared_params_alloc_v89 {
	struct shared_params_v89_wire params;
	struct qtn_txbf_mbox_v89 txbf_mbox;
	struct qtn_muc_dsp_mbox_v89 muc_dsp_mbox;
	u8 bb_mutex[12];
	u8 csa[44];
	struct qtn_samp_chan_info_v89 chan_sample;
	struct qtn_scan_chan_info_v89 chan_scan;
	struct qtn_scs_info_set_v89 scs_info_set;
	struct qtn_remain_chan_info_v89 remain_chan;
	u8 ocac[72];
	u8 chan_meas[56];
	u8 sem_trace_log[1584];
	u8 bmps[16];
	struct qtn_nac_mon_info_v89 nac_mon_info;
};

static_assert(sizeof(struct qtn_samp_chan_info_v89) == 160);
static_assert(offsetof(struct qtn_samp_chan_info_v89, control_flags) == 16);
static_assert(offsetof(struct qtn_samp_chan_info_v89, start_tsf) == 20);
static_assert(offsetof(struct qtn_samp_chan_info_v89, result) == 28);
static_assert(offsetof(struct qtn_samp_chan_info_v89, type) == 56);
static_assert(offsetof(struct qtn_samp_chan_info_v89, tsf) == 80);
static_assert(sizeof(struct qtn_remain_chan_info_v89) == 40);
static_assert(offsetof(struct qtn_remain_chan_info_v89, flags) == 12);
static_assert(offsetof(struct qtn_remain_chan_info_v89, start_tsf) == 16);
static_assert(offsetof(struct qtn_remain_chan_info_v89, duration_usecs) == 24);
static_assert(offsetof(struct qtn_remain_chan_info_v89, status) == 28);
static_assert(offsetof(struct qtn_remain_chan_info_v89, peer_mac) == 32);
static_assert(sizeof(struct qtn_nac_mon_entry_v89) == 20);
static_assert(offsetof(struct qtn_nac_mon_entry_v89, rssi_db) == 1);
static_assert(offsetof(struct qtn_nac_mon_entry_v89, channel) == 2);
static_assert(offsetof(struct qtn_nac_mon_entry_v89, packet_type) == 3);
static_assert(offsetof(struct qtn_nac_mon_entry_v89, timestamp_lo) == 4);
static_assert(offsetof(struct qtn_nac_mon_entry_v89, mac_addr) == 12);
static_assert(sizeof(struct qtn_nac_mon_info_v89) == 2596);
static_assert(offsetof(struct qtn_nac_mon_info_v89, enabled) == 4);
static_assert(offsetof(struct qtn_nac_mon_info_v89, entries) == 8);
static_assert(offsetof(struct qtn_nac_mon_info_v89, opaque_tail) == 2568);
static_assert(sizeof(struct qtn_txbf_algo_tail_v89) == 32);
static_assert(offsetof(struct qtn_txbf_algo_tail_v89, ranking_algorithm_to_use) == 0);
static_assert(offsetof(struct qtn_txbf_algo_tail_v89, precoding_algorithm_to_use) == 4);
static_assert(offsetof(struct qtn_txbf_algo_tail_v89, rank_criteria_to_use) == 8);
static_assert(offsetof(struct qtn_txbf_algo_tail_v89, mu_prec_cache_max_time) == 12);
static_assert(offsetof(struct qtn_txbf_algo_tail_v89, mu_rank_tolerance) == 16);
static_assert(offsetof(struct qtn_txbf_algo_tail_v89, opaque_extension) == 20);
static_assert(QDRV_V89_TXBF_ALGO_TAIL_OFFSET +
	      sizeof(struct qtn_txbf_algo_tail_v89) == QDRV_V89_TXBF_MBOX_SIZE);
static_assert(sizeof(struct qtn_dsp_qmat_stats_v89) == 20);
static_assert(offsetof(struct qtn_dsp_qmat_stats_v89,
	      opaque_after_dsp_qmat_invalid) == 4);
static_assert(offsetof(struct qtn_dsp_qmat_stats_v89, dsp_sram_qmat_num) == 8);
static_assert(offsetof(struct qtn_dsp_qmat_stats_v89, dsp_flag) == 16);
static_assert(sizeof(struct qtn_txbf_mbox_v89) == QDRV_V89_TXBF_MBOX_SIZE);
static_assert(offsetof(struct qtn_txbf_mbox_v89, muc_to_dsp_ndp_mbox) == 52);
static_assert(offsetof(struct qtn_txbf_mbox_v89, dsp_to_host_mbox) == 68);
static_assert(offsetof(struct qtn_txbf_mbox_v89, qmat_stats) == 0x1070);
static_assert(offsetof(struct qtn_txbf_mbox_v89, algorithm_tail) == 0x1190);
static_assert(sizeof(struct qtn_muc_dsp_mbox_v89) == QDRV_V89_MUC_DSP_MBOX_SIZE);
static_assert(__alignof__(struct qtn_muc_dsp_mbox_v89) == 32);
static_assert(offsetof(struct qtn_muc_dsp_mbox_v89, ring) == 0x20);
static_assert(offsetof(struct qtn_muc_dsp_mbox_v89, special_slot) ==
	      QDRV_V89_MUC_DSP_SPECIAL_OFFSET);
static_assert(sizeof(struct qtn_scs_scan_info_v89) == 0x34);
static_assert(sizeof(struct qtn_scs_oc_info_v89) == 0x30);
static_assert(offsetof(struct qtn_scs_oc_info_v89, off_chan_cca_pri) == 0x24);
static_assert(offsetof(struct qtn_scs_scan_info_v89, cca_pri) == 0x18);
static_assert(offsetof(struct qtn_scs_scan_info_v89, bcn_rcvd) == 0x24);
static_assert(offsetof(struct qtn_scs_scan_info_v89, lpre_err) == 0x2c);
static_assert(offsetof(struct qtn_scs_scan_info_v89, spre_err) == 0x30);
static_assert(sizeof(struct qtn_scs_info_v89) == 0x6c8);
static_assert(offsetof(struct qtn_scs_info_v89, bw_sel) == 0x604);
static_assert(offsetof(struct qtn_scs_info_v89, cca_pri) == 0x61c);
static_assert(offsetof(struct qtn_scs_info_v89, scs_vsp_info) == 0x634);
static_assert(sizeof(struct qtn_scs_stats_history_v89) == 0x810);
static_assert(sizeof(struct qtn_scs_info_set_v89) == 0x4970);
static_assert(offsetof(struct qtn_scs_info_set_v89, scs_info) == 0x4);
static_assert(offsetof(struct qtn_scs_info_set_v89, scan_info) == 0xd94);
static_assert(offsetof(struct qtn_scs_info_set_v89, stats_history) == 0x4160);
static_assert(sizeof(struct qtn_scan_chan_info_v89) == 172);
static_assert(offsetof(struct qtn_scan_chan_info_v89, opaque_at_0x14) == 20);
static_assert(offsetof(struct qtn_scan_chan_info_v89, start_txdesc_host) == 24);
static_assert(offsetof(struct qtn_scan_chan_info_v89, prbreq_txdesc_host) == 36);
static_assert(offsetof(struct qtn_scan_chan_info_v89, finish_txdesc_host) == 48);
static_assert(offsetof(struct qtn_scan_chan_info_v89, tsf) == 60);
static_assert(sizeof(struct shared_params_v89_wire) == 400);
static_assert(offsetof(struct shared_params_v89_wire, fw_no_mu) == 76);
static_assert(offsetof(struct shared_params_v89_wire, nac_mon_info_lhost) == 388);
static_assert(sizeof(struct qdrv_shared_params_alloc_v89) == QDRV_V89_SHARED_ALLOC_SIZE);
static_assert(offsetof(struct qdrv_shared_params_alloc_v89, txbf_mbox) == 0x190);
static_assert(offsetof(struct qdrv_shared_params_alloc_v89, muc_dsp_mbox) == 0x1340);
static_assert(offsetof(struct qdrv_shared_params_alloc_v89, chan_sample) == 0x1bd8);
static_assert(offsetof(struct qdrv_shared_params_alloc_v89, chan_scan) == 0x1c78);
static_assert(offsetof(struct qdrv_shared_params_alloc_v89, scs_info_set) == 0x1d24);
static_assert(offsetof(struct qdrv_shared_params_alloc_v89, nac_mon_info) == 0x6d7c);
static_assert(sizeof(struct qtn_vap_args) == QDRV_V89_VAP_PAYLOAD_SIZE);
static_assert(offsetof(struct qtn_vap_args, vap_id) == 17);
static_assert(offsetof(struct qtn_vap_args, vap_macaddr) == 18);
static_assert(QDRV_V89_VAP_TRANSFER_SIZE == QDRV_V89_VAP_PAYLOAD_SIZE + 1);

/* W3_PAIR_APPROVED is zero: no caller may publish this wire object yet. */
static inline int
qdrv_v89_samp_direct_init(struct qtn_samp_chan_info_v89 *sample,
			  u32 freq_band, u32 channel, u32 duration,
			  u64 start_tsf)
{
	(void)sample;
	(void)freq_band;
	(void)channel;
	(void)duration;
	(void)start_tsf;
	return -EOPNOTSUPP;
}

static inline int
qdrv_v89_remain_init(struct qtn_remain_chan_info_v89 *remain)
{
	(void)remain;
	return -EOPNOTSUPP;
}

static inline int
qdrv_v89_nac_info_init(struct qtn_nac_mon_info_v89 *nac)
{
	(void)nac;
	return -EOPNOTSUPP;
}

static inline int
qdrv_v89_txbf_tail_init(struct qtn_txbf_algo_tail_v89 *tail)
{
	(void)tail;
	return -EOPNOTSUPP;
}

static inline int
qdrv_v89_txbf_mbox_init(struct qtn_txbf_mbox_v89 *mbox)
{
	volatile u8 *raw = (volatile u8 *)mbox;
	size_t i;

	for (i = 0; i < sizeof(*mbox); i++)
		raw[i] = 0;
	for (i = 0; i < ARRAY_SIZE(mbox->muc_to_dsp_action_frame_mbox); i++)
		mbox->muc_to_dsp_action_frame_mbox[i] = ~0U;
	mbox->muc_to_dsp_ndp_mbox = ~0U;
	mbox->dsp_to_host_mbox = ~0U;
	return 0;
}

static inline int
qdrv_v89_dsp_qmat_stats_init(struct qtn_dsp_qmat_stats_v89 *stats)
{
	(void)stats;
	return -EOPNOTSUPP;
}

static inline int
qdrv_v89_muc_dsp_mbox_init(struct qtn_muc_dsp_mbox_v89 *mbox)
{
	(void)mbox;
	return -EOPNOTSUPP;
}

static inline int
qdrv_v89_scs_info_set_init(struct qtn_scs_info_set_v89 *scs)
{
	(void)scs;
	return -EOPNOTSUPP;
}

static inline int
qdrv_v89_scan_chan_init(struct qtn_scan_chan_info_v89 *scan)
{
	(void)scan;
	return -EOPNOTSUPP;
}

static inline int
qdrv_v89_shared_publish_init(struct qdrv_shared_params_alloc_v89 *a,
			     u32 local_base, u32 bus_base,
			     const struct qdrv_v89_board_gate *b,
			     u32 gate_magic)
{
	volatile u8 *raw = (volatile u8 *)a;
	u32 *p = (u32 *)&a->params;
	size_t i;

	if (gate_magic != QDRV_V89_PAIR_GATE_MAGIC || !b ||
	    b->board_id != 65535 || b->emac0 != 1 || b->emac1 != 1 ||
	    b->wifi_hw != 7 || b->rfic != 4 || b->calstate != 3 ||
	    b->ext_lna_gain != 12 || b->ext_lna_bypass_gain != -5 ||
	    b->tx_power_cal != 0 || b->min_tx_power != 7 ||
	    b->max_tx_power != 21 || b->allow_dram_sram_fallback != 0)
		return -EPERM;
	for (i = 0; i < sizeof(*a); i++)
		raw[i] = 0;
	qdrv_v89_txbf_mbox_init(&a->txbf_mbox);
	a->muc_dsp_mbox.muc_to_dsp_mbox = ~0U;
	a->muc_dsp_mbox.dsp_to_muc_mbox = ~0U;
#define QDRV_V89_PTR(_word, _member) do { \
	p[_word] = local_base + offsetof(struct qdrv_shared_params_alloc_v89, _member); \
	p[(_word) + 1] = bus_base + offsetof(struct qdrv_shared_params_alloc_v89, _member); \
} while (0)
	QDRV_V89_PTR(20, txbf_mbox);
	QDRV_V89_PTR(22, muc_dsp_mbox);
	QDRV_V89_PTR(24, bb_mutex);
	QDRV_V89_PTR(26, csa);
	QDRV_V89_PTR(28, chan_sample);
	QDRV_V89_PTR(30, chan_scan);
	QDRV_V89_PTR(32, scs_info_set);
	QDRV_V89_PTR(34, remain_chan);
	QDRV_V89_PTR(36, ocac);
	QDRV_V89_PTR(38, bmps);
	QDRV_V89_PTR(40, chan_meas);
	QDRV_V89_PTR(42, sem_trace_log);
	QDRV_V89_PTR(97, nac_mon_info);
#undef QDRV_V89_PTR
	return 0;
}

#endif
