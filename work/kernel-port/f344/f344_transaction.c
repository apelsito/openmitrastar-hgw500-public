/* SPDX-License-Identifier: GPL-2.0-only */
#include "f344_transaction.h"
#include <string.h>
static unsigned bit(const uint8_t *m, unsigned n) {
  return (m[n / 8] >> (n % 8)) & 1U;
}
bool f344_mask_non_dfs(const uint8_t m[32]) {
  unsigned n, count = 0;
  if (!m)
    return false;
  for (n = 0; n < 256; n++)
    if (bit(m, n)) {
      if (n != 36 && n != 40 && n != 44 && n != 48)
        return false;
      count++;
    }
  return count != 0;
}
int f344_channel_encode(const uint8_t actual[32], unsigned offset,
                        uint8_t setter[32]) {
  unsigned n;
  if (!actual || !setter || offset > 1)
    return -1;
  memset(setter, 0, 32);
  for (n = 0; n < 256; n++)
    if (bit(actual, n)) {
      if (n < offset)
        return -1;
      setter[(n - offset) / 8] |= (uint8_t)(1U << ((n - offset) % 8));
    }
  return 0;
}
bool f344_target_observed(const struct f344_target *t,
                          const struct f344_state *s) {
  if (!t || !s || s->valid != F344_SNAPSHOT_VALID || s->mode != t->mode ||
      s->topology.extender || s->topology.other_vaps ||
      memcmp(t->profile_digest, s->profile_digest, 32) ||
      memcmp(t->channel_mask, s->channel_mask, 32) ||
      s->configured_bandwidth != t->bandwidth ||
      (s->bandwidth != 20 && s->bandwidth != 40 && s->bandwidth != 80) ||
      s->bandwidth > t->bandwidth)
    return false;
  if (!s->topology.primary_present || !s->topology.primary_up ||
      !s->primary_bridged || !s->topology.open_gate)
    return false;
  if (s->frequency_mhz < 5000 || s->frequency_mhz > 6275 ||
      (s->frequency_mhz - 5000) % 5 ||
      !bit(t->channel_mask, (s->frequency_mhz - 5000) / 5))
    return false;
  if (t->mode == F344_MODE_AP)
    return s->topology.primary_mode == F344_MODE_AP &&
           !s->topology.secondary_present && !s->topology.repeater &&
           s->ap_enabled && s->frequency_mhz == t->ap_frequency_mhz &&
           s->bandwidth == t->bandwidth;
  if (s->topology.primary_mode != F344_MODE_STA || !s->upstream_completed ||
      (!s->three_address_bridge && !s->four_address_negotiated))
    return false;
  if (t->mode == F344_MODE_STA)
    return !s->topology.secondary_present && !s->topology.repeater;
  return t->mode == F344_MODE_REPEATER && s->topology.repeater &&
         s->topology.secondary_present &&
         s->topology.secondary_mode == F344_MODE_AP &&
         s->topology.secondary_up && s->secondary_bridged && s->ap_enabled;
}
static int same_management(const struct f344_state *a,
                           const struct f344_state *b) {
  return (a->valid & F344_VALID_MANAGEMENT) &&
         (b->valid & F344_VALID_MANAGEMENT) &&
         !memcmp(a->management_digest, b->management_digest, 32);
}
static int action(const struct f344_ops *o, enum f344_action a,
                  const struct f344_target *t,
                  const struct f344_state *original, bool rollback,
                  struct f344_result *r) {
  struct f344_state observed;
  int rc;
  if (rollback)
    r->rollback_actions++;
  else
    r->actions++;
  rc = o->execute(o->context, a, t, original, rollback);
  if (rc)
    return rc;
  memset(&observed, 0, sizeof(observed));
  rc = o->inspect(o->context, &observed);
  if (rc)
    return rc;
  /* Restoration is allowed to repair an intermediate bridge identity change;
   * only the final restored observation may confer rollback success. */
  return rollback || same_management(original, &observed) ? 0 : -4;
}
static int perform(const struct f344_ops *o, const struct f344_target *t,
                   const struct f344_state *original, bool rollback,
                   struct f344_result *r, struct f344_state *observed) {
  static const enum f344_action dismantle[] = {
      F344_GUARD_MANAGEMENT, F344_STOP_SECURITY, F344_DOWN_VAPS,
      F344_CLOSE_OPEN_GATE, F344_DRAIN_CSA, F344_DETACH_WIFI,   F344_REPEATER_CLEAR,
      F344_DELETE_VAPS};
  static const enum f344_action finish[] = {
      F344_SET_BRIDGE_POLICY, F344_ATTACH_WIFI, F344_CONFIGURE_SECURITY,
      F344_OPEN_GATE, F344_START_SECURITY};
  unsigned i;
  int rc;
  for (i = 0; i < sizeof(dismantle) / sizeof(dismantle[0]); i++) {
    rc = action(o, dismantle[i], t, original, rollback, r);
    if (rc)
      return rc;
  }
  rc = action(o, F344_CREATE_PRIMARY, t, original, rollback, r);
  if (rc)
    return rc;
  rc = action(o, F344_SET_CHANNEL_POLICY, t, original, rollback, r);
  if (rc)
    return rc;
  if (t->mode == F344_MODE_REPEATER) {
    rc = action(o, F344_REPEATER_ENABLE, t, original, rollback, r);
    if (rc)
      return rc;
    rc = action(o, F344_CREATE_SECONDARY, t, original, rollback, r);
    if (rc)
      return rc;
  }
  for (i = 0; i < sizeof(finish) / sizeof(finish[0]); i++) {
    rc = action(o, finish[i], t, original, rollback, r);
    if (rc)
      return rc;
  }
  memset(observed, 0, sizeof(*observed));
  rc = o->wait_target(o->context, t, observed);
  if (rc)
    return rc;
  if (!same_management(original, observed) ||
      memcmp(original->primary_mac, observed->primary_mac, 6) ||
      !f344_target_observed(t, observed))
    return -5;
  if (rollback && original->three_address_bridge != observed->three_address_bridge)
    return -5;
  if (rollback && original->mode == F344_MODE_REPEATER &&
      memcmp(original->secondary_mac, observed->secondary_mac, 6))
    return -5;
  return 0;
}
int f344_apply(const struct f344_ops *o, const struct f344_target *t,
               struct f344_result *r) {
  struct f344_state before, after;
  struct f344_target undo;
  int rc, rollback_rc;
  if (!r)
    return -1;
  memset(r, 0, sizeof(*r));
  r->outcome = F344_REJECTED;
  if (!o || !t || !o->snapshot || !o->inspect || !o->execute ||
      !o->wait_target || t->mode < F344_MODE_AP ||
      t->mode > F344_MODE_REPEATER ||
      (t->bandwidth != 20 && t->bandwidth != 40 && t->bandwidth != 80) ||
      !t->profile_cookie || !f344_mask_non_dfs(t->channel_mask))
    return -1;
  if (t->mode == F344_MODE_AP &&
      (t->ap_frequency_mhz < 5180 || t->ap_frequency_mhz > 5240 ||
       (t->ap_frequency_mhz - 5000) % 5 ||
       !bit(t->channel_mask, (t->ap_frequency_mhz - 5000) / 5)))
    return -1;
  memset(&before, 0, sizeof(before));
  rc = o->snapshot(o->context, &before);
  if (rc || before.valid != F344_SNAPSHOT_VALID || !before.snapshot_cookie ||
      before.mode < F344_MODE_AP || before.mode > F344_MODE_REPEATER ||
      before.topology.extender || before.topology.other_vaps ||
      !before.topology.csa_known || before.topology.csa_pending) {
    r->error = rc ? rc : -2;
    return r->error;
  }
  if (!before.topology.csa_reuse_supported) {
    r->error = -95; /* EOPNOTSUPP: unresolved MuC descriptor retirement/reuse. */
    return r->error;
  }
  if ((before.mode != F344_MODE_AP &&
       !f344_mask_non_dfs(before.channel_mask)) ||
      before.frequency_mhz < 5180 || before.frequency_mhz > 5240 ||
      (before.frequency_mhz - 5180) % 20) {
    r->error = -3;
    return -3;
  }
  if (f344_target_observed(t, &before)) {
    r->outcome = F344_UNCHANGED;
    return 0;
  }
  rc = perform(o, t, &before, false, r, &after);
  if (!rc) {
    r->outcome = F344_APPLIED_READBACK;
    return 0;
  }
  r->error = rc;
  memset(&undo, 0, sizeof(undo));
  undo.mode = before.mode;
  undo.ap_frequency_mhz = before.frequency_mhz;
  undo.bandwidth = before.configured_bandwidth;
  undo.profile_cookie = before.snapshot_cookie;
  memcpy(undo.channel_mask, before.channel_mask, 32);
  memcpy(undo.profile_digest, before.profile_digest, 32);
  /* Rollback may restore the previous legal AP channel list. No station is
   * opened unless its prior list is non-DFS, matching the admitted baseline. */
  if (undo.mode != F344_MODE_AP && !f344_mask_non_dfs(undo.channel_mask)) {
    r->outcome = F344_ROLLBACK_FAILED;
    return rc;
  }
  rollback_rc = perform(o, &undo, &before, true, r, &after);
  r->outcome = rollback_rc ? F344_ROLLBACK_FAILED : F344_ROLLED_BACK_READBACK;
  return rc;
}
