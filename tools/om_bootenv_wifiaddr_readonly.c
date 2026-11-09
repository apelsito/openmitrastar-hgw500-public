// SPDX-License-Identifier: GPL-2.0-only
/* Read-only redundant Bootbase wifiaddr importer for HGW-500BNA-QCv2. */
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

#define ENV_SIZE 0x10000U
#define ENV_CRC_END 0x6000U
#define TARGET "mitrastar,hgw-500bna-qcv2"

struct identity {
	int crc_valid;
	int wifi_count;
	uint8_t wifi[6];
};

static uint32_t load_le32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
		((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t crc32_env(const uint8_t *data, size_t size)
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

static int nibble(unsigned char c)
{
	if (c >= '0' && c <= '9') return c - '0';
	if (c >= 'a' && c <= 'f') return c - 'a' + 10;
	if (c >= 'A' && c <= 'F') return c - 'A' + 10;
	return -1;
}

static int parse_mac(const char *text, size_t length, uint8_t mac[6])
{
	unsigned int i, all_zero = 1, all_ff = 1;

	if (length != 17)
		return -1;
	for (i = 0; i < 6; i++) {
		int hi = nibble((unsigned char)text[i * 3]);
		int lo = nibble((unsigned char)text[i * 3 + 1]);
		if (hi < 0 || lo < 0 || (i < 5 && text[i * 3 + 2] != ':'))
			return -1;
		mac[i] = (uint8_t)((hi << 4) | lo);
		all_zero &= mac[i] == 0;
		all_ff &= mac[i] == 0xff;
	}
	return (mac[0] & 1U) || all_zero || all_ff ? -1 : 0;
}

static void parse_env(const uint8_t raw[ENV_SIZE], struct identity *id)
{
	size_t offset = 4;

	memset(id, 0, sizeof(*id));
	id->crc_valid = load_le32(raw) == crc32_env(raw + 4, ENV_CRC_END - 4);
	if (!id->crc_valid)
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
		if ((size_t)(equal - entry) == 8 && !memcmp(entry, "wifiaddr", 8)) {
			uint8_t parsed[6];
			id->wifi_count++;
			if (parse_mac((const char *)equal + 1,
					length - (size_t)(equal - entry) - 1, parsed) == 0)
				memcpy(id->wifi, parsed, sizeof(parsed));
			else
				id->wifi_count = -1;
		}
		offset += length + 1;
	}
}

static int target_ok(const char *path)
{
	char data[512];
	ssize_t length;
	size_t offset = 0;
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0) return 0;
	length = read(fd, data, sizeof(data));
	close(fd);
	if (length <= 0) return 0;
	while (offset < (size_t)length) {
		size_t left = (size_t)length - offset;
		size_t item = strnlen(data + offset, left);
		if (item == strlen(TARGET) && !memcmp(data + offset, TARGET, item))
			return 1;
		if (item == left) break;
		offset += item + 1;
	}
	return 0;
}

static int read_text(const char *path, char *out, size_t capacity)
{
	ssize_t length;
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0) return -1;
	length = read(fd, out, capacity - 1);
	close(fd);
	if (length <= 0) return -1;
	while (length > 0 && (out[length - 1] == '\n' || out[length - 1] == '\r'))
		length--;
	out[length] = '\0';
	return 0;
}

static int find_mtd(const char *proc_mtd, const char *wanted)
{
	char line[256], name[64];
	unsigned int index;
	unsigned long size, erase;
	FILE *stream = fopen(proc_mtd, "r");
	if (!stream) return -1;
	while (fgets(line, sizeof(line), stream)) {
		if (sscanf(line, "mtd%u: %lx %lx \"%63[^\"]\"", &index, &size, &erase, name) == 4 &&
			!strcmp(name, wanted) && size == ENV_SIZE && erase == ENV_SIZE) {
			fclose(stream);
			return (int)index;
		}
	}
	fclose(stream);
	return -1;
}

static int read_partition(const char *proc_mtd, const char *sys_mtd,
		const char *dev_root, const char *label, int test_mode, uint8_t raw[ENV_SIZE])
{
	char path[256], value[64];
	struct stat st;
	size_t done = 0;
	int index = find_mtd(proc_mtd, label);
	int fd;

	if (index < 0) return -1;
	snprintf(path, sizeof(path), "%s/mtd%d/name", sys_mtd, index);
	if (read_text(path, value, sizeof(value)) || strcmp(value, label)) return -1;
	snprintf(path, sizeof(path), "%s/mtd%d/type", sys_mtd, index);
	if (read_text(path, value, sizeof(value)) || strcmp(value, "rom")) return -1;
	snprintf(path, sizeof(path), "%s/mtd%d/size", sys_mtd, index);
	if (read_text(path, value, sizeof(value)) || strtoul(value, NULL, 0) != ENV_SIZE) return -1;
	snprintf(path, sizeof(path), "%s/mtd%d", dev_root, index);
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0 || fstat(fd, &st)) { if (fd >= 0) close(fd); return -1; }
	if ((!test_mode && !S_ISCHR(st.st_mode)) || (test_mode && !S_ISREG(st.st_mode))) {
		close(fd); return -1;
	}
	while (done < ENV_SIZE) {
		ssize_t rc = read(fd, raw + done, ENV_SIZE - done);
		if (rc < 0 && errno == EINTR) continue;
		if (rc <= 0) { close(fd); return -1; }
		done += (size_t)rc;
	}
	close(fd);
	return 0;
}

static int ensure_directory(const char *path, mode_t mode, int enforce_mode)
{
	struct stat st;

	if (mkdir(path, mode) && errno != EEXIST)
		return -1;
	if (lstat(path, &st) || !S_ISDIR(st.st_mode))
		return -1;
	return enforce_mode ? chmod(path, mode) : 0;
}

static int atomic_write(const char *path, const void *data, size_t length)
{
	char temporary[320];
	int fd;
	if (snprintf(temporary, sizeof(temporary), "%s.tmp.%ld", path,
			(long)getpid()) >= (int)sizeof(temporary)) return -1;
	fd = open(temporary, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
	if (fd < 0) return -1;
	if (write(fd, data, length) != (ssize_t)length || fchmod(fd, 0600) || fsync(fd)) {
		close(fd); unlink(temporary); return -1;
	}
	if (close(fd) || rename(temporary, path)) { unlink(temporary); return -1; }
	return chmod(path, 0600);
}

int main(int argc, char **argv)
{
	const char *compatible = "/proc/device-tree/compatible";
	const char *proc_mtd = "/proc/mtd";
	const char *sys_mtd = "/sys/class/mtd";
	const char *dev_root = "/dev";
	const char *runtime = "/run/openmitrastar/bootenv";
	struct identity primary, backup;
	uint8_t *raw = NULL;
	char wifi_path[256], ready_path[256], wifi_line[19];
	static const char ready[] =
		"schema=openmitrastar.bootenv-wifiaddr/v1\n"
		"source=mtd1+mtd2-redundant-readonly\n"
		"primary_crc=valid\nbackup_crc=valid\ncopies=match\n"
		"key=wifiaddr\nsecrets=redacted\n";
	int test_mode = 0, rc = 1;

#ifdef OPENMITRASTAR_BOOTENV_HOST_TEST
	if (argc != 6) return 2;
	compatible = argv[1]; proc_mtd = argv[2]; sys_mtd = argv[3];
	dev_root = argv[4]; runtime = argv[5]; test_mode = 1;
#else
	(void)argv;
	if (argc != 1) return 2;
#endif
	if (!target_ok(compatible)) { fprintf(stderr, "OMBOOTENV_REFUSED reason=target secrets=redacted\n"); return 3; }
	raw = malloc(ENV_SIZE * 2U);
	if (!raw) return 4;
	if (read_partition(proc_mtd, sys_mtd, dev_root, "uboot_env", test_mode, raw) ||
		read_partition(proc_mtd, sys_mtd, dev_root, "uboot_env_bak", test_mode, raw + ENV_SIZE)) {
		fprintf(stderr, "OMBOOTENV_REFUSED reason=mtd-contract secrets=redacted\n"); goto out;
	}
	parse_env(raw, &primary); parse_env(raw + ENV_SIZE, &backup);
	if (!primary.crc_valid || !backup.crc_valid) {
		fprintf(stderr, "OMBOOTENV_REFUSED reason=crc primary=%u backup=%u secrets=redacted\n",
			primary.crc_valid, backup.crc_valid); goto out;
	}
	if (primary.wifi_count != 1 || backup.wifi_count != 1) {
		fprintf(stderr, "OMBOOTENV_REFUSED reason=wifiaddr-count secrets=redacted\n"); goto out;
	}
	if (memcmp(primary.wifi, backup.wifi, sizeof(primary.wifi))) {
		fprintf(stderr, "OMBOOTENV_REFUSED reason=redundant-wifiaddr-mismatch secrets=redacted\n"); goto out;
	}
	if (!test_mode && ensure_directory("/run/openmitrastar", 0755, 0)) goto out;
	if (ensure_directory(runtime, 0700, 1)) goto out;
	if (snprintf(wifi_path, sizeof(wifi_path), "%s/wifiaddr", runtime) >= (int)sizeof(wifi_path) ||
		snprintf(ready_path, sizeof(ready_path), "%s/ready", runtime) >= (int)sizeof(ready_path)) goto out;
	snprintf(wifi_line, sizeof(wifi_line), "%02x:%02x:%02x:%02x:%02x:%02x\n",
		primary.wifi[0], primary.wifi[1], primary.wifi[2],
		primary.wifi[3], primary.wifi[4], primary.wifi[5]);
	if (atomic_write(wifi_path, wifi_line, strlen(wifi_line)) ||
		atomic_write(ready_path, ready, sizeof(ready) - 1)) {
		unlink(wifi_path); unlink(ready_path); goto out;
	}
	printf("OMBOOTENV_READY source=mtd1+mtd2-redundant-readonly primary_crc=valid backup_crc=valid copies=match key=wifiaddr mode=0600 secrets=redacted\n");
	rc = 0;
out:
	memset(raw, 0, ENV_SIZE * 2U); free(raw);
	return rc;
}
