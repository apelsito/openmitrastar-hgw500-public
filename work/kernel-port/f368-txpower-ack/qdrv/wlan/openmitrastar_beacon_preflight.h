#ifndef OPENMITRASTAR_BEACON_PREFLIGHT_H
#define OPENMITRASTAR_BEACON_PREFLIGHT_H

#include <linux/types.h>

struct sk_buff;
struct ieee80211_beacon_param_t;

enum om_beacon_preflight_reason {
	OM_BEACON_PREFLIGHT_OK = 0,
	OM_BEACON_PREFLIGHT_PARAM,
	OM_BEACON_PREFLIGHT_HEAD,
	OM_BEACON_PREFLIGHT_DESCRIPTOR,
	OM_BEACON_PREFLIGHT_CYCLE,
	OM_BEACON_PREFLIGHT_SIZE,
	OM_BEACON_PREFLIGHT_BUFFER,
	OM_BEACON_PREFLIGHT_BUFFER_DMA,
	OM_BEACON_PREFLIGHT_NEXT_DMA,
	OM_BEACON_PREFLIGHT_TOTAL,
	OM_BEACON_PREFLIGHT_TAIL,
};

struct om_beacon_preflight_report {
	u32 reason;
	u32 index;
	u32 count;
	u32 total;
	u32 used;
};

int om_ieee80211_beacon_preflight(struct ieee80211_beacon_param_t *param,
		struct sk_buff *skb, struct om_beacon_preflight_report *report);
int om_ieee80211_beacon_prepare_v89_wire(
		struct ieee80211_beacon_param_t *param, struct sk_buff *skb,
		u32 *head_wire, struct om_beacon_preflight_report *report);

#endif
