// SPDX-License-Identifier: GPL-2.0-only
/* Read-only per-device Quantenna MAC importer for HGW-500BNA-QCv2. */
#define _XOPEN_SOURCE 700

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define ENV_PRIMARY_OFFSET 0x00020000U
#define ENV_BACKUP_OFFSET  0x00030000U
#define ENV_PART_SIZE      0x00010000U
#define ENV_CRC_END        0x00006000U

#define DEFAULT_SOURCE     "/dev/omspiro"
#define DEFAULT_COMPATIBLE "/proc/device-tree/compatible"
#define DEFAULT_OUTPUT     "/run/openmitrastar/secrets/qtn-mac0addr"
#define TARGET_COMPATIBLE  "mitrastar,hgw-500bna-qcv2"

struct env_identity {
	int crc_valid;
	int identity_valid;
	uint8_t eth[6];
	uint8_t wifi[6];
};

static uint32_t load_le32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
		((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t env_crc32(const uint8_t *data, size_t size)
{
	uint32_t crc = 0xffffffffU;
	size_t i;

	for (i = 0; i < size; i++) {
		unsigned int bit;

		crc ^= data[i];
		for (bit = 0; bit < 8; bit++)
			crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
	}
	return ~crc;
}

static int hex_nibble(unsigned char c)
{
	if (c >= '0' && c <= '9')
		return c - '0';
	if (c >= 'a' && c <= 'f')
		return c - 'a' + 10;
	if (c >= 'A' && c <= 'F')
		return c - 'A' + 10;
	return -1;
}

static int parse_mac(const char *value, size_t length, uint8_t mac[6])
{
	unsigned int i;
	unsigned int all_zero = 1;
	unsigned int all_ff = 1;

	if (length != 17)
		return -1;
	for (i = 0; i < 6; i++) {
		int hi = hex_nibble((unsigned char)value[i * 3]);
		int lo = hex_nibble((unsigned char)value[i * 3 + 1]);

		if (hi < 0 || lo < 0 || (i != 5 && value[i * 3 + 2] != ':'))
			return -1;
		mac[i] = (uint8_t)((hi << 4) | lo);
		all_zero &= mac[i] == 0;
		all_ff &= mac[i] == 0xff;
	}
	if ((mac[0] & 1U) || all_zero || all_ff)
		return -1;
	return 0;
}

static int wifi_is_base_plus_one(const uint8_t eth[6], const uint8_t wifi[6])
{
	uint8_t derived[6];
	int i;

	memcpy(derived, eth, sizeof(derived));
	for (i = 5; i >= 0; i--) {
		derived[i]++;
		if (derived[i] != 0)
			break;
	}
	return memcmp(derived, wifi, sizeof(derived)) == 0;
}

static int read_exact_at(int fd, void *buffer, size_t size, off_t offset)
{
	uint8_t *out = buffer;
	size_t done = 0;

	while (done < size) {
		ssize_t rc = pread(fd, out + done, size - done, offset + (off_t)done);

		if (rc < 0 && errno == EINTR)
			continue;
		if (rc <= 0)
			return -1;
		done += (size_t)rc;
	}
	return 0;
}

static void parse_environment(const uint8_t raw[ENV_PART_SIZE],
		struct env_identity *identity)
{
	size_t offset = 4;
	int have_eth = 0;
	int have_wifi = 0;

	memset(identity, 0, sizeof(*identity));
	identity->crc_valid = load_le32(raw) ==
		env_crc32(raw + 4, ENV_CRC_END - 4);
	if (!identity->crc_valid)
		return;

	while (offset < ENV_CRC_END) {
		const uint8_t *entry = raw + offset;
		const uint8_t *end = memchr(entry, '\0', ENV_CRC_END - offset);
		const uint8_t *equal;
		size_t length;

		if (!end)
			return;
		length = (size_t)(end - entry);
		if (!length)
			break;
		equal = memchr(entry, '=', length);
		if (!equal)
			return;
		if ((size_t)(equal - entry) == 7 && !memcmp(entry, "ethaddr", 7))
			have_eth = parse_mac((const char *)equal + 1,
				length - (size_t)(equal - entry) - 1, identity->eth) == 0;
		else if ((size_t)(equal - entry) == 8 && !memcmp(entry, "wifiaddr", 8))
			have_wifi = parse_mac((const char *)equal + 1,
				length - (size_t)(equal - entry) - 1, identity->wifi) == 0;
		offset += length + 1;
	}
	identity->identity_valid = have_eth && have_wifi &&
		wifi_is_base_plus_one(identity->eth, identity->wifi);
}

static int compatible_is_target(const char *path)
{
	char buffer[512];
	ssize_t length;
	size_t offset = 0;
	int fd = open(path, O_RDONLY | O_CLOEXEC);

	if (fd < 0)
		return 0;
	length = read(fd, buffer, sizeof(buffer));
	close(fd);
	if (length <= 0)
		return 0;
	while (offset < (size_t)length) {
		size_t remaining = (size_t)length - offset;
		size_t item = strnlen(buffer + offset, remaining);

		if (item == strlen(TARGET_COMPATIBLE) &&
			!memcmp(buffer + offset, TARGET_COMPATIBLE, item))
			return 1;
		if (item == remaining)
			break;
		offset += item + 1;
	}
	return 0;
}

static int same_identity(const struct env_identity *a,
		const struct env_identity *b)
{
	return !memcmp(a->eth, b->eth, sizeof(a->eth)) &&
		!memcmp(a->wifi, b->wifi, sizeof(a->wifi));
}

static int publish_mac(const char *path, const uint8_t mac[6])
{
	char temporary[256];
	char line[19];
	int fd;
	int length;

	if (snprintf(temporary, sizeof(temporary), "%s.tmp.%ld", path,
			(long)getpid()) >= (int)sizeof(temporary))
		return -1;
	length = snprintf(line, sizeof(line), "%02X:%02X:%02X:%02X:%02X:%02X\n",
		mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
	fd = open(temporary, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
	if (fd < 0)
		return -1;
	if (write(fd, line, (size_t)length) != length || fsync(fd) || fchmod(fd, 0600)) {
		close(fd);
		unlink(temporary);
		return -1;
	}
	if (close(fd) || rename(temporary, path)) {
		unlink(temporary);
		return -1;
	}
	return chmod(path, 0600);
}

int main(int argc, char **argv)
{
	const char *source = DEFAULT_SOURCE;
	const char *compatible = DEFAULT_COMPATIBLE;
	const char *output = DEFAULT_OUTPUT;
	struct env_identity primary;
	struct env_identity backup;
	const struct env_identity *chosen;
	uint8_t *raw;
	struct stat st;
	int fd;
	int rc = 1;

#ifdef OPENMITRASTAR_QTN_MAC_HOST_TEST
	if (argc != 4) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=test-arguments\n");
		return 2;
	}
	source = argv[1];
	compatible = argv[2];
	output = argv[3];
#else
	(void)argv;
	if (argc != 1) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=arguments\n");
		return 2;
	}
#endif
	if (!compatible_is_target(compatible)) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=target\n");
		return 3;
	}
	fd = open(source, O_RDONLY | O_CLOEXEC);
	if (fd < 0 || fstat(fd, &st)) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=source-open\n");
		if (fd >= 0)
			close(fd);
		return 4;
	}
#ifndef OPENMITRASTAR_QTN_MAC_HOST_TEST
	if (!S_ISCHR(st.st_mode) || (st.st_mode & 0777) != 0400) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=source-contract\n");
		close(fd);
		return 4;
	}
#endif
	raw = malloc(ENV_PART_SIZE * 2U);
	if (!raw) {
		close(fd);
		return 5;
	}
	if (read_exact_at(fd, raw, ENV_PART_SIZE, ENV_PRIMARY_OFFSET) ||
		read_exact_at(fd, raw + ENV_PART_SIZE, ENV_PART_SIZE, ENV_BACKUP_OFFSET)) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=source-read\n");
		goto out;
	}
	close(fd);
	fd = -1;
	parse_environment(raw, &primary);
	parse_environment(raw + ENV_PART_SIZE, &backup);
	if (primary.identity_valid && backup.identity_valid &&
		!same_identity(&primary, &backup)) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=redundant-identity-conflict\n");
		goto out;
	}
	chosen = primary.identity_valid ? &primary :
		(backup.identity_valid ? &backup : NULL);
	if (!chosen) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=no-valid-identity primary_crc=%u backup_crc=%u\n",
			primary.crc_valid, backup.crc_valid);
		goto out;
	}
	if (publish_mac(output, chosen->wifi)) {
		fprintf(stderr, "OMQTNMAC_REFUSED reason=publish\n");
		goto out;
	}
	printf("OMQTNMAC_READY source=%s primary_crc=%s backup_crc=%s relation=base-plus-one mode=0600 secrets=redacted\n",
		chosen == &primary ? "uboot-env-primary" : "uboot-env-backup",
		primary.crc_valid ? "PASS" : "FAIL",
		backup.crc_valid ? "PASS" : "FAIL");
	rc = 0;
out:
	if (fd >= 0)
		close(fd);
	memset(raw, 0, ENV_PART_SIZE * 2U);
	free(raw);
	return rc;
}
