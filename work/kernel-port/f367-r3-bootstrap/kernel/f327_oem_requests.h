/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef OPENMITRASTAR_F327_OEM_REQUESTS_H
#define OPENMITRASTAR_F327_OEM_REQUESTS_H
#include "f316_portable.h"

/* OEM-compatible nonblocking requests. The caller holds one IRQ-safe lock.
 * The worker owns the classifier and applies requests without sharing that
 * mutable classifier with IRQ callers. Disable excludes NEW dispatches; an
 * already executing callback may finish, as in OEM radar_disable/del_timer.
 */
struct f327_oem_requests {
	uint64_t epoch;
	uint64_t applied_epoch;
	uint16_t channel;
	uint16_t bandwidth;
	uint8_t registrations;
	bool started;
	bool enable_requested;
	bool exhausted;
};

static inline void f327_oem_init(struct f327_oem_requests *state,
	uint16_t channel, uint16_t bandwidth)
{
	state->epoch = 1;
	state->applied_epoch = 0;
	state->channel = channel;
	state->bandwidth = bandwidth;
	state->registrations = 0;
	state->started = false;
	state->enable_requested = false;
	state->exhausted = false;
}

static inline bool f327_oem_invalidate(struct f327_oem_requests *state)
{
	state->applied_epoch = 0;
	if (state->exhausted || state->epoch == (uint64_t)~(uint64_t)0) {
		state->exhausted = true;
		state->enable_requested = false;
		return false;
	}
	state->epoch++;
	return true;
}

static inline bool f327_oem_channel(struct f327_oem_requests *state,
	uint16_t channel)
{
	if (!channel || channel > 196 || state->exhausted)
		return false;
	if (channel == state->channel)
		return true;
	if (!f327_oem_invalidate(state))
		return false;
	state->channel = channel;
	return true;
}

static inline bool f327_oem_bandwidth(struct f327_oem_requests *state,
	uint16_t bandwidth)
{
	if ((bandwidth != 20 && bandwidth != 40 && bandwidth != 80) || state->exhausted)
		return false;
	if (bandwidth == state->bandwidth)
		return true;
	if (!f327_oem_invalidate(state))
		return false;
	state->bandwidth = bandwidth;
	return true;
}

static inline void f327_oem_disable(struct f327_oem_requests *state, bool stop)
{
	(void)f327_oem_invalidate(state);
	state->enable_requested = false;
	if (stop)
		state->started = false;
}

static inline bool f327_oem_enable(struct f327_oem_requests *state)
{
	if (!state->started || state->registrations != 7 || !f327_oem_invalidate(state))
		return false;
	state->enable_requested = true;
	return true;
}

static inline bool f327_oem_apply(struct f327_oem_requests *state,
	const struct f327_oem_requests *captured)
{
	if (state->exhausted || state->epoch != captured->epoch ||
		state->channel != captured->channel || state->bandwidth != captured->bandwidth)
		return false;
	state->applied_epoch = captured->epoch;
	return true;
}

static inline bool f327_oem_current(const struct f327_oem_requests *state,
	const struct f327_oem_requests *captured)
{
	return !state->exhausted && state->epoch == captured->epoch &&
		state->channel == captured->channel && state->bandwidth == captured->bandwidth;
}

static inline bool f327_oem_callback_allowed(const struct f327_oem_requests *state,
	const struct f327_oem_requests *captured, bool authority)
{
	return authority && state->started && state->enable_requested &&
		state->registrations == 7 && state->applied_epoch == captured->epoch &&
		f327_oem_current(state, captured);
}
#endif
