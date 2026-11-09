#include "lyoko_sha512_32.h"

#include <stdio.h>

static int add_file(struct lyoko_sha512_32 *state, const char *path, size_t limit)
{
	unsigned char buffer[4096];
	FILE *stream = fopen(path, "rb");
	size_t count, total = 0;
	if (!stream) return -1;
	while ((count = fread(buffer, 1, sizeof(buffer), stream)) > 0) {
		if (limit && total + count > limit) count = limit - total;
		lyoko_sha512_32_update(state, buffer, count);
		total += count;
		if (limit && total == limit) break;
	}
	return fclose(stream);
}

int main(int argc, char **argv)
{
	struct lyoko_sha512_32 state;
	unsigned char digest[64];
	unsigned int i;
	if (argc != 4) return 2;
	lyoko_sha512_32_init(&state);
	if (add_file(&state, argv[1], 32) || add_file(&state, argv[2], 0) || add_file(&state, argv[3], 0)) return 2;
	lyoko_sha512_32_final(&state, digest);
	for (i = 0; i < 64; i++) printf("%02x", digest[i]);
	putchar('\n');
	return 0;
}
