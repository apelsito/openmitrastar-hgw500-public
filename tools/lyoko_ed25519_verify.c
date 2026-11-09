/* Minimal Lyoko package-feed verifier using Dropbear's Ed25519 implementation. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "curve25519.h"

#define PUBLIC_KEY_BYTES 32U
#define SIGNATURE_BYTES 64U
#define MAX_MESSAGE_BYTES (1024U * 1024U)

static unsigned char *read_file(const char *path, size_t minimum, size_t maximum, size_t *length)
{
	FILE *stream;
	struct stat info;
	unsigned char *payload;
	size_t read_bytes;

	if (stat(path, &info) != 0 || info.st_size < 0) {
		return NULL;
	}
	if ((size_t)info.st_size < minimum || (size_t)info.st_size > maximum) {
		errno = EFBIG;
		return NULL;
	}
	stream = fopen(path, "rb");
	if (stream == NULL) {
		return NULL;
	}
	payload = malloc((size_t)info.st_size + 1U);
	if (payload == NULL) {
		fclose(stream);
		return NULL;
	}
	read_bytes = fread(payload, 1U, (size_t)info.st_size, stream);
	if (read_bytes != (size_t)info.st_size || fclose(stream) != 0) {
		memset(payload, 0, (size_t)info.st_size + 1U);
		free(payload);
		return NULL;
	}
	payload[read_bytes] = 0;
	*length = read_bytes;
	return payload;
}

static void burn(unsigned char *payload, size_t length)
{
	volatile unsigned char *cursor = payload;
	while (length-- > 0U) {
		*cursor++ = 0;
	}
}

int main(int argc, char **argv)
{
	unsigned char *public_key = NULL;
	unsigned char *signature = NULL;
	unsigned char *message = NULL;
	size_t public_key_length = 0;
	size_t signature_length = 0;
	size_t message_length = 0;
	int verified;
	int result = 2;

	if (argc != 4) {
		fprintf(stderr, "usage: lyoko-ed25519-verify PUBLIC_KEY_RAW SIGNATURE_RAW MESSAGE\n");
		return 2;
	}
	public_key = read_file(argv[1], PUBLIC_KEY_BYTES, PUBLIC_KEY_BYTES, &public_key_length);
	signature = read_file(argv[2], SIGNATURE_BYTES, SIGNATURE_BYTES, &signature_length);
	message = read_file(argv[3], 1U, MAX_MESSAGE_BYTES, &message_length);
	if (public_key == NULL || signature == NULL || message == NULL) {
		fprintf(stderr, "LYOKO_ED25519_VERIFY_ERROR=input\n");
		goto out;
	}
	verified = dropbear_ed25519_verify(
		message, (unsigned long)message_length,
		signature, (unsigned long)signature_length,
		public_key
	);
	if (verified != 0) {
		fprintf(stderr, "LYOKO_ED25519_VERIFY_ERROR=signature\n");
		result = 1;
		goto out;
	}
	printf("LYOKO_ED25519_VERIFY_PASS=1 bytes=%lu\n", (unsigned long)message_length);
	result = 0;

out:
	if (public_key != NULL) { burn(public_key, public_key_length); free(public_key); }
	if (signature != NULL) { burn(signature, signature_length); free(signature); }
	if (message != NULL) { burn(message, message_length); free(message); }
	return result;
}
