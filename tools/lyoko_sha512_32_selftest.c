#include "lyoko_sha512_32.h"

#include <stdio.h>

static void print_digest(size_t length)
{
	unsigned char message[923];
	struct lyoko_sha512_32 state;
	unsigned char digest[64];
	unsigned int i;
	for (i = 0; i < sizeof(message); i++) message[i] = (unsigned char)i;
	lyoko_sha512_32_init(&state);
	lyoko_sha512_32_update(&state, message, length);
	lyoko_sha512_32_final(&state, digest);
	printf("%u=", (unsigned int)length);
	for (i = 0; i < sizeof(digest); i++) printf("%02x", digest[i]);
	putchar('\n');
	
}

int main(void)
{
	static const unsigned char abc[] = { 'a', 'b', 'c' };
	struct lyoko_sha512_32 state;
	unsigned char digest[64];
	unsigned int i;
	lyoko_sha512_32_init(&state);
	lyoko_sha512_32_update(&state, abc, sizeof(abc));
	lyoko_sha512_32_final(&state, digest);
	printf("abc=");
	for (i = 0; i < sizeof(digest); i++) printf("%02x", digest[i]);
	putchar('\n');
	print_digest(127);
	print_digest(128);
	print_digest(129);
	print_digest(923);
	return 0;
}
