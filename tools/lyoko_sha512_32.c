/* SHA-512 using pairs of 32-bit words for ARC700 correctness. */
#include "lyoko_sha512_32.h"

#include <string.h>

typedef struct lyoko_sha512_word word;

static const word initial_state[8] = {
	{ 0x6a09e667U, 0xf3bcc908U }, { 0xbb67ae85U, 0x84caa73bU },
	{ 0x3c6ef372U, 0xfe94f82bU }, { 0xa54ff53aU, 0x5f1d36f1U },
	{ 0x510e527fU, 0xade682d1U }, { 0x9b05688cU, 0x2b3e6c1fU },
	{ 0x1f83d9abU, 0xfb41bd6bU }, { 0x5be0cd19U, 0x137e2179U },
};

static const word round_k[80] = {
	{ 0x428a2f98U, 0xd728ae22U }, { 0x71374491U, 0x23ef65cdU },
	{ 0xb5c0fbcfU, 0xec4d3b2fU }, { 0xe9b5dba5U, 0x8189dbbcU },
	{ 0x3956c25bU, 0xf348b538U }, { 0x59f111f1U, 0xb605d019U },
	{ 0x923f82a4U, 0xaf194f9bU }, { 0xab1c5ed5U, 0xda6d8118U },
	{ 0xd807aa98U, 0xa3030242U }, { 0x12835b01U, 0x45706fbeU },
	{ 0x243185beU, 0x4ee4b28cU }, { 0x550c7dc3U, 0xd5ffb4e2U },
	{ 0x72be5d74U, 0xf27b896fU }, { 0x80deb1feU, 0x3b1696b1U },
	{ 0x9bdc06a7U, 0x25c71235U }, { 0xc19bf174U, 0xcf692694U },
	{ 0xe49b69c1U, 0x9ef14ad2U }, { 0xefbe4786U, 0x384f25e3U },
	{ 0x0fc19dc6U, 0x8b8cd5b5U }, { 0x240ca1ccU, 0x77ac9c65U },
	{ 0x2de92c6fU, 0x592b0275U }, { 0x4a7484aaU, 0x6ea6e483U },
	{ 0x5cb0a9dcU, 0xbd41fbd4U }, { 0x76f988daU, 0x831153b5U },
	{ 0x983e5152U, 0xee66dfabU }, { 0xa831c66dU, 0x2db43210U },
	{ 0xb00327c8U, 0x98fb213fU }, { 0xbf597fc7U, 0xbeef0ee4U },
	{ 0xc6e00bf3U, 0x3da88fc2U }, { 0xd5a79147U, 0x930aa725U },
	{ 0x06ca6351U, 0xe003826fU }, { 0x14292967U, 0x0a0e6e70U },
	{ 0x27b70a85U, 0x46d22ffcU }, { 0x2e1b2138U, 0x5c26c926U },
	{ 0x4d2c6dfcU, 0x5ac42aedU }, { 0x53380d13U, 0x9d95b3dfU },
	{ 0x650a7354U, 0x8baf63deU }, { 0x766a0abbU, 0x3c77b2a8U },
	{ 0x81c2c92eU, 0x47edaee6U }, { 0x92722c85U, 0x1482353bU },
	{ 0xa2bfe8a1U, 0x4cf10364U }, { 0xa81a664bU, 0xbc423001U },
	{ 0xc24b8b70U, 0xd0f89791U }, { 0xc76c51a3U, 0x0654be30U },
	{ 0xd192e819U, 0xd6ef5218U }, { 0xd6990624U, 0x5565a910U },
	{ 0xf40e3585U, 0x5771202aU }, { 0x106aa070U, 0x32bbd1b8U },
	{ 0x19a4c116U, 0xb8d2d0c8U }, { 0x1e376c08U, 0x5141ab53U },
	{ 0x2748774cU, 0xdf8eeb99U }, { 0x34b0bcb5U, 0xe19b48a8U },
	{ 0x391c0cb3U, 0xc5c95a63U }, { 0x4ed8aa4aU, 0xe3418acbU },
	{ 0x5b9cca4fU, 0x7763e373U }, { 0x682e6ff3U, 0xd6b2b8a3U },
	{ 0x748f82eeU, 0x5defb2fcU }, { 0x78a5636fU, 0x43172f60U },
	{ 0x84c87814U, 0xa1f0ab72U }, { 0x8cc70208U, 0x1a6439ecU },
	{ 0x90befffaU, 0x23631e28U }, { 0xa4506cebU, 0xde82bde9U },
	{ 0xbef9a3f7U, 0xb2c67915U }, { 0xc67178f2U, 0xe372532bU },
	{ 0xca273eceU, 0xea26619cU }, { 0xd186b8c7U, 0x21c0c207U },
	{ 0xeada7dd6U, 0xcde0eb1eU }, { 0xf57d4f7fU, 0xee6ed178U },
	{ 0x06f067aaU, 0x72176fbaU }, { 0x0a637dc5U, 0xa2c898a6U },
	{ 0x113f9804U, 0xbef90daeU }, { 0x1b710b35U, 0x131c471bU },
	{ 0x28db77f5U, 0x23047d84U }, { 0x32caab7bU, 0x40c72493U },
	{ 0x3c9ebe0aU, 0x15c9bebcU }, { 0x431d67c4U, 0x9c100d4cU },
	{ 0x4cc5d4beU, 0xcb3e42b6U }, { 0x597f299cU, 0xfc657e2aU },
	{ 0x5fcb6fabU, 0x3ad6faecU }, { 0x6c44198cU, 0x4a475817U },
};

static word wxor(word a, word b) { word r = { a.hi ^ b.hi, a.lo ^ b.lo }; return r; }
static word wand(word a, word b) { word r = { a.hi & b.hi, a.lo & b.lo }; return r; }
static word wnot(word a) { word r = { ~a.hi, ~a.lo }; return r; }
static word wor(word a, word b) { word r = { a.hi | b.hi, a.lo | b.lo }; return r; }

static word wadd(word a, word b)
{
	word r;
	r.lo = a.lo + b.lo;
	r.hi = a.hi + b.hi + (r.lo < a.lo);
	return r;
}

static word wadd4(word a, word b, word c, word d)
{
	return wadd(wadd(a, b), wadd(c, d));
}

static word wadd5(word a, word b, word c, word d, word e)
{
	return wadd(wadd4(a, b, c, d), e);
}

static word wshr(word a, unsigned int bits)
{
	word r = { 0, 0 };
	if (bits == 0) return a;
	if (bits < 32) {
		r.hi = a.hi >> bits;
		r.lo = (a.lo >> bits) | (a.hi << (32 - bits));
	} else if (bits < 64) {
		r.lo = a.hi >> (bits - 32);
	}
	return r;
}

static word wshl(word a, unsigned int bits)
{
	word r = { 0, 0 };
	if (bits == 0) return a;
	if (bits < 32) {
		r.hi = (a.hi << bits) | (a.lo >> (32 - bits));
		r.lo = a.lo << bits;
	} else if (bits < 64) {
		r.hi = a.lo << (bits - 32);
	}
	return r;
}

static word wror(word a, unsigned int bits)
{
	bits &= 63U;
	if (bits == 0) return a;
	return wor(wshr(a, bits), wshl(a, 64U - bits));
}

static word load_be(const uint8_t *input)
{
	word r;
	r.hi = ((uint32_t)input[0] << 24) | ((uint32_t)input[1] << 16) |
	       ((uint32_t)input[2] << 8) | input[3];
	r.lo = ((uint32_t)input[4] << 24) | ((uint32_t)input[5] << 16) |
	       ((uint32_t)input[6] << 8) | input[7];
	return r;
}

static void store_be(uint8_t *output, word value)
{
	output[0] = (uint8_t)(value.hi >> 24); output[1] = (uint8_t)(value.hi >> 16);
	output[2] = (uint8_t)(value.hi >> 8); output[3] = (uint8_t)value.hi;
	output[4] = (uint8_t)(value.lo >> 24); output[5] = (uint8_t)(value.lo >> 16);
	output[6] = (uint8_t)(value.lo >> 8); output[7] = (uint8_t)value.lo;
}

static void transform(struct lyoko_sha512_32 *state, const uint8_t block[128])
{
	word w[16], a, b, c, d, e, f, g, h;
	unsigned int i;
	for (i = 0; i < 16; i++) w[i] = load_be(block + (i * 8));
	a = state->h[0]; b = state->h[1]; c = state->h[2]; d = state->h[3];
	e = state->h[4]; f = state->h[5]; g = state->h[6]; h = state->h[7];
	for (i = 0; i < 80; i++) {
		word wi = w[i & 15], wi15 = w[(i + 1) & 15], wi2 = w[(i + 14) & 15], wi7 = w[(i + 9) & 15];
		word s0 = wxor(wxor(wror(wi15, 1), wror(wi15, 8)), wshr(wi15, 7));
		word s1 = wxor(wxor(wror(wi2, 19), wror(wi2, 61)), wshr(wi2, 6));
		word S0 = wxor(wxor(wror(a, 28), wror(a, 34)), wror(a, 39));
		word S1 = wxor(wxor(wror(e, 14), wror(e, 18)), wror(e, 41));
		word ch = wxor(wand(e, f), wand(wnot(e), g));
		word maj = wxor(wxor(wand(a, b), wand(a, c)), wand(b, c));
		word temp1 = wadd5(h, S1, ch, round_k[i], wi);
		word temp2 = wadd(S0, maj);
		h = g; g = f; f = e; e = wadd(d, temp1);
		d = c; c = b; b = a; a = wadd(temp1, temp2);
		w[i & 15] = wadd4(wi, s0, wi7, s1);
	}
	state->h[0] = wadd(state->h[0], a); state->h[1] = wadd(state->h[1], b);
	state->h[2] = wadd(state->h[2], c); state->h[3] = wadd(state->h[3], d);
	state->h[4] = wadd(state->h[4], e); state->h[5] = wadd(state->h[5], f);
	state->h[6] = wadd(state->h[6], g); state->h[7] = wadd(state->h[7], h);
}

void lyoko_sha512_32_init(struct lyoko_sha512_32 *state)
{
	memcpy(state->h, initial_state, sizeof(initial_state));
	state->total_bytes = 0;
	state->block_bytes = 0;
}

void lyoko_sha512_32_update(struct lyoko_sha512_32 *state, const void *data, size_t length)
{
	const uint8_t *input = data;
	while (length > 0) {
		size_t available = 128U - state->block_bytes;
		size_t take = length < available ? length : available;
		memcpy(state->block + state->block_bytes, input, take);
		state->block_bytes += (uint32_t)take;
		state->total_bytes += (uint32_t)take;
		input += take;
		length -= take;
		if (state->block_bytes == 128U) {
			transform(state, state->block);
			state->block_bytes = 0;
		}
	}
}

void lyoko_sha512_32_final(struct lyoko_sha512_32 *state, uint8_t digest[64])
{
	uint32_t bits = state->total_bytes << 3;
	unsigned int i;
	state->block[state->block_bytes++] = 0x80;
	if (state->block_bytes > 112U) {
		memset(state->block + state->block_bytes, 0, 128U - state->block_bytes);
		transform(state, state->block);
		state->block_bytes = 0;
	}
	memset(state->block + state->block_bytes, 0, 128U - state->block_bytes);
	state->block[124] = (uint8_t)(bits >> 24);
	state->block[125] = (uint8_t)(bits >> 16);
	state->block[126] = (uint8_t)(bits >> 8);
	state->block[127] = (uint8_t)bits;
	transform(state, state->block);
	for (i = 0; i < 8; i++) store_be(digest + (i * 8), state->h[i]);
}
