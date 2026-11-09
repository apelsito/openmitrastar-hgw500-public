/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F344_TRANSACTION_H
#define F344_TRANSACTION_H
#include "f344_mode_gate.h"
#include <stdbool.h>
#include <stdint.h>
#define F344_SNAPSHOT_VALID 0x7fU
#define F344_VALID_MANAGEMENT 4U
/* No credentials are put in the public state. The backend retains complete
 * private daemon profiles under snapshot_cookie, tied to process identity. */
struct f344_state {
  uint32_t valid, snapshot_cookie;
  enum f344_mode mode;
  struct f344_topology topology;
  uint8_t channel_mask[32], management_digest[32], profile_digest[32];
  uint8_t primary_mac[6], secondary_mac[6];
  unsigned frequency_mhz, bandwidth, configured_bandwidth;
  bool ap_enabled, upstream_completed, primary_bridged, secondary_bridged;
  bool three_address_bridge, four_address_negotiated;
};
struct f344_target {
  enum f344_mode mode;
  unsigned ap_frequency_mhz, bandwidth;
  uint8_t channel_mask[32], profile_digest[32];
  uint32_t profile_cookie;
};
enum f344_action {
  F344_GUARD_MANAGEMENT,
  F344_STOP_SECURITY,
  F344_DOWN_VAPS,
  F344_CLOSE_OPEN_GATE,
  F344_DRAIN_CSA,
  F344_DETACH_WIFI,
  F344_REPEATER_CLEAR,
  F344_DELETE_VAPS,
  F344_CREATE_PRIMARY,
  F344_SET_CHANNEL_POLICY,
  F344_REPEATER_ENABLE,
  F344_CREATE_SECONDARY,
  F344_SET_BRIDGE_POLICY,
  F344_ATTACH_WIFI,
  F344_CONFIGURE_SECURITY,
  F344_OPEN_GATE,
  F344_START_SECURITY
};
enum f344_outcome {
  F344_REJECTED,
  F344_UNCHANGED,
  F344_APPLIED_READBACK,
  F344_ROLLED_BACK_READBACK,
  F344_ROLLBACK_FAILED
};
struct f344_result {
  enum f344_outcome outcome;
  unsigned actions, rollback_actions;
  int error;
  bool traffic_verified;
};
struct f344_ops {
  void *context;
  int (*snapshot)(void *, struct f344_state *);
  int (*inspect)(void *, struct f344_state *);
  int (*execute)(void *, enum f344_action, const struct f344_target *,
                 const struct f344_state *, bool rollback);
  /* Wait is bounded by the caller's absolute watchdog-protected transaction
   * deadline. It must return actual fresh daemon/driver/bridge observations. */
  int (*wait_target)(void *, const struct f344_target *, struct f344_state *);
};
int f344_apply(const struct f344_ops *, const struct f344_target *,
               struct f344_result *);
int f344_channel_encode(const uint8_t actual_mask[32], unsigned input_offset,
                        uint8_t setter_mask[32]);
bool f344_mask_non_dfs(const uint8_t mask[32]);
bool f344_target_observed(const struct f344_target *,
                          const struct f344_state *);
#endif
