// SPDX-License-Identifier: GPL-2.0
/* Copyright(c) 2009-2014  Realtek Corporation.*/

#include "../wifi.h"
#include "../pci.h"
#include "../base.h"
#include "../stats.h"
#include "reg.h"
#include "def.h"
#include "phy.h"
#include <asm/unaligned.h>
#include <linux/dma-mapping.h>
#include <linux/jiffies.h>
#include <linux/module.h>
#include <linux/of.h>

static bool hgw500_tx_close_diag;
module_param_named(hgw500_tx_close_diag, hgw500_tx_close_diag, bool, 0444);
MODULE_PARM_DESC(hgw500_tx_close_diag,
		 "Trace RTL8192EE TX ring closure on HGW-500BNA-QCv2 lab runs");

static bool hgw500_tx_dma_wmb;
module_param_named(hgw500_tx_dma_wmb, hgw500_tx_dma_wmb, bool, 0444);
MODULE_PARM_DESC(hgw500_tx_dma_wmb,
		 "Publish RTL8192EE TXBDs with dma_wmb on HGW-500BNA-QCv2 lab runs");

static bool hgw500_txbd_mgmt_split;
module_param_named(hgw500_txbd_mgmt_split, hgw500_txbd_mgmt_split, bool, 0444);
MODULE_PARM_DESC(hgw500_txbd_mgmt_split,
		 "Split 802.11 management header and body across compact TXBD segments on HGW-500BNA-QCv2");

static unsigned int hgw500_tx_page_units = 2;
module_param_named(hgw500_tx_page_units, hgw500_tx_page_units, uint, 0444);
MODULE_PARM_DESC(hgw500_tx_page_units,
		 "TX packet-buffer page size in 128-byte units for HGW-500BNA-QCv2");

static bool hgw500_force_data_11m;
module_param_named(hgw500_force_data_11m,
		   hgw500_force_data_11m, bool, 0444);
MODULE_PARM_DESC(hgw500_force_data_11m,
		 "Force unicast data to robust 11 Mbps CCK on HGW-500BNA-QCv2");

static bool hgw500_force_data_mcs7;
module_param_named(hgw500_force_data_mcs7,
		   hgw500_force_data_mcs7, bool, 0444);
MODULE_PARM_DESC(hgw500_force_data_mcs7,
		 "Force unicast data to 1-stream MCS7 with fallback on HGW500");

static bool hgw500_force_data_mcs15;
module_param_named(hgw500_force_data_mcs15,
		   hgw500_force_data_mcs15, bool, 0444);
MODULE_PARM_DESC(hgw500_force_data_mcs15,
		 "Bypass firmware RA and use MCS15 with fallback for HGW500 unicast data");

static bool hgw500_force_data_ht40sgi;
module_param_named(hgw500_force_data_ht40sgi,
		   hgw500_force_data_ht40sgi, bool, 0444);
MODULE_PARM_DESC(hgw500_force_data_ht40sgi,
		 "Force HT40 and short GI descriptor bits for HGW500 MCS15 unicast data when the peer advertises support");

static bool hgw500_txbd_be_data_split;
module_param_named(hgw500_txbd_be_data_split,
		   hgw500_txbd_be_data_split, bool, 0444);
MODULE_PARM_DESC(hgw500_txbd_be_data_split,
		 "Split BE data header/LLC and payload across legacy64 TXBD segments");

bool rtl92ee_hgw500_tx_rate_trace;
module_param_named(hgw500_tx_rate_trace,
		   rtl92ee_hgw500_tx_rate_trace, bool, 0444);
MODULE_PARM_DESC(hgw500_tx_rate_trace,
		 "Trace BE TX descriptor policy and firmware RA reports on HGW500");

static unsigned int hgw500_mgmt_reply_rate;
module_param_named(hgw500_mgmt_reply_rate,
		   hgw500_mgmt_reply_rate, uint, 0444);
MODULE_PARM_DESC(hgw500_mgmt_reply_rate,
		 "Force HGW500 AUTH/ASSOC reply TX rate: 0=off, 1=1M, 2=2M, 6=6M, 11=11M");

static bool hgw500_mgmt_trace;
module_param_named(hgw500_mgmt_trace, hgw500_mgmt_trace, bool, 0444);
MODULE_PARM_DESC(hgw500_mgmt_trace,
		 "Trace bounded HGW500 management RX/TX frames when explicitly enabled");

static bool hgw500_oem_tx_report;
module_param_named(hgw500_oem_tx_report,
		   hgw500_oem_tx_report, bool, 0444);
MODULE_PARM_DESC(hgw500_oem_tx_report,
		 "Request and trace OEM RTL8192EE AP TX reports on HGW500");
#include "trx.h"
#include "led.h"
#include "dm.h"
#include "fw.h"

#define H2C_92E_AP_REQ_TX_REPORT	0x43
#define C2H_92E_AP_TX_REPORT		0x04
#define C2H_92E_AP_TX_REPORT_LEN		12

static unsigned long hgw500_oem_tx_report_last_request;
static unsigned int hgw500_oem_tx_report_request_count;
static unsigned int hgw500_oem_tx_report_count;

static void rtl92ee_hgw500_request_oem_tx_report(struct ieee80211_hw *hw,
						 u8 rx_macid)
{
	u8 report_macid = rx_macid < 0x3f ? rx_macid : 2;
	u8 request[2] = { report_macid, 0xff };
	unsigned int event;

	if (!hgw500_oem_tx_report ||
	    !of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") ||
	    time_before(jiffies, hgw500_oem_tx_report_last_request + HZ))
		return;

	/* Live AP traffic has used MACID 2.  Query the RX descriptor MACID first
	 * and keep MACID 2 as a second-slot fallback when they differ.  The OEM
	 * command supports two stations and 0xff means unused.
	 */
	if (report_macid != 2)
		request[1] = 2;
	hgw500_oem_tx_report_last_request = jiffies;
	event = ++hgw500_oem_tx_report_request_count;
	rtl92ee_fill_h2c_cmd(hw, H2C_92E_AP_REQ_TX_REPORT,
			     sizeof(request), request);
	if (event <= 8 || is_power_of_2(event))
		pr_info("OMRTLTXRPT stage=request event=%u rx_macid=%u sta1=%u sta2=%u h2c=%02x\n",
			event, rx_macid, request[0], request[1],
			H2C_92E_AP_REQ_TX_REPORT);
}

static void rtl92ee_hgw500_trace_c2h(struct ieee80211_hw *hw,
				     const u8 *frame, u16 len)
{
	unsigned int event;
	u8 cmd_id;
	u8 seq;
	u16 payload_len;
	unsigned int i;

	if (!hgw500_oem_tx_report ||
	    !of_machine_is_compatible("mitrastar,hgw-500bna-qcv2"))
		return;

	if (len < C2H_DATA_OFFSET) {
		pr_info("OMRTLTXRPT stage=c2h-short len=%u\n", len);
		return;
	}

	cmd_id = frame[0];
	seq = frame[1];
	payload_len = len - C2H_DATA_OFFSET;
	event = ++hgw500_oem_tx_report_count;
	if (event <= 8 || is_power_of_2(event))
		pr_info("OMRTLTXRPT stage=c2h event=%u id=%u seq=%u len=%u raw=%*phN\n",
			event, cmd_id, seq, payload_len,
			min_t(unsigned int, len, 16), frame);

	if (cmd_id != C2H_92E_AP_TX_REPORT)
		return;
	if (payload_len < C2H_92E_AP_TX_REPORT_LEN) {
		pr_info("OMRTLTXRPT stage=report-short event=%u len=%u expected=%u\n",
			event, payload_len, C2H_92E_AP_TX_REPORT_LEN);
		return;
	}

	for (i = 0; i < 2; i++) {
		const u8 *report = frame + C2H_DATA_OFFSET + i * 6;
		u8 macid = report[0];

		if (macid == 0xff)
			continue;
		pr_info("OMRTLTXRPT stage=report event=%u slot=%u macid=%u txok=%u txfail=%u initial_rate=%u\n",
			event, i, macid,
			get_unaligned_le16(report + 1),
			get_unaligned_le16(report + 3), report[5]);
	}
}

enum rtl92ee_hgw500_mgmt_trace_class {
	HGW500_MGMT_PROBE_REQ,
	HGW500_MGMT_PROBE_RESP,
	HGW500_MGMT_AUTH,
	HGW500_MGMT_ASSOC_REQ,
	HGW500_MGMT_ASSOC_RESP,
	HGW500_MGMT_REASSOC_REQ,
	HGW500_MGMT_REASSOC_RESP,
	HGW500_MGMT_DEAUTH,
	HGW500_MGMT_DISASSOC,
	HGW500_MGMT_ACTION,
	HGW500_MGMT_TRACE_CLASS_MAX,
};

static unsigned int hgw500_mgmt_rx_trace_count[HGW500_MGMT_TRACE_CLASS_MAX];
static unsigned int hgw500_mgmt_tx_trace_count[HGW500_MGMT_TRACE_CLASS_MAX];

static int rtl92ee_hgw500_mgmt_trace_class(__le16 fc)
{
	if (ieee80211_is_probe_req(fc))
		return HGW500_MGMT_PROBE_REQ;
	if (ieee80211_is_probe_resp(fc))
		return HGW500_MGMT_PROBE_RESP;
	if (ieee80211_is_auth(fc))
		return HGW500_MGMT_AUTH;
	if (ieee80211_is_assoc_req(fc))
		return HGW500_MGMT_ASSOC_REQ;
	if (ieee80211_is_assoc_resp(fc))
		return HGW500_MGMT_ASSOC_RESP;
	if (ieee80211_is_reassoc_req(fc))
		return HGW500_MGMT_REASSOC_REQ;
	if (ieee80211_is_reassoc_resp(fc))
		return HGW500_MGMT_REASSOC_RESP;
	if (ieee80211_is_deauth(fc))
		return HGW500_MGMT_DEAUTH;
	if (ieee80211_is_disassoc(fc))
		return HGW500_MGMT_DISASSOC;
	if (ieee80211_is_action(fc))
		return HGW500_MGMT_ACTION;
	return -1;
}

static const char *rtl92ee_mgmt_subtype_name(__le16 fc)
{
	if (ieee80211_is_probe_req(fc))
		return "probe_req";
	if (ieee80211_is_probe_resp(fc))
		return "probe_resp";
	if (ieee80211_is_auth(fc))
		return "auth";
	if (ieee80211_is_assoc_req(fc))
		return "assoc_req";
	if (ieee80211_is_assoc_resp(fc))
		return "assoc_resp";
	if (ieee80211_is_reassoc_req(fc))
		return "reassoc_req";
	if (ieee80211_is_reassoc_resp(fc))
		return "reassoc_resp";
	if (ieee80211_is_deauth(fc))
		return "deauth";
	if (ieee80211_is_disassoc(fc))
		return "disassoc";
	if (ieee80211_is_action(fc))
		return "action";
	return "mgmt_other";
}

static bool rtl92ee_hgw500_mgmt_reply_desc_rate(__le16 fc, u8 *rate)
{
	if (!ieee80211_is_auth(fc) &&
	    !ieee80211_is_assoc_resp(fc) &&
	    !ieee80211_is_reassoc_resp(fc))
		return false;

	switch (hgw500_mgmt_reply_rate) {
	case 1:
		*rate = DESC_RATE1M;
		return true;
	case 2:
		*rate = DESC_RATE2M;
		return true;
	case 6:
		*rate = DESC_RATE6M;
		return true;
	case 11:
		*rate = DESC_RATE11M;
		return true;
	default:
		return false;
	}
}

static bool rtl92ee_hgw500_trace_mgmt_frame(struct ieee80211_hw *hw,
					    __le16 fc,
					    unsigned int *counters)
{
	int trace_class;
	unsigned int initial_limit;
	unsigned int n;

	if (!hgw500_mgmt_trace)
		return false;
	if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2"))
		return false;
	if (rtl_priv(hw)->rtlhal.hw_type != HARDWARE_TYPE_RTL8192EE)
		return false;
	if (!ieee80211_is_mgmt(fc))
		return false;
	trace_class = rtl92ee_hgw500_mgmt_trace_class(fc);
	if (trace_class < 0)
		return false;

	/* Probe traffic can be noisy enough to consume a shared trace budget
	 * before a client starts AUTH/ASSOC. Keep an independent bounded counter
	 * for every subtype so the first join attempt is always observable.
	 */
	initial_limit = trace_class == HGW500_MGMT_PROBE_REQ ||
			trace_class == HGW500_MGMT_PROBE_RESP ? 16 : 64;
	n = ++counters[trace_class];
	return n <= initial_limit || !(n & (n - 1));
}

static bool rtl92ee_is_robust_mgmt_frame_unaligned(const u8 *frame,
						    __le16 frame_control)
{
	if (ieee80211_is_disassoc(frame_control) ||
	    ieee80211_is_deauth(frame_control))
		return true;

	if (!ieee80211_is_action(frame_control))
		return false;
	if (ieee80211_has_protected(frame_control))
		return true;

	return frame[24] != WLAN_CATEGORY_PUBLIC &&
		frame[24] != WLAN_CATEGORY_HT &&
		frame[24] != WLAN_CATEGORY_WNM_UNPROTECTED &&
		frame[24] != WLAN_CATEGORY_SELF_PROTECTED &&
		frame[24] != WLAN_CATEGORY_UNPROT_DMG &&
		frame[24] != WLAN_CATEGORY_VHT &&
		frame[24] != WLAN_CATEGORY_VENDOR_SPECIFIC;
}

static bool rtl92ee_hgw500_is_eapol_data(struct sk_buff *skb, __le16 fc)
{
	const u8 *llc;
	unsigned int hdr_len;
	u16 ethertype;

	if (!of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") ||
	    !ieee80211_is_data(fc))
		return false;

	hdr_len = ieee80211_hdrlen(fc);
	if (skb->len < hdr_len + 12)
		return false;

	llc = skb->data + hdr_len;
	if (llc[0] != 0xaa || llc[1] != 0xaa || llc[2] != 0x03 ||
	    llc[3] != 0x00 || llc[4] != 0x00 || llc[5] != 0x00)
		return false;

	ethertype = ((u16)llc[6] << 8) | llc[7];
	return ethertype == 0x888e;
}

static u8 _rtl92ee_map_hwqueue_to_fwqueue(struct sk_buff *skb, u8 hw_queue)
{
	__le16 fc = rtl_get_fc(skb);

	if (unlikely(ieee80211_is_beacon(fc)))
		return QSLT_BEACON;
	if (ieee80211_is_mgmt(fc) || ieee80211_is_ctl(fc))
		return QSLT_MGNT;
	if (hw_queue == MGNT_QUEUE && rtl92ee_hgw500_is_eapol_data(skb, fc))
		return QSLT_MGNT;

	return skb->priority;
}

static void _rtl92ee_query_rxphystatus(struct ieee80211_hw *hw,
				       struct rtl_stats *pstatus, u8 *pdesc,
				       struct rx_fwinfo *p_drvinfo,
				       bool bpacket_match_bssid,
				       bool bpacket_toself,
				       bool packet_beacon)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct phy_status_rpt *p_phystrpt = (struct phy_status_rpt *)p_drvinfo;
	s8 rx_pwr_all, rx_pwr[4];
	u8 rf_rx_num = 0, evm, pwdb_all;
	u8 i, max_spatial_stream;
	u32 rssi, total_rssi = 0;
	bool is_cck = pstatus->is_cck;
	u8 lan_idx, vga_idx;

	/* Record it for next packet processing */
	pstatus->packet_matchbssid = bpacket_match_bssid;
	pstatus->packet_toself = bpacket_toself;
	pstatus->packet_beacon = packet_beacon;
	pstatus->rx_mimo_signalquality[0] = -1;
	pstatus->rx_mimo_signalquality[1] = -1;

	if (is_cck) {
		u8 cck_highpwr;
		u8 cck_agc_rpt;
		/* CCK Driver info Structure is not the same as OFDM packet. */
		cck_agc_rpt = p_phystrpt->cck_agc_rpt_ofdm_cfosho_a;

		/* (1)Hardware does not provide RSSI for CCK
		 * (2)PWDB, Average PWDB calculated by
		 * hardware (for rate adaptive)
		 */
		cck_highpwr = (u8)rtl_get_bbreg(hw, RFPGA0_XA_HSSIPARAMETER2,
						 BIT(9));

		lan_idx = ((cck_agc_rpt & 0xE0) >> 5);
		vga_idx = (cck_agc_rpt & 0x1f);
		switch (lan_idx) {
		case 7: /*VGA_idx = 27~2*/
				if (vga_idx <= 27)
					rx_pwr_all = -100 + 2 * (27 - vga_idx);
				else
					rx_pwr_all = -100;
				break;
		case 6: /*VGA_idx = 2~0*/
				rx_pwr_all = -48 + 2 * (2 - vga_idx);
				break;
		case 5: /*VGA_idx = 7~5*/
				rx_pwr_all = -42 + 2 * (7 - vga_idx);
				break;
		case 4: /*VGA_idx = 7~4*/
				rx_pwr_all = -36 + 2 * (7 - vga_idx);
				break;
		case 3: /*VGA_idx = 7~0*/
				rx_pwr_all = -24 + 2 * (7 - vga_idx);
				break;
		case 2: /*VGA_idx = 5~0*/
				if (cck_highpwr)
					rx_pwr_all = -12 + 2 * (5 - vga_idx);
				else
					rx_pwr_all = -6 + 2 * (5 - vga_idx);
				break;
		case 1:
				rx_pwr_all = 8 - 2 * vga_idx;
				break;
		case 0:
				rx_pwr_all = 14 - 2 * vga_idx;
				break;
		default:
				rx_pwr_all = 0;
				break;
		}
		rx_pwr_all += 16;
		pwdb_all = rtl_query_rxpwrpercentage(rx_pwr_all);

		if (!cck_highpwr) {
			if (pwdb_all >= 80)
				pwdb_all = ((pwdb_all - 80) << 1) +
					   ((pwdb_all - 80) >> 1) + 80;
			else if ((pwdb_all <= 78) && (pwdb_all >= 20))
				pwdb_all += 3;
			if (pwdb_all > 100)
				pwdb_all = 100;
		}

		pstatus->rx_pwdb_all = pwdb_all;
		pstatus->bt_rx_rssi_percentage = pwdb_all;
		pstatus->recvsignalpower = rx_pwr_all;

		/* (3) Get Signal Quality (EVM) */
		if (bpacket_match_bssid) {
			u8 sq, sq_rpt;

			if (pstatus->rx_pwdb_all > 40) {
				sq = 100;
			} else {
				sq_rpt = p_phystrpt->cck_sig_qual_ofdm_pwdb_all;
				if (sq_rpt > 64)
					sq = 0;
				else if (sq_rpt < 20)
					sq = 100;
				else
					sq = ((64 - sq_rpt) * 100) / 44;
			}

			pstatus->signalquality = sq;
			pstatus->rx_mimo_signalquality[0] = sq;
			pstatus->rx_mimo_signalquality[1] = -1;
		}
	} else {
		/* (1)Get RSSI for HT rate */
		for (i = RF90_PATH_A; i < RF6052_MAX_PATH; i++) {
			/* we will judge RF RX path now. */
			if (rtlpriv->dm.rfpath_rxenable[i])
				rf_rx_num++;

			rx_pwr[i] = ((p_phystrpt->path_agc[i].gain & 0x3f) * 2)
				    - 110;

			pstatus->rx_pwr[i] = rx_pwr[i];
			/* Translate DBM to percentage. */
			rssi = rtl_query_rxpwrpercentage(rx_pwr[i]);
			total_rssi += rssi;

			pstatus->rx_mimo_signalstrength[i] = (u8)rssi;
		}

		/* (2)PWDB, Average PWDB calculated by
		 * hardware (for rate adaptive)
		 */
		rx_pwr_all = ((p_phystrpt->cck_sig_qual_ofdm_pwdb_all >> 1)
			      & 0x7f) - 110;

		pwdb_all = rtl_query_rxpwrpercentage(rx_pwr_all);
		pstatus->rx_pwdb_all = pwdb_all;
		pstatus->bt_rx_rssi_percentage = pwdb_all;
		pstatus->rxpower = rx_pwr_all;
		pstatus->recvsignalpower = rx_pwr_all;

		/* (3)EVM of HT rate */
		if (pstatus->rate >= DESC_RATEMCS8 &&
		    pstatus->rate <= DESC_RATEMCS15)
			max_spatial_stream = 2;
		else
			max_spatial_stream = 1;

		for (i = 0; i < max_spatial_stream; i++) {
			evm = rtl_evm_db_to_percentage(
						p_phystrpt->stream_rxevm[i]);

			if (bpacket_match_bssid) {
				/* Fill value in RFD, Get the first
				 * spatial stream only
				 */
				if (i == 0)
					pstatus->signalquality = (u8)(evm &
								       0xff);
				pstatus->rx_mimo_signalquality[i] = (u8)(evm &
									  0xff);
			}
		}

		if (bpacket_match_bssid) {
			for (i = RF90_PATH_A; i <= RF90_PATH_B; i++)
				rtl_priv(hw)->dm.cfo_tail[i] =
					(int)p_phystrpt->path_cfotail[i];

			if (rtl_priv(hw)->dm.packet_count == 0xffffffff)
				rtl_priv(hw)->dm.packet_count = 0;
			else
				rtl_priv(hw)->dm.packet_count++;
		}
	}

	/* UI BSS List signal strength(in percentage),
	 * make it good looking, from 0~100.
	 */
	if (is_cck)
		pstatus->signalstrength = (u8)(rtl_signal_scale_mapping(hw,
								     pwdb_all));
	else if (rf_rx_num != 0)
		pstatus->signalstrength = (u8)(rtl_signal_scale_mapping(hw,
						      total_rssi /= rf_rx_num));
}

static void _rtl92ee_translate_rx_signal_stuff(struct ieee80211_hw *hw,
					       struct sk_buff *skb,
					       struct rtl_stats *pstatus,
					       u8 *pdesc,
					       struct rx_fwinfo *p_drvinfo)
{
	struct rtl_mac *mac = rtl_mac(rtl_priv(hw));
	struct rtl_efuse *rtlefuse = rtl_efuse(rtl_priv(hw));
	struct ieee80211_hdr *hdr;
	struct ieee80211_hdr local_hdr;
	u8 *tmp_buf;
	u8 *praddr;
	u8 *psaddr;
	__le16 fc;
	bool packet_matchbssid, packet_toself, packet_beacon;

	tmp_buf = skb->data + pstatus->rx_drvinfo_size +
		  pstatus->rx_bufshift + 24;

	hdr = (struct ieee80211_hdr *)tmp_buf;
	if (unlikely(of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
		     ((unsigned long)tmp_buf & 1))) {
		size_t copy_len = min_t(size_t, pstatus->length,
					sizeof(local_hdr));

		memset(&local_hdr, 0, sizeof(local_hdr));
		memcpy(&local_hdr, tmp_buf, copy_len);
		hdr = &local_hdr;
		pr_info_once("OMRTLRXALIGN stage=signal-safe target=hgw500 rx_shift=%u drvinfo=%u\n",
			     pstatus->rx_bufshift, pstatus->rx_drvinfo_size);
	}
	fc = hdr->frame_control;
	praddr = hdr->addr1;
	psaddr = ieee80211_get_SA(hdr);
	ether_addr_copy(pstatus->psaddr, psaddr);

	packet_matchbssid = (!ieee80211_is_ctl(fc) &&
			       (ether_addr_equal(mac->bssid,
						ieee80211_has_tods(fc) ?
						hdr->addr1 :
						ieee80211_has_fromds(fc) ?
						hdr->addr2 : hdr->addr3)) &&
				(!pstatus->hwerror) && (!pstatus->crc) &&
				(!pstatus->icv));

	packet_toself = packet_matchbssid &&
			 (ether_addr_equal(praddr, rtlefuse->dev_addr));

	if (ieee80211_is_beacon(fc))
		packet_beacon = true;
	else
		packet_beacon = false;

	if (packet_beacon && packet_matchbssid)
		rtl_priv(hw)->dm.dbginfo.num_qry_beacon_pkt++;

	if (packet_matchbssid && ieee80211_is_data_qos(fc) &&
	    !is_multicast_ether_addr(ieee80211_get_DA(hdr))) {
		struct ieee80211_qos_hdr *hdr_qos =
					    (struct ieee80211_qos_hdr *)hdr;
		u16 tid = le16_to_cpu(hdr_qos->qos_ctrl) & 0xf;

		if (tid != 0 && tid != 3)
			rtl_priv(hw)->dm.dbginfo.num_non_be_pkt++;
	}

	_rtl92ee_query_rxphystatus(hw, pstatus, pdesc, p_drvinfo,
				   packet_matchbssid, packet_toself,
				   packet_beacon);
	rtl_process_phyinfo(hw, tmp_buf, pstatus);
}

static void _rtl92ee_insert_emcontent(struct rtl_tcb_desc *ptcb_desc,
				      u8 *virtualaddress8)
{
	u32 dwtmp;
	__le32 *virtualaddress = (__le32 *)virtualaddress8;

	memset(virtualaddress, 0, 8);

	set_earlymode_pktnum(virtualaddress, ptcb_desc->empkt_num);
	if (ptcb_desc->empkt_num == 1) {
		dwtmp = ptcb_desc->empkt_len[0];
	} else {
		dwtmp = ptcb_desc->empkt_len[0];
		dwtmp += ((dwtmp % 4) ? (4 - dwtmp % 4) : 0) + 4;
		dwtmp += ptcb_desc->empkt_len[1];
	}
	set_earlymode_len0(virtualaddress, dwtmp);

	if (ptcb_desc->empkt_num <= 3) {
		dwtmp = ptcb_desc->empkt_len[2];
	} else {
		dwtmp = ptcb_desc->empkt_len[2];
		dwtmp += ((dwtmp % 4) ? (4 - dwtmp % 4) : 0) + 4;
		dwtmp += ptcb_desc->empkt_len[3];
	}
	set_earlymode_len1(virtualaddress, dwtmp);
	if (ptcb_desc->empkt_num <= 5) {
		dwtmp = ptcb_desc->empkt_len[4];
	} else {
		dwtmp = ptcb_desc->empkt_len[4];
		dwtmp += ((dwtmp % 4) ? (4 - dwtmp % 4) : 0) + 4;
		dwtmp += ptcb_desc->empkt_len[5];
	}
	set_earlymode_len2_1(virtualaddress, dwtmp & 0xF);
	set_earlymode_len2_2(virtualaddress, dwtmp >> 4);
	if (ptcb_desc->empkt_num <= 7) {
		dwtmp = ptcb_desc->empkt_len[6];
	} else {
		dwtmp = ptcb_desc->empkt_len[6];
		dwtmp += ((dwtmp % 4) ? (4 - dwtmp % 4) : 0) + 4;
		dwtmp += ptcb_desc->empkt_len[7];
	}
	set_earlymode_len3(virtualaddress, dwtmp);
	if (ptcb_desc->empkt_num <= 9) {
		dwtmp = ptcb_desc->empkt_len[8];
	} else {
		dwtmp = ptcb_desc->empkt_len[8];
		dwtmp += ((dwtmp % 4) ? (4 - dwtmp % 4) : 0) + 4;
		dwtmp += ptcb_desc->empkt_len[9];
	}
	set_earlymode_len4(virtualaddress, dwtmp);
}

bool rtl92ee_rx_query_desc(struct ieee80211_hw *hw,
			   struct rtl_stats *status,
			   struct ieee80211_rx_status *rx_status,
			   u8 *pdesc8, struct sk_buff *skb)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rx_fwinfo *p_drvinfo;
	struct ieee80211_hdr *hdr;
	__le32 *pdesc = (__le32 *)pdesc8;
	u32 phystatus = get_rx_desc_physt(pdesc);
	__le16 frame_control;
	const u8 *frame;
	bool robust_mgmt;
	u8 wake_match;

	if (get_rx_status_desc_rpt_sel(pdesc) == 0)
		status->packet_report_type = NORMAL_RX;
	else
		status->packet_report_type = C2H_PACKET;
	status->length = (u16)get_rx_desc_pkt_len(pdesc);
	status->rx_drvinfo_size = (u8)get_rx_desc_drv_info_size(pdesc) *
				  RX_DRV_INFO_SIZE_UNIT;
	status->rx_bufshift = (u8)(get_rx_desc_shift(pdesc) & 0x03);
	status->icv = (u16)get_rx_desc_icv(pdesc);
	status->crc = (u16)get_rx_desc_crc32(pdesc);
	status->hwerror = (status->crc | status->icv);
	status->decrypted = !get_rx_desc_swdec(pdesc);
	status->rate = (u8)get_rx_desc_rxmcs(pdesc);
	status->shortpreamble = (u16)get_rx_desc_splcp(pdesc);
	status->isampdu = (bool)(get_rx_desc_paggr(pdesc) == 1);
	status->isfirst_ampdu = (bool)((get_rx_desc_paggr(pdesc) == 1) &&
				       (get_rx_desc_faggr(pdesc) == 1));
	status->timestamp_low = get_rx_desc_tsfl(pdesc);
	status->rx_is40mhzpacket = (bool)get_rx_desc_bw(pdesc);
	status->is_ht = (bool)get_rx_desc_rxht(pdesc);
	status->is_cck = RTL92EE_RX_HAL_IS_CCK_RATE(status->rate);

	status->macid = get_rx_desc_macid(pdesc);
	frame = skb->data + status->rx_drvinfo_size +
		status->rx_bufshift + 24;
	/* C2H packets are firmware records, not 802.11 frames.  The generic RX
	 * path consumes them after query_rx_desc(); return before interpreting
	 * their short payload as frame_control or PHY data on the ARC target.
	 */
	if (status->packet_report_type == C2H_PACKET &&
	    of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")) {
		rtl92ee_hgw500_trace_c2h(hw, frame, status->length);
		return true;
	}
	if (get_rx_status_desc_pattern_match(pdesc))
		wake_match = BIT(2);
	else if (get_rx_status_desc_magic_match(pdesc))
		wake_match = BIT(1);
	else if (get_rx_status_desc_unicast_match(pdesc))
		wake_match = BIT(0);
	else
		wake_match = 0;
	if (wake_match)
		rtl_dbg(rtlpriv, COMP_RXDESC, DBG_LOUD,
			"GGGGGGGGGGGGGet Wakeup Packet!! WakeMatch=%d\n",
			wake_match);
	rx_status->freq = hw->conf.chandef.chan->center_freq;
	rx_status->band = hw->conf.chandef.chan->band;

	hdr = (struct ieee80211_hdr *)frame;
	frame = (const u8 *)hdr;
	if (unlikely(of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
		     ((unsigned long)hdr & 1))) {
		frame_control = cpu_to_le16(get_unaligned_le16((const u8 *)hdr));
		robust_mgmt = rtl92ee_is_robust_mgmt_frame_unaligned(
			(const u8 *)hdr, frame_control);
		pr_info_once("OMRTLRXALIGN stage=query-safe target=hgw500 rx_shift=%u drvinfo=%u\n",
			     status->rx_bufshift, status->rx_drvinfo_size);
	} else {
		frame_control = hdr->frame_control;
		robust_mgmt = _ieee80211_is_robust_mgmt_frame(hdr);
	}
	if (!status->hwerror && ieee80211_is_data(frame_control))
		rtl92ee_hgw500_request_oem_tx_report(hw, status->macid);

	if (status->crc)
		rx_status->flag |= RX_FLAG_FAILED_FCS_CRC;

	if (status->rx_is40mhzpacket)
		rx_status->bw = RATE_INFO_BW_40;

	if (status->is_ht)
		rx_status->encoding = RX_ENC_HT;

	rx_status->flag |= RX_FLAG_MACTIME_START;

	/* hw will set status->decrypted true, if it finds the
	 * frame is open data frame or mgmt frame.
	 * So hw will not decryption robust managment frame
	 * for IEEE80211w but still set status->decrypted
	 * true, so here we should set it back to undecrypted
	 * for IEEE80211w frame, and mac80211 sw will help
	 * to decrypt it
	 */
	if (status->decrypted) {
		if (!robust_mgmt && ieee80211_has_protected(frame_control))
			rx_status->flag |= RX_FLAG_DECRYPTED;
		else
			rx_status->flag &= ~RX_FLAG_DECRYPTED;
	}

	/* rate_idx: index of data rate into band's
	 * supported rates or MCS index if HT rates
	 * are use (RX_FLAG_HT)
	 * Notice: this is diff with windows define
	 */
	rx_status->rate_idx = rtlwifi_rate_mapping(hw, status->is_ht,
						   false, status->rate);
	if (status->is_ht)
		pr_info_once("OMRTL92 stage=rx-rate-decode ht=1 desc_rate=%u rate_idx=%d bw40=%u ampdu=%u first=%u dword3=%08x\n",
			     status->rate, rx_status->rate_idx,
			     status->rx_is40mhzpacket, status->isampdu,
			     status->isfirst_ampdu,
			     le32_to_cpu(pdesc[3]));

	rx_status->mactime = status->timestamp_low;
	if (phystatus) {
		p_drvinfo = (struct rx_fwinfo *)(skb->data +
						 status->rx_bufshift + 24);

		_rtl92ee_translate_rx_signal_stuff(hw, skb, status, pdesc8,
						   p_drvinfo);
	}
	rx_status->signal = status->recvsignalpower + 10;
	if (status->length >= 24 &&
	    rtl92ee_hgw500_trace_mgmt_frame(hw, frame_control,
					    hgw500_mgmt_rx_trace_count)) {
		pr_info("OMRTLMGMT stage=rx type=%s fc=%04x len=%u drvinfo=%u shift=%u rate=%u rate_idx=%d ht=%u cck=%u crc=%u icv=%u signal=%d da=%pM sa=%pM bssid=%pM body0=%04x body1=%04x body2=%04x\n",
			rtl92ee_mgmt_subtype_name(frame_control),
			le16_to_cpu(frame_control),
			status->length, status->rx_drvinfo_size,
			status->rx_bufshift, status->rate,
			rx_status->rate_idx, status->is_ht,
			status->is_cck, status->crc, status->icv,
			rx_status->signal, frame + 4, frame + 10,
			frame + 16,
			status->length >= 30 ? get_unaligned_le16(frame + 24) : 0,
			status->length >= 30 ? get_unaligned_le16(frame + 26) : 0,
			status->length >= 30 ? get_unaligned_le16(frame + 28) : 0);
	}
	if (status->packet_report_type == TX_REPORT2) {
		status->macid_valid_entry[0] =
			get_rx_rpt2_desc_macid_valid_1(pdesc);
		status->macid_valid_entry[1] =
			get_rx_rpt2_desc_macid_valid_2(pdesc);
	}
	return true;
}

/*in Windows, this == Rx_92EE_Interrupt*/
void rtl92ee_rx_check_dma_ok(struct ieee80211_hw *hw, u8 *header_desc8,
			     u8 queue_index)
{
	u8 first_seg = 0;
	u8 last_seg = 0;
	u16 total_len = 0;
	u16 read_cnt = 0;
	__le32 *header_desc = (__le32 *)header_desc8;

	if (header_desc == NULL)
		return;

	total_len = (u16)get_rx_buffer_desc_total_length(header_desc);

	first_seg = (u8)get_rx_buffer_desc_fs(header_desc);

	last_seg = (u8)get_rx_buffer_desc_ls(header_desc);

	while (total_len == 0 && first_seg == 0 && last_seg == 0) {
		read_cnt++;
		total_len = (u16)get_rx_buffer_desc_total_length(header_desc);
		first_seg = (u8)get_rx_buffer_desc_fs(header_desc);
		last_seg = (u8)get_rx_buffer_desc_ls(header_desc);

		if (read_cnt > 20)
			break;
	}
}

u16 rtl92ee_rx_desc_buff_remained_cnt(struct ieee80211_hw *hw, u8 queue_index)
{
	struct rtl_pci *rtlpci = rtl_pcidev(rtl_pcipriv(hw));
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u16 read_point, write_point, remind_cnt;
	u32 tmp_4byte;
	static bool start_rx;

	tmp_4byte = rtl_read_dword(rtlpriv, REG_RXQ_TXBD_IDX);
	read_point = (u16)((tmp_4byte>>16) & 0x7ff);
	write_point = (u16)(tmp_4byte & 0x7ff);

	if (write_point != rtlpci->rx_ring[queue_index].next_rx_rp) {
		rtl_dbg(rtlpriv, COMP_RXDESC, DBG_DMESG,
			"!!!write point is 0x%x, reg 0x3B4 value is 0x%x\n",
			write_point, tmp_4byte);
		tmp_4byte = rtl_read_dword(rtlpriv, REG_RXQ_TXBD_IDX);
		read_point = (u16)((tmp_4byte>>16) & 0x7ff);
		write_point = (u16)(tmp_4byte & 0x7ff);
	}

	if (read_point > 0)
		start_rx = true;
	if (!start_rx)
		return 0;

	remind_cnt = calc_fifo_space(read_point, write_point,
				     RTL_PCI_MAX_RX_COUNT);

	if (remind_cnt == 0)
		return 0;

	rtlpci->rx_ring[queue_index].next_rx_rp = write_point;

	return remind_cnt;
}

static u16 get_desc_addr_fr_q_idx(u16 queue_index)
{
	u16 desc_address;

	switch (queue_index) {
	case BK_QUEUE:
		desc_address = REG_BKQ_TXBD_IDX;
		break;
	case BE_QUEUE:
		desc_address = REG_BEQ_TXBD_IDX;
		break;
	case VI_QUEUE:
		desc_address = REG_VIQ_TXBD_IDX;
		break;
	case VO_QUEUE:
		desc_address = REG_VOQ_TXBD_IDX;
		break;
	case BEACON_QUEUE:
		desc_address = REG_BEQ_TXBD_IDX;
		break;
	case TXCMD_QUEUE:
		desc_address = REG_BEQ_TXBD_IDX;
		break;
	case MGNT_QUEUE:
		desc_address = REG_MGQ_TXBD_IDX;
		break;
	case HIGH_QUEUE:
		desc_address = REG_HI0Q_TXBD_IDX;
		break;
	case HCCA_QUEUE:
		desc_address = REG_BEQ_TXBD_IDX;
		break;
	default:
		desc_address = REG_BEQ_TXBD_IDX;
		break;
	}
	return desc_address;
}

u16 rtl92ee_get_available_desc(struct ieee80211_hw *hw, u8 q_idx)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u16 point_diff = 0;
	u16 current_tx_read_point, current_tx_write_point;
	u32 tmp_4byte;

	tmp_4byte = rtl_read_dword(rtlpriv,
				   get_desc_addr_fr_q_idx(q_idx));
	current_tx_read_point = (u16)((tmp_4byte >> 16) & 0x0fff);
	current_tx_write_point = (u16)((tmp_4byte) & 0x0fff);

	point_diff = calc_fifo_space(current_tx_read_point,
				     current_tx_write_point,
				     TX_DESC_NUM_92E);

	return point_diff;
}

static void rtl92ee_pre_fill_tx_bd_desc(struct ieee80211_hw *hw,
					u8 *tx_bd_desc8, u8 *desc8,
					u8 queue_index,
					struct sk_buff *skb,
					dma_addr_t addr)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_pci *rtlpci = rtl_pcidev(rtl_pcipriv(hw));
	u32 pkt_len = skb->len;
	u16 desc_size = 40; /*tx desc size*/
	u32 psblen = 0;
	u16 tx_page_size;
	u32 total_packet_size;
	u16 current_bd_desc;
	u8 i;
	u16 real_desc_size = 0x28;
	u16	append_early_mode_size = 0;
	u8 segmentnum = 1 << (RTL8192EE_SEG_NUM + 1);
	dma_addr_t desc_dma_addr;
	bool dma64 = rtlpriv->cfg->mod_params->dma64;
	__le32 *desc = (__le32 *)desc8;
	__le32 *tx_bd_desc = (__le32 *)tx_bd_desc8;
	bool compact32 = rtlpci->tx_ring[queue_index].buffer_desc_stride == 32;
	bool split_be_data = false;
	u16 split_header_len = 0;

	tx_page_size = 2;
	if (of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
	    hgw500_tx_page_units == 4)
		tx_page_size = 4;
	current_bd_desc = rtlpci->tx_ring[queue_index].cur_tx_wp;

	total_packet_size = desc_size+pkt_len;

	if (rtlpriv->rtlhal.earlymode_enable)	{
		if (queue_index < BEACON_QUEUE) {
			append_early_mode_size = 8;
			total_packet_size += append_early_mode_size;
		}
	}

	if (hgw500_txbd_be_data_split &&
	    of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
	    queue_index == BE_QUEUE &&
	    rtlpci->tx_ring[queue_index].buffer_desc_stride == 64 &&
	    append_early_mode_size == 0 && pkt_len >= 24) {
		const u8 *frame = skb->data;
		__le16 frame_control = cpu_to_le16(get_unaligned_le16(frame));

		if (ieee80211_is_data(frame_control)) {
			split_header_len = ieee80211_hdrlen(frame_control);
			/* OEM hdrLen includes LLC.  mac80211 Ethernet data normally
			 * carries an RFC1042/802.1H SNAP header immediately after the
			 * 802.11 header; keep those eight bytes in TXBD element 1.
			 */
			if (pkt_len >= split_header_len + 8 &&
			    frame[split_header_len] == 0xaa &&
			    frame[split_header_len + 1] == 0xaa &&
			    frame[split_header_len + 2] == 0x03)
				split_header_len += 8;
			split_be_data = split_header_len >= 24 &&
					split_header_len < pkt_len;
		}
	}

	if (tx_page_size > 0) {
		psblen = (pkt_len + real_desc_size + append_early_mode_size) /
			 (tx_page_size * 128);

		if (psblen * (tx_page_size * 128) < total_packet_size)
			psblen += 1;
	}

	/* tx desc addr */
	desc_dma_addr = rtlpci->tx_ring[queue_index].dma +
			(current_bd_desc * TX_DESC_SIZE);
	if (compact32) {
		const u8 *frame = skb->data + append_early_mode_size;
		__le16 frame_control = 0;
		u16 header_len = 0;
		bool split_mgmt = false;

		/* OEM DMA32 layout: four 8-byte segments in one 0x20-byte TXBD.
		 * Segment 0 points at the 0x28-byte TX descriptor. The vendor AP
		 * path uses segment 1 for the 802.11 header and segment 2 for the
		 * remaining body; preserve that split for management frames when
		 * explicitly enabled. Other traffic keeps the proven single-buffer
		 * layout while this A/B remains diagnostic.
		 */
		memset(tx_bd_desc, 0, 32);
		clear_pci_tx_desc_content(desc, TX_DESC_SIZE);
		set_tx_buff_desc_len_0(tx_bd_desc,
			desc_size + (rtlpriv->rtlhal.earlymode_enable &&
				     queue_index < BEACON_QUEUE ? 8 : 0));
		set_tx_buff_desc_psb(tx_bd_desc, psblen);
		set_tx_buff_desc_own(tx_bd_desc, 0);
		tx_bd_desc[1] = cpu_to_le32((u32)desc_dma_addr);
		if (hgw500_txbd_mgmt_split &&
		    of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
		    append_early_mode_size == 0 && pkt_len >= 24) {
			frame_control = cpu_to_le16(get_unaligned_le16(frame));
			header_len = ieee80211_hdrlen(frame_control);
			split_mgmt = (ieee80211_is_auth(frame_control) ||
				ieee80211_is_assoc_resp(frame_control) ||
				ieee80211_is_reassoc_resp(frame_control) ||
				ieee80211_is_deauth(frame_control) ||
				ieee80211_is_disassoc(frame_control)) &&
				header_len >= 24 && header_len < pkt_len;
		}
		if (split_mgmt) {
			tx_bd_desc[2] = cpu_to_le32(header_len);
			tx_bd_desc[3] = cpu_to_le32((u32)addr);
			tx_bd_desc[4] = cpu_to_le32(pkt_len - header_len);
			tx_bd_desc[5] = cpu_to_le32((u32)addr + header_len);
			pr_info_ratelimited("OMRTLTX16 stage=mgmt-reply-txbd-split q=%u len=%u hdr=%u body=%u\n",
					    queue_index, pkt_len, header_len,
					    pkt_len - header_len);
		} else {
			tx_bd_desc[2] = cpu_to_le32(pkt_len);
			tx_bd_desc[3] = cpu_to_le32((u32)addr);
		}
		set_tx_desc_pkt_size(desc, (u16)pkt_len);
		set_tx_desc_tx_buffer_size(desc, (u16)pkt_len);
		return;
	}

	/* Reset */
	set_tx_buff_desc_len_0(tx_bd_desc, 0);
	set_tx_buff_desc_psb(tx_bd_desc, 0);
	set_tx_buff_desc_own(tx_bd_desc, 0);

	for (i = 1; i < segmentnum; i++) {
		set_txbuffer_desc_len_with_offset(tx_bd_desc, i, 0);
		set_txbuffer_desc_amsdu_with_offset(tx_bd_desc, i, 0);
		set_txbuffer_desc_add_low_with_offset(tx_bd_desc, i, 0);
		set_txbuffer_desc_add_high_with_offset(tx_bd_desc, i, 0, dma64);
	}

	/* Clear all status */
	clear_pci_tx_desc_content(desc, TX_DESC_SIZE);

	if (rtlpriv->rtlhal.earlymode_enable) {
		if (queue_index < BEACON_QUEUE) {
			/* This if needs braces */
			set_tx_buff_desc_len_0(tx_bd_desc, desc_size + 8);
		} else {
			set_tx_buff_desc_len_0(tx_bd_desc, desc_size);
		}
	} else {
		set_tx_buff_desc_len_0(tx_bd_desc, desc_size);
	}
	set_tx_buff_desc_psb(tx_bd_desc, psblen);
	set_tx_buff_desc_addr_low_0(tx_bd_desc, desc_dma_addr);
	set_tx_buff_desc_addr_high_0(tx_bd_desc, ((u64)desc_dma_addr >> 32),
				     dma64);

	if (split_be_data) {
		set_txbuffer_desc_len_with_offset(tx_bd_desc, 1,
					       split_header_len);
		set_txbuffer_desc_amsdu_with_offset(tx_bd_desc, 1, 0);
		set_txbuffer_desc_add_low_with_offset(tx_bd_desc, 1, addr);
		set_txbuffer_desc_add_high_with_offset(tx_bd_desc, 1,
					       ((u64)addr >> 32), dma64);
		set_txbuffer_desc_len_with_offset(tx_bd_desc, 2,
					       pkt_len - split_header_len);
		set_txbuffer_desc_amsdu_with_offset(tx_bd_desc, 2, 0);
		set_txbuffer_desc_add_low_with_offset(tx_bd_desc, 2,
					       addr + split_header_len);
		set_txbuffer_desc_add_high_with_offset(tx_bd_desc, 2,
					       ((u64)(addr + split_header_len) >> 32),
					       dma64);
		pr_info_once("OMRTLTXBD stage=be-data-split target=hgw500 q=%u hdr_llc=%u body=%u stride=64\n",
			     queue_index, split_header_len,
			     pkt_len - split_header_len);
	} else {
		set_txbuffer_desc_len_with_offset(tx_bd_desc, 1, pkt_len);
		/* don't using extendsion mode. */
		set_txbuffer_desc_amsdu_with_offset(tx_bd_desc, 1, 0);
		set_txbuffer_desc_add_low_with_offset(tx_bd_desc, 1, addr);
		set_txbuffer_desc_add_high_with_offset(tx_bd_desc, 1,
					       ((u64)addr >> 32), dma64);
	}

	set_tx_desc_pkt_size(desc, (u16)(pkt_len));
	set_tx_desc_tx_buffer_size(desc, (u16)(pkt_len));
}

void rtl92ee_tx_fill_desc(struct ieee80211_hw *hw,
			  struct ieee80211_hdr *hdr, u8 *pdesc8,
			  u8 *pbd_desc_tx,
			  struct ieee80211_tx_info *info,
			  struct ieee80211_sta *sta,
			  struct sk_buff *skb,
			  u8 hw_queue, struct rtl_tcb_desc *ptcb_desc)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_mac *mac = rtl_mac(rtl_priv(hw));
	struct rtl_pci *rtlpci = rtl_pcidev(rtl_pcipriv(hw));
	struct rtl_hal *rtlhal = rtl_hal(rtlpriv);
	struct rtlwifi_tx_info *tx_info = rtl_tx_skb_cb_info(skb);
	u16 seq_number;
	__le16 fc = hdr->frame_control;
	const u8 *frame = (const u8 *)hdr;
	u8 fw_qsel = _rtl92ee_map_hwqueue_to_fwqueue(skb, hw_queue);
	bool firstseg = ((hdr->seq_ctrl &
			    cpu_to_le16(IEEE80211_SCTL_FRAG)) == 0);
	bool lastseg = ((hdr->frame_control &
			   cpu_to_le16(IEEE80211_FCTL_MOREFRAGS)) == 0);
	u8 hgw500_forced_mgmt_rate = 0;
	dma_addr_t mapping;
	u8 bw_40 = 0;
	__le32 *pdesc = (__le32 *)pdesc8;

	if (mac->opmode == NL80211_IFTYPE_STATION) {
		bw_40 = mac->bw_40;
	} else if (mac->opmode == NL80211_IFTYPE_AP ||
		   mac->opmode == NL80211_IFTYPE_ADHOC) {
		if (sta)
			bw_40 = sta->deflink.ht_cap.cap &
				IEEE80211_HT_CAP_SUP_WIDTH_20_40;
	}
	seq_number = (le16_to_cpu(hdr->seq_ctrl) & IEEE80211_SCTL_SEQ) >> 4;
	rtl_get_tcb_desc(hw, info, sta, skb, ptcb_desc);
	/* reserve 8 byte for AMPDU early mode */
	if (rtlhal->earlymode_enable) {
		skb_push(skb, EM_HDR_LEN);
		memset(skb->data, 0, EM_HDR_LEN);
	}
	mapping = dma_map_single(&rtlpci->pdev->dev, skb->data, skb->len,
				 DMA_TO_DEVICE);
	if (dma_mapping_error(&rtlpci->pdev->dev, mapping)) {
		rtl_dbg(rtlpriv, COMP_SEND, DBG_TRACE,
			"DMA mapping error\n");
		return;
	}

	if (pbd_desc_tx != NULL)
		rtl92ee_pre_fill_tx_bd_desc(hw, pbd_desc_tx, pdesc8, hw_queue,
					    skb, mapping);

	if (ieee80211_is_nullfunc(fc) || ieee80211_is_ctl(fc)) {
		firstseg = true;
		lastseg = true;
	}
	if (firstseg) {
		if (rtlhal->earlymode_enable) {
			set_tx_desc_pkt_offset(pdesc, 1);
			set_tx_desc_offset(pdesc,
					   USB_HWDESC_HEADER_LEN + EM_HDR_LEN);
			if (ptcb_desc->empkt_num) {
				rtl_dbg(rtlpriv, COMP_SEND, DBG_TRACE,
					"Insert 8 byte.pTcb->EMPktNum:%d\n",
					ptcb_desc->empkt_num);
				_rtl92ee_insert_emcontent(ptcb_desc,
							  (u8 *)(skb->data));
			}
		} else {
			set_tx_desc_offset(pdesc, USB_HWDESC_HEADER_LEN);
		}


		set_tx_desc_tx_rate(pdesc, ptcb_desc->hw_rate);

		if (ieee80211_is_mgmt(fc)) {
			ptcb_desc->use_driver_rate = true;
			if (of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
			    rtl92ee_hgw500_mgmt_reply_desc_rate(
				    fc, &hgw500_forced_mgmt_rate)) {
				ptcb_desc->hw_rate = hgw500_forced_mgmt_rate;
				ptcb_desc->disable_ratefallback = false;
				ptcb_desc->packet_bw = HT_CHANNEL_WIDTH_20;
				ptcb_desc->use_shortgi = false;
				set_tx_desc_tx_rate(pdesc, ptcb_desc->hw_rate);
				pr_info_ratelimited("OMRTLMGMT stage=force-reply-rate type=%s rate=%u desc_rate=%u fallback=1\n",
						    rtl92ee_mgmt_subtype_name(fc),
						    hgw500_mgmt_reply_rate,
						    ptcb_desc->hw_rate);
			}
		} else {
			if (rtlpriv->ra.is_special_data) {
				ptcb_desc->use_driver_rate = true;
				set_tx_desc_tx_rate(pdesc, DESC_RATE11M);
			} else {
				ptcb_desc->use_driver_rate = false;
			}
		}
		if (hgw500_force_data_mcs7 &&
		    of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
		    sta && ieee80211_is_data(fc) &&
		    !rtlpriv->ra.is_special_data &&
		    !is_multicast_ether_addr(ieee80211_get_DA(hdr))) {
			ptcb_desc->hw_rate = DESC_RATEMCS7;
			ptcb_desc->packet_bw = HT_CHANNEL_WIDTH_20;
			ptcb_desc->use_shortgi = false;
			ptcb_desc->use_driver_rate = true;
			ptcb_desc->disable_ratefallback = true;
			set_tx_desc_tx_rate(pdesc, ptcb_desc->hw_rate);
			pr_info_once("OMRTLRA stage=force-data-rate target=hgw500 rate=MCS7 nss=1 fallback=0 dis_fb=1 pkt_bw=20 shortgi=0\n");
		} else if (hgw500_force_data_11m &&
		    of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
		    sta && ieee80211_is_data(fc) &&
		    !rtlpriv->ra.is_special_data &&
		    !is_multicast_ether_addr(ieee80211_get_DA(hdr))) {
			ptcb_desc->use_driver_rate = true;
			ptcb_desc->disable_ratefallback = false;
			set_tx_desc_tx_rate(pdesc, DESC_RATE11M);
			pr_info_once("OMRTL92 stage=force-data-rate target=hgw500 rate=11M\n");
		}
		else if (hgw500_force_data_mcs15 &&
		    of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
		    sta && ieee80211_is_data(fc) &&
		    !rtlpriv->ra.is_special_data &&
		    !is_multicast_ether_addr(ieee80211_get_DA(hdr))) {
			ptcb_desc->use_driver_rate = true;
			ptcb_desc->disable_ratefallback = false;
			if (hgw500_force_data_ht40sgi && bw_40) {
				ptcb_desc->packet_bw = HT_CHANNEL_WIDTH_20_40;
				ptcb_desc->use_shortgi =
					!!(sta->ht_cap.cap & IEEE80211_HT_CAP_SGI_40);
			}
			set_tx_desc_tx_rate(pdesc, DESC_RATEMCS15);
			pr_info_once("OMRTLRA stage=force-data-rate target=hgw500 rate=MCS15 fallback=1 ht40sgi=%u pkt_bw=%u shortgi=%u bw40=%u\n",
				     hgw500_force_data_ht40sgi,
				     ptcb_desc->packet_bw,
				     ptcb_desc->use_shortgi, bw_40);
		}

		if (info->flags & IEEE80211_TX_CTL_AMPDU) {
			set_tx_desc_agg_enable(pdesc, 1);
			set_tx_desc_max_agg_num(pdesc, 0x14);
		}
		set_tx_desc_seq(pdesc, seq_number);
		set_tx_desc_rts_enable(pdesc,
				       ((ptcb_desc->rts_enable &&
					 !ptcb_desc->cts_enable) ? 1 : 0));
		set_tx_desc_hw_rts_enable(pdesc, 0);
		set_tx_desc_cts2self(pdesc,
				     ((ptcb_desc->cts_enable) ? 1 : 0));

		set_tx_desc_rts_rate(pdesc, ptcb_desc->rts_rate);
		set_tx_desc_rts_sc(pdesc, ptcb_desc->rts_sc);
		set_tx_desc_rts_short(pdesc,
				((ptcb_desc->rts_rate <= DESC_RATE54M) ?
				 (ptcb_desc->rts_use_shortpreamble ? 1 : 0) :
				 (ptcb_desc->rts_use_shortgi ? 1 : 0)));

		if (ptcb_desc->tx_enable_sw_calc_duration)
			set_tx_desc_nav_use_hdr(pdesc, 1);

		if (bw_40) {
			if (ptcb_desc->packet_bw == HT_CHANNEL_WIDTH_20_40) {
				set_tx_desc_data_bw(pdesc, 1);
				set_tx_desc_tx_sub_carrier(pdesc, 3);
			} else {
				set_tx_desc_data_bw(pdesc, 0);
				set_tx_desc_tx_sub_carrier(pdesc,
							   mac->cur_40_prime_sc);
			}
		} else {
			set_tx_desc_data_bw(pdesc, 0);
			set_tx_desc_tx_sub_carrier(pdesc, 0);
		}
		set_tx_desc_shortgi(pdesc, ptcb_desc->use_shortgi ? 1 : 0);

		set_tx_desc_linip(pdesc, 0);
		if (sta) {
			u8 ampdu_density = sta->deflink.ht_cap.ampdu_density;

			set_tx_desc_ampdu_density(pdesc, ampdu_density);
		}
		if (info->control.hw_key) {
			struct ieee80211_key_conf *key = info->control.hw_key;

			switch (key->cipher) {
			case WLAN_CIPHER_SUITE_WEP40:
			case WLAN_CIPHER_SUITE_WEP104:
			case WLAN_CIPHER_SUITE_TKIP:
				set_tx_desc_sec_type(pdesc, 0x1);
				break;
			case WLAN_CIPHER_SUITE_CCMP:
				set_tx_desc_sec_type(pdesc, 0x3);
				break;
			default:
				set_tx_desc_sec_type(pdesc, 0x0);
				break;
			}
		}

		set_tx_desc_queue_sel(pdesc, fw_qsel);
		set_tx_desc_data_rate_fb_limit(pdesc, 0x1F);
		set_tx_desc_rts_rate_fb_limit(pdesc, 0xF);
		set_tx_desc_disable_fb(pdesc,
				       ptcb_desc->disable_ratefallback ? 1 : 0);
		set_tx_desc_use_rate(pdesc, ptcb_desc->use_driver_rate ? 1 : 0);

		/*set_tx_desc_pwr_status(pdesc, pwr_status);*/
		/* Set TxRate and RTSRate in TxDesc  */
		/* This prevent Tx initial rate of new-coming packets */
		/* from being overwritten by retried  packet rate.*/
		if (!ptcb_desc->use_driver_rate) {
			/*set_tx_desc_rts_rate(pdesc, 0x08); */
			/* set_tx_desc_tx_rate(pdesc, 0x0b); */
		}
		if (ieee80211_is_data_qos(fc)) {
			if (mac->rdg_en) {
				rtl_dbg(rtlpriv, COMP_SEND, DBG_TRACE,
					"Enable RDG function.\n");
				set_tx_desc_rdg_enable(pdesc, 1);
				set_tx_desc_htc(pdesc, 1);
			}
		}
		/* tx report */
		rtl_set_tx_report(ptcb_desc, pdesc8, hw, tx_info);
	}

	set_tx_desc_first_seg(pdesc, (firstseg ? 1 : 0));
	set_tx_desc_last_seg(pdesc, (lastseg ? 1 : 0));
	set_tx_desc_tx_buffer_address(pdesc, mapping);
	if (rtlpriv->dm.useramask) {
		set_tx_desc_rate_id(pdesc, ptcb_desc->ratr_index);
		set_tx_desc_macid(pdesc, ptcb_desc->mac_id);
	} else {
		set_tx_desc_rate_id(pdesc, 0xC + ptcb_desc->ratr_index);
		set_tx_desc_macid(pdesc, ptcb_desc->ratr_index);
	}

	set_tx_desc_more_frag(pdesc, (lastseg ? 0 : 1));
	if (is_multicast_ether_addr(ieee80211_get_DA(hdr)) ||
	    is_broadcast_ether_addr(ieee80211_get_DA(hdr))) {
		set_tx_desc_bmc(pdesc, 1);
	}
	if (rtl92ee_hgw500_tx_rate_trace &&
	    of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
	    hw_queue == BE_QUEUE && sta && ieee80211_is_data(fc) &&
	    !is_multicast_ether_addr(ieee80211_get_DA(hdr))) {
		static unsigned int rate_trace_count;
		unsigned int event = ++rate_trace_count;

		if (event <= 32 || is_power_of_2(event))
			pr_info("OMRTLRA stage=tx-desc event=%u len=%u tid=%u macid=%u ratr=%u hw_rate=%u use_rate=%u dis_fb=%u ampdu=%u shortgi=%u pkt_bw=%u bw40=%u qsel=%u d0=%08x d1=%08x d2=%08x d3=%08x d4=%08x d5=%08x\n",
				event, skb->len, rtl_get_tid(skb),
				ptcb_desc->mac_id, ptcb_desc->ratr_index,
				ptcb_desc->hw_rate, ptcb_desc->use_driver_rate,
				ptcb_desc->disable_ratefallback,
				!!(info->flags & IEEE80211_TX_CTL_AMPDU),
				ptcb_desc->use_shortgi, ptcb_desc->packet_bw,
				bw_40, fw_qsel,
				le32_to_cpu(pdesc[0]), le32_to_cpu(pdesc[1]),
				le32_to_cpu(pdesc[2]), le32_to_cpu(pdesc[3]),
				le32_to_cpu(pdesc[4]), le32_to_cpu(pdesc[5]));
	}
	if (skb->len >= 24 &&
	    rtl92ee_hgw500_trace_mgmt_frame(hw, fc,
					    hgw500_mgmt_tx_trace_count)) {
		__le32 *txbd = (__le32 *)pbd_desc_tx;

		pr_info("OMRTLMGMT stage=tx type=%s fc=%04x len=%u q=%u qsel=%u seq=%u hw_rate=%u use_driver_rate=%u data_bw=%u sta=%u da=%pM sa=%pM bssid=%pM body0=%04x body1=%04x body2=%04x d0=%08x d1=%08x d2=%08x d3=%08x d7=%08x b0=%08x b1=%08x b2=%08x b3=%08x b4=%08x b5=%08x\n",
			rtl92ee_mgmt_subtype_name(fc), le16_to_cpu(fc),
			skb->len, hw_queue, fw_qsel, seq_number,
			ptcb_desc->hw_rate, ptcb_desc->use_driver_rate,
			bw_40, !!sta, frame + 4, frame + 10, frame + 16,
			skb->len >= 30 ? get_unaligned_le16(frame + 24) : 0,
			skb->len >= 30 ? get_unaligned_le16(frame + 26) : 0,
			skb->len >= 30 ? get_unaligned_le16(frame + 28) : 0,
			le32_to_cpu(pdesc[0]), le32_to_cpu(pdesc[1]),
			le32_to_cpu(pdesc[2]), le32_to_cpu(pdesc[3]),
			le32_to_cpu(pdesc[7]),
			txbd ? le32_to_cpu(txbd[0]) : 0,
			txbd ? le32_to_cpu(txbd[1]) : 0,
			txbd ? le32_to_cpu(txbd[2]) : 0,
			txbd ? le32_to_cpu(txbd[3]) : 0,
			txbd && rtlpci->tx_ring[hw_queue].buffer_desc_stride >= 24 ? le32_to_cpu(txbd[4]) : 0,
			txbd && rtlpci->tx_ring[hw_queue].buffer_desc_stride >= 24 ? le32_to_cpu(txbd[5]) : 0);
	}
	rtl_dbg(rtlpriv, COMP_SEND, DBG_TRACE, "\n");
}

void rtl92ee_tx_fill_cmddesc(struct ieee80211_hw *hw, u8 *pdesc8,
			     struct sk_buff *skb)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_pci *rtlpci = rtl_pcidev(rtl_pcipriv(hw));
	u8 fw_queue = QSLT_BEACON;
	dma_addr_t mapping = dma_map_single(&rtlpci->pdev->dev, skb->data,
					    skb->len, DMA_TO_DEVICE);
	u8 txdesc_len = 40;
	__le32 *pdesc = (__le32 *)pdesc8;

	if (dma_mapping_error(&rtlpci->pdev->dev, mapping)) {
		rtl_dbg(rtlpriv, COMP_SEND, DBG_TRACE,
			"DMA mapping error\n");
		return;
	}
	clear_pci_tx_desc_content(pdesc, txdesc_len);

	set_tx_desc_offset(pdesc, txdesc_len);

	set_tx_desc_tx_rate(pdesc, DESC_RATE1M);

	set_tx_desc_seq(pdesc, 0);

	set_tx_desc_linip(pdesc, 0);

	set_tx_desc_queue_sel(pdesc, fw_queue);

	set_tx_desc_first_seg(pdesc, 1);
	set_tx_desc_last_seg(pdesc, 1);

	set_tx_desc_tx_buffer_size(pdesc, (u16)(skb->len));

	set_tx_desc_tx_buffer_address(pdesc, mapping);

	set_tx_desc_rate_id(pdesc, 7);
	set_tx_desc_macid(pdesc, 0);

	set_tx_desc_own(pdesc, 1);

	set_tx_desc_pkt_size(pdesc, (u16)(skb->len));

	set_tx_desc_first_seg(pdesc, 1);
	set_tx_desc_last_seg(pdesc, 1);

	set_tx_desc_offset(pdesc, 40);

	set_tx_desc_use_rate(pdesc, 1);

	RT_PRINT_DATA(rtlpriv, COMP_CMD, DBG_LOUD,
		      "H2C Tx Cmd Content\n", pdesc, txdesc_len);
}

void rtl92ee_set_desc(struct ieee80211_hw *hw, u8 *pdesc8, bool istx,
		      u8 desc_name, u8 *val)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u8 q_idx = *val;
	bool dma64 = rtlpriv->cfg->mod_params->dma64;
	__le32 *pdesc = (__le32 *)pdesc8;

	if (istx) {
		switch (desc_name) {
		case HW_DESC_TX_NEXTDESC_ADDR:
			set_tx_desc_next_desc_address(pdesc, *(u32 *)val);
			break;
		case HW_DESC_OWN:{
			struct rtl_pci *rtlpci = rtl_pcidev(rtl_pcipriv(hw));
			struct rtl8192_tx_ring *ring = &rtlpci->tx_ring[q_idx];
			bool tx_dma_wmb = hgw500_tx_dma_wmb &&
				of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
				rtlpriv->rtlhal.hw_type == HARDWARE_TYPE_RTL8192EE;
			u16 max_tx_desc = ring->entries;
			u16 old_wp = ring->cur_tx_wp;
			u32 desc_address = get_desc_addr_fr_q_idx(q_idx);
			static unsigned int doorbell_trace_count;
			unsigned int trace_id = ++doorbell_trace_count;
			bool trace = trace_id <= 32;

			if (trace)
				pr_info("OMRTL92 stage=tx-doorbell-pre id=%u q=%u old_wp=%u rp=%u qidx=%08x pcie=%08x himr=%08x hisr=%08x himre=%08x hisre=%08x txdma=%08x rxdma=%08x txempty=%04x trxdma=%04x\n",
					trace_id, q_idx, old_wp, ring->cur_tx_rp,
					rtl_read_dword(rtlpriv, desc_address),
					rtl_read_dword(rtlpriv, REG_PCIE_CTRL_REG),
					rtl_read_dword(rtlpriv, REG_HIMR),
					rtl_read_dword(rtlpriv, REG_HISR),
					rtl_read_dword(rtlpriv, REG_HIMRE),
					rtl_read_dword(rtlpriv, REG_HISRE),
					rtl_read_dword(rtlpriv, REG_TXDMA_STATUS),
					rtl_read_dword(rtlpriv, REG_RXDMA_STATUS),
					rtl_read_word(rtlpriv, REG_TXPKT_EMPTY),
					rtl_read_word(rtlpriv, REG_TRXDMA_CTRL));

			if (q_idx == BEACON_QUEUE) {
				ring->cur_tx_wp = 0;
				ring->cur_tx_rp = 0;
				set_tx_buff_desc_own(pdesc, 1);
				if (trace)
					pr_info("OMRTL92 stage=tx-doorbell-beacon id=%u q=%u b0=%08x\n",
						trace_id, q_idx, le32_to_cpu(pdesc[0]));
				return;
			}

			/* make sure tx desc is available by caller */
			ring->cur_tx_wp = ((ring->cur_tx_wp + 1) % max_tx_desc);

			if (tx_dma_wmb) {
				pr_info_once("OMRTLTX1 stage=publish-barrier-active target=hgw500 rtl8192ee=1 dma64=%u\n",
					     dma64);
				dma_wmb();
			}
			rtl_write_word(rtlpriv, desc_address, ring->cur_tx_wp);
			if (trace)
				pr_info("OMRTL92 stage=tx-doorbell-post id=%u q=%u old_wp=%u new_wp=%u rp=%u qidx=%08x pcie=%08x himr=%08x hisr=%08x himre=%08x hisre=%08x txdma=%08x rxdma=%08x txempty=%04x trxdma=%04x\n",
					trace_id, q_idx, old_wp, ring->cur_tx_wp,
					ring->cur_tx_rp,
					rtl_read_dword(rtlpriv, desc_address),
					rtl_read_dword(rtlpriv, REG_PCIE_CTRL_REG),
					rtl_read_dword(rtlpriv, REG_HIMR),
					rtl_read_dword(rtlpriv, REG_HISR),
					rtl_read_dword(rtlpriv, REG_HIMRE),
					rtl_read_dword(rtlpriv, REG_HISRE),
					rtl_read_dword(rtlpriv, REG_TXDMA_STATUS),
					rtl_read_dword(rtlpriv, REG_RXDMA_STATUS),
					rtl_read_word(rtlpriv, REG_TXPKT_EMPTY),
					rtl_read_word(rtlpriv, REG_TRXDMA_CTRL));
		}
		break;
		}
	} else {
		switch (desc_name) {
		case HW_DESC_RX_PREPARE:
			set_rx_buffer_desc_ls(pdesc, 0);
			set_rx_buffer_desc_fs(pdesc, 0);
			set_rx_buffer_desc_total_length(pdesc, 0);

			set_rx_buffer_desc_data_length(pdesc,
						       MAX_RECEIVE_BUFFER_SIZE +
						       RX_DESC_SIZE);

			set_rx_buffer_physical_low(pdesc, (*(dma_addr_t *)val) &
						   DMA_BIT_MASK(32));
			set_rx_buffer_physical_high(pdesc,
						    ((u64)(*(dma_addr_t *)val)
						    >> 32),
						    dma64);
			break;
		case HW_DESC_RXERO:
			set_rx_desc_eor(pdesc, 1);
			break;
		default:
			WARN_ONCE(true,
				  "rtl8192ee: ERR rxdesc :%d not processed\n",
				  desc_name);
			break;
		}
	}
}

u64 rtl92ee_get_desc(struct ieee80211_hw *hw,
		     u8 *pdesc8, bool istx, u8 desc_name)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u64 ret = 0;
	bool dma64 = rtlpriv->cfg->mod_params->dma64;
	__le32 *pdesc = (__le32 *)pdesc8;

	if (istx) {
		switch (desc_name) {
		case HW_DESC_OWN:
			ret = get_tx_desc_own(pdesc);
			break;
		case HW_DESC_TXBUFF_ADDR:
			ret = get_txbuffer_desc_addr_low(pdesc, 1);
			ret |= (u64)get_txbuffer_desc_addr_high(pdesc, 1,
								dma64) << 32;
			break;
		default:
			WARN_ONCE(true,
				  "rtl8192ee: ERR txdesc :%d not processed\n",
				  desc_name);
			break;
		}
	} else {
		switch (desc_name) {
		case HW_DESC_OWN:
			ret = get_rx_desc_own(pdesc);
			break;
		case HW_DESC_RXPKT_LEN:
			ret = get_rx_desc_pkt_len(pdesc);
			break;
		case HW_DESC_RXBUFF_ADDR:
			ret = get_rx_desc_buff_addr(pdesc);
			break;
		default:
			WARN_ONCE(true,
				  "rtl8192ee: ERR rxdesc :%d not processed\n",
				  desc_name);
			break;
		}
	}
	return ret;
}

bool rtl92ee_is_tx_desc_closed(struct ieee80211_hw *hw, u8 hw_queue, u16 index)
{
	struct rtl_pci *rtlpci = rtl_pcidev(rtl_pcipriv(hw));
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	u16 read_point, write_point;
	u16 hw_write_point;
	u32 qidx;
	bool ret = false;
	static unsigned int close_diag_count;
	static unsigned int close_diag_max_queued;
	struct rtl8192_tx_ring *ring = &rtlpci->tx_ring[hw_queue];

	{
		u16 cur_tx_rp;

		qidx =
		  rtl_read_dword(rtlpriv,
				 get_desc_addr_fr_q_idx(hw_queue));
		cur_tx_rp = (u16)((qidx >> 16) & 0x0fff);

		/* don't need to update ring->cur_tx_wp */
		ring->cur_tx_rp = cur_tx_rp;
	}

	read_point = ring->cur_tx_rp;
	write_point = ring->cur_tx_wp;
	hw_write_point = (u16)(qidx & 0x0fff);

	/* OEM SyncSWTXBDHostIdxToHW88XX/tx_recycle semantics: HW RP is
	 * the next descriptor still owned by hardware. index == HW RP is not
	 * reclaimable, including the full-minus-one state WP == RP - 1.
	 */
	if (write_point > read_point) {
		if (index < write_point && index >= read_point)
			ret = false;
		else
			ret = true;
	} else if (write_point < read_point) {
		if (index > write_point && index < read_point)
			ret = true;
		else
			ret = false;
	} else {
		if (index != read_point)
			ret = true;
	}

	if (hw_queue == BEACON_QUEUE)
		ret = true;

	if (rtlpriv->rtlhal.driver_is_goingto_unload ||
	    rtlpriv->psc.rfoff_reason > RF_CHANGE_BY_PS)
		ret = true;

	if (hw_queue < BEACON_QUEUE) {
		if (!ret)
			stop_report_cnt++;
		else
			stop_report_cnt = 0;
	}

	if (hgw500_tx_close_diag &&
	    of_machine_is_compatible("mitrastar,hgw-500bna-qcv2") &&
	    hw_queue == BE_QUEUE && !ret) {
		unsigned int trace_id = ++close_diag_count;
		u32 desc0 = le32_to_cpu(ring->desc[index].dword[0]);
		u32 bd0 = rtlpriv->use_new_trx_flow ?
			le32_to_cpu(((__le32 *)rtl_pci_txbd_entry(ring, index))[0]) : 0;
		unsigned int queued = skb_queue_len(&ring->queue);
		bool high_water_edge = queued > close_diag_max_queued &&
			queued >= ring->entries - 2;

		if (queued > close_diag_max_queued)
			close_diag_max_queued = queued;
		if (trace_id <= 16 || is_power_of_2(trace_id) || high_water_edge)
			pr_info("OMRTLTXCLOSE id=%u q=%u index=%u sw_rp=%u sw_wp=%u hw_rp=%u hw_wp=%u entries=%u queued=%u desc_own=%u bd_own=%u qidx=%08x closed=0\n",
				trace_id, hw_queue, index, read_point,
				write_point, read_point, hw_write_point,
				ring->entries, queued, desc0 >> 31,
				bd0 >> 31, qidx);
	}

	return ret;
}

void rtl92ee_tx_polling(struct ieee80211_hw *hw, u8 hw_queue)
{
	struct rtl_priv *rtlpriv = rtl_priv(hw);
	struct rtl_pci *rtlpci = rtl_pcidev(rtl_pcipriv(hw));
	struct rtl8192_tx_ring *ring = &rtlpci->tx_ring[hw_queue];
	u32 desc_address = get_desc_addr_fr_q_idx(hw_queue);
	static unsigned int poll_trace_count;
	static unsigned int beacon_trigger_count;
	unsigned int trace_id = ++poll_trace_count;
	bool trace = trace_id <= 32;

	/* The 92EE new-flow queues ring their index register from set_desc(),
	 * except BCNQ: its fixed descriptor 0 is downloaded by PCIe poll bit 4.
	 */
	if (hw_queue == BEACON_QUEUE &&
	    rtlpci->irq_line_lifecycle_managed) {
		unsigned int trigger_id = ++beacon_trigger_count;

		rtl_write_word(rtlpriv, REG_PCIE_CTRL_REG, BIT(4));
		if (trigger_id <= 8)
			pr_info("OMRTL92 stage=tx-poll-beacon-trigger id=%u pcie=%08x\n",
				trigger_id,
				rtl_read_dword(rtlpriv, REG_PCIE_CTRL_REG));
	}

	if (!trace)
		return;

	pr_info("OMRTL92 stage=tx-poll-enter id=%u q=%u wp=%u rp=%u qidx=%08x pcie=%08x hisr=%08x hisre=%08x txdma=%08x rxdma=%08x txempty=%04x\n",
		trace_id, hw_queue, ring->cur_tx_wp, ring->cur_tx_rp,
		rtl_read_dword(rtlpriv, desc_address),
		rtl_read_dword(rtlpriv, REG_PCIE_CTRL_REG),
		rtl_read_dword(rtlpriv, REG_HISR),
		rtl_read_dword(rtlpriv, REG_HISRE),
		rtl_read_dword(rtlpriv, REG_TXDMA_STATUS),
		rtl_read_dword(rtlpriv, REG_RXDMA_STATUS),
		rtl_read_word(rtlpriv, REG_TXPKT_EMPTY));
	pr_info("OMRTL92 stage=tx-poll-exit id=%u q=%u wp=%u rp=%u qidx=%08x pcie=%08x hisr=%08x hisre=%08x txdma=%08x rxdma=%08x txempty=%04x\n",
		trace_id, hw_queue, ring->cur_tx_wp, ring->cur_tx_rp,
		rtl_read_dword(rtlpriv, desc_address),
		rtl_read_dword(rtlpriv, REG_PCIE_CTRL_REG),
		rtl_read_dword(rtlpriv, REG_HISR),
		rtl_read_dword(rtlpriv, REG_HISRE),
		rtl_read_dword(rtlpriv, REG_TXDMA_STATUS),
		rtl_read_dword(rtlpriv, REG_RXDMA_STATUS),
		rtl_read_word(rtlpriv, REG_TXPKT_EMPTY));
}
