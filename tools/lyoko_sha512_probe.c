/* Diagnostic SHA-512 probe for the Lyoko Ed25519 verification path. */
#include <stdio.h>
#include <stdlib.h>

#include "tomcrypt.h"

static int hash_file_contents(hash_state *state, const char *path)
{
	unsigned char buffer[4096];
	FILE *stream = fopen(path, "rb");
	size_t count;

	if (stream == NULL)
		return -1;
	while ((count = fread(buffer, 1, sizeof(buffer), stream)) > 0) {
		if (sha512_process(state, buffer, (unsigned long)count) != CRYPT_OK) {
			fclose(stream);
			return -1;
		}
	}
	if (ferror(stream) || fclose(stream) != 0)
		return -1;
	return 0;
}

int main(int argc, char **argv)
{
	hash_state state __attribute__((aligned(8)));
	unsigned char digest[64];
	unsigned int index;
	FILE *signature;
	FILE *public_key;
	unsigned char prefix[32];

	if (argc != 4)
		return 2;
	signature = fopen(argv[1], "rb");
	public_key = fopen(argv[2], "rb");
	if (signature == NULL || public_key == NULL)
		return 2;
	if (fread(prefix, 1, 32, signature) != 32 || fclose(signature) != 0)
		return 2;
	if (sha512_init(&state) != CRYPT_OK ||
	    sha512_process(&state, prefix, 32) != CRYPT_OK ||
	    fread(prefix, 1, 32, public_key) != 32 || fclose(public_key) != 0 ||
	    sha512_process(&state, prefix, 32) != CRYPT_OK ||
	    hash_file_contents(&state, argv[3]) != 0 || sha512_done(&state, digest) != CRYPT_OK)
		return 2;
	for (index = 0; index < sizeof(digest); index++)
		printf("%02x", digest[index]);
	putchar('\n');
	return 0;
}
