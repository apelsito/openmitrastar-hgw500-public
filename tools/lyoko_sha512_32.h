#ifndef LYOKO_SHA512_32_H
#define LYOKO_SHA512_32_H

#include <stddef.h>
#include <stdint.h>

struct lyoko_sha512_word {
	uint32_t hi;
	uint32_t lo;
};

struct lyoko_sha512_32 {
	struct lyoko_sha512_word h[8];
	uint8_t block[128];
	uint32_t total_bytes;
	uint32_t block_bytes;
};

void lyoko_sha512_32_init(struct lyoko_sha512_32 *state);
void lyoko_sha512_32_update(struct lyoko_sha512_32 *state, const void *data, size_t length);
void lyoko_sha512_32_final(struct lyoko_sha512_32 *state, uint8_t digest[64]);

#endif
