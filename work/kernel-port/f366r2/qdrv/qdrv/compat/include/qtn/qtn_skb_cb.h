#ifndef __QTN_SKB_CB_H
#define __QTN_SKB_CB_H

#include <linux/openmitrastar_qtn_skb.h>

#define QTN_SKB_ALLOC_TRACE 0
#define QTN_SKB_ALLOC_TRACE_ARGNAMES(file, func, line)
#define QTN_SKB_ALLOC_TRACE_ARGS
#define QTN_SKB_ALLOC_TRACE_ARGVARS
#define QTN_SKB_ALLOC_TRACE_ARGSRC

#define QTN_SKB_ENCAP_ETH 0
#define QTN_SKB_ENCAP_80211_MGMT 1
#define QTN_SKB_ENCAP_80211_DATA 2
#define QTN_SKB_ENCAP(skb) ((skb)->qtn_cb.encap)
#define QTN_SKB_ENCAP_IS_80211(skb) ((skb)->qtn_cb.encap > 0)
#define QTN_SKB_ENCAP_IS_80211_MGMT(skb) \
	((skb)->qtn_cb.encap == QTN_SKB_ENCAP_80211_MGMT)

#define QTN_SKB_CB_NI(skb) ((skb)->qtn_cb.ni)
#define QTN_SKB_CB_ETHERTYPE(skb) ((skb)->qtn_cb.ether_type)
#define QTN_SKB_CB_IPPROTO(skb) ((skb)->qtn_cb.ip_protocol)

#define M_LINK0 0x0001
#define M_FF 0x0002
#define M_PWR_SAV 0x0004
#define M_UAPSD 0x0008
#define M_RAW 0x0010
#define M_CLASSIFY 0x0020
#define M_VSP_CHK 0x0040
#define M_VSP_NOT_FOUND 0x0080
#define M_VSP_RX_BSS 0x0100
#define M_RATE_TRAINING 0x0200
#define M_NO_AMSDU 0x0400
#define M_ENQUEUED_SCH 0x0800
#define M_ENQUEUED_MUC 0x1000
#define M_TX_DONE_IMM_INT 0x2000
#define M_VLAN_TAGGED 0x4000
#define M_ORIG_OUTSIDE 0x8000
#define M_ORIG_BR 0x10000
#define M_NO_L2_LRN 0x20000

#define M_FLAG_SET(skb, flag) ((skb)->qtn_cb.flags |= (flag))
#define M_FLAG_CLR(skb, flag) ((skb)->qtn_cb.flags &= ~(flag))
#define M_FLAG_GET(skb, flag) ((skb)->qtn_cb.flags & (flag))
#define M_FLAG_ISSET(skb, flag) (!!M_FLAG_GET((skb), (flag)))
#define M_FLAG_KEEP_ONLY(skb, flag) ((skb)->qtn_cb.flags &= (flag))
#define M_PWR_SAV_SET(skb) M_FLAG_SET((skb), M_PWR_SAV)
#define M_PWR_SAV_CLR(skb) M_FLAG_CLR((skb), M_PWR_SAV)
#define M_PWR_SAV_GET(skb) M_FLAG_GET((skb), M_PWR_SAV)

#endif
