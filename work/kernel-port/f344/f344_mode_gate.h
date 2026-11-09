/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F344_MODE_GATE_H
#define F344_MODE_GATE_H
#ifdef __KERNEL__
#include <linux/types.h>
#else
#include <stdbool.h>
#endif
enum f344_mode {F344_MODE_NONE=0,F344_MODE_AP=1,F344_MODE_STA=2,F344_MODE_REPEATER=3};
enum f344_vap_operation {F344_CREATE_AP0,F344_CREATE_STA0,F344_CREATE_AP1,F344_DELETE_ALL,F344_BRIDGE_CONFIG};
enum f344_gate_result {F344_GATE_OK=0,F344_GATE_UNKNOWN=-1,F344_GATE_ORDER=-2,F344_GATE_POLICY=-3};
struct f344_topology {
 bool valid,core_started,primary_present,secondary_present;
 bool csa_known,csa_pending,channel_hold,csa_drained,csa_reuse_supported;
 unsigned csa_generation,csa_readers;
 bool primary_up,secondary_up,repeater,extender;
 bool open_gate,primary_mac_matches,four_address;
 unsigned bandwidth;
 enum f344_mode primary_mode,secondary_mode;
 unsigned other_vaps;
};
/* These inputs are actual driver state copied under its existing lifecycle
 * locks. open_gate0 means future ndo_open is blocked, never RF quiescence. */
int f344_vap_admit(const struct f344_topology*,enum f344_vap_operation);
/* OEM start-prod selector interpretation. AUTO needs observed configuration
 * and lease state. This function never starts DHCP or changes management IP. */
int f344_selector_mode(unsigned selector,bool static_ip,bool lease_known,bool lease_present,enum f344_mode configured,enum f344_mode*result);
#endif
