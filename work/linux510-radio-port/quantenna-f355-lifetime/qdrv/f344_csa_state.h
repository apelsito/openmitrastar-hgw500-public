/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F344_CSA_STATE_H
#define F344_CSA_STATE_H
#ifdef __KERNEL__
#include <linux/types.h>
typedef u32 f344_generation;
#else
#include <stdbool.h>
#include <stdint.h>
typedef uint32_t f344_generation;
#endif
/* Caller serializes each operation. No firmware state is synthesized here. */
struct f344_csa_state {
  f344_generation generation;
  unsigned readers;
  bool hold, drained;
};
static inline int f344_csa_hold(struct f344_csa_state *s, bool hold)
{
  if (hold) {
    if (s->generation == (f344_generation)~0U) return -1;
    ++s->generation;
    s->hold = true;
    s->drained = false;
  } else {
    if (s->hold && !s->drained) return -1;
    s->hold = false;
  }
  return 0;
}
static inline f344_generation f344_csa_enter(struct f344_csa_state *s,
                                            f344_generation expected)
{
  if (s->hold || !s->generation || s->readers == ~0U ||
      (expected && expected != s->generation)) return 0;
  ++s->readers;
  return s->generation;
}
static inline void f344_csa_leave(struct f344_csa_state *s)
{
  if (s->readers) --s->readers;
}
static inline bool f344_csa_mark_drained(struct f344_csa_state *s,
                                       bool hardware_active, bool joined)
{
  s->drained = s->hold && !s->readers && !hardware_active && joined;
  return s->drained;
}
#endif
