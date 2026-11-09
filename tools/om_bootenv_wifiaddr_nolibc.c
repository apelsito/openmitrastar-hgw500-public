// SPDX-License-Identifier: GPL-2.0-only
/* ARC700 syscall-only Bootbase wifiaddr importer; no libc, CRT, TLS or atomics. */

typedef unsigned char om_u8;
typedef unsigned int om_u32;
typedef unsigned long om_word;

#define OM_ENV_SIZE 0x10000U
#define OM_ENV_CRC_END 0x6000U
#define OM_AT_FDCWD (-100)
#define OM_O_RDONLY 0
#define OM_O_WRONLY 1
#define OM_O_CREAT 0100
#define OM_O_TRUNC 01000
#define OM_O_CLOEXEC 02000000
#define OM_EEXIST 17

#define OM_NR_MKDIRAT 34
#define OM_NR_UNLINKAT 35
#define OM_NR_RENAMEAT 38
#define OM_NR_FCHMOD 52
#define OM_NR_OPENAT 56
#define OM_NR_CLOSE 57
#define OM_NR_READ 63
#define OM_NR_WRITE 64
#define OM_NR_FSYNC 82
#define OM_NR_EXIT 93

static om_u8 om_primary[OM_ENV_SIZE];
static om_u8 om_backup[OM_ENV_SIZE];
static char om_proc_mtd[2048];
static char om_path[160];

struct om_identity {
	int crc_valid;
	int wifi_count;
	om_u8 wifi[6];
};

static long om_syscall1(long number, long arg0)
{
	register long r0 __asm__("r0") = arg0;
	register long r8 __asm__("r8") = number;
	__asm__ volatile("trap0" : "+r"(r0) : "r"(r8) : "memory");
	return r0;
}

static long om_syscall2(long number, long arg0, long arg1)
{
	register long r0 __asm__("r0") = arg0;
	register long r1 __asm__("r1") = arg1;
	register long r8 __asm__("r8") = number;
	__asm__ volatile("trap0" : "+r"(r0) : "r"(r1), "r"(r8) : "memory");
	return r0;
}

static long om_syscall3(long number, long arg0, long arg1, long arg2)
{
	register long r0 __asm__("r0") = arg0;
	register long r1 __asm__("r1") = arg1;
	register long r2 __asm__("r2") = arg2;
	register long r8 __asm__("r8") = number;
	__asm__ volatile("trap0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r8) : "memory");
	return r0;
}

static long om_syscall4(long number, long arg0, long arg1, long arg2, long arg3)
{
	register long r0 __asm__("r0") = arg0;
	register long r1 __asm__("r1") = arg1;
	register long r2 __asm__("r2") = arg2;
	register long r3 __asm__("r3") = arg3;
	register long r8 __asm__("r8") = number;
	__asm__ volatile("trap0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r8) : "memory");
	return r0;
}

static om_word om_strlen(const char *s)
{
	om_word n = 0;
	while (s[n]) n++;
	return n;
}

static int om_streq(const char *a, const char *b)
{
	while (*a && *a == *b) { a++; b++; }
	return *a == *b;
}

static int om_memcmp(const void *av, const void *bv, om_word n)
{
	const om_u8 *a = av, *b = bv;
	while (n--) { if (*a != *b) return *a - *b; a++; b++; }
	return 0;
}

static void om_memcpy(void *dv, const void *sv, om_word n)
{
	om_u8 *d = dv; const om_u8 *s = sv;
	while (n--) *d++ = *s++;
}

static void om_memzero(void *dv, om_word n)
{
	om_u8 *d = dv;
	while (n--) *d++ = 0;
}

static void om_puts_fd(int fd, const char *s)
{
	om_word left = om_strlen(s);
	while (left) {
		long rc = om_syscall3(OM_NR_WRITE, fd, (long)s, left);
		if (rc <= 0) return;
		s += rc; left -= (om_word)rc;
	}
}

__attribute__((noreturn)) static void om_exit(long status)
{
	om_syscall1(OM_NR_EXIT, status);
	for (;;) __asm__ volatile("nop");
}

__attribute__((noreturn)) static void om_refuse(const char *reason, long code)
{
	om_puts_fd(2, "OMBOOTENV_REFUSED reason=");
	om_puts_fd(2, reason);
	om_puts_fd(2, " secrets=redacted\n");
	om_exit(code);
}

static long om_open_ro(const char *path)
{
	return om_syscall4(OM_NR_OPENAT, OM_AT_FDCWD, (long)path,
		OM_O_RDONLY | OM_O_CLOEXEC, 0);
}

static long om_read_all(const char *path, void *buffer, om_word capacity)
{
	long fd = om_open_ro(path);
	om_word done = 0;
	if (fd < 0) return fd;
	while (done < capacity) {
		long rc = om_syscall3(OM_NR_READ, fd, (long)((om_u8 *)buffer + done), capacity - done);
		if (rc < 0) { om_syscall1(OM_NR_CLOSE, fd); return rc; }
		if (!rc) break;
		done += (om_word)rc;
	}
	om_syscall1(OM_NR_CLOSE, fd);
	return (long)done;
}

static om_u32 om_load_le32(const om_u8 *p)
{
	return (om_u32)p[0] | ((om_u32)p[1] << 8) |
		((om_u32)p[2] << 16) | ((om_u32)p[3] << 24);
}

static om_u32 om_crc32(const om_u8 *p, om_word n)
{
	om_u32 crc = 0xffffffffU;
	while (n--) {
		unsigned int bit;
		crc ^= *p++;
		for (bit = 0; bit < 8; bit++)
			crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
	}
	return ~crc;
}

static int om_nibble(char c)
{
	if (c >= '0' && c <= '9') return c - '0';
	if (c >= 'a' && c <= 'f') return c - 'a' + 10;
	if (c >= 'A' && c <= 'F') return c - 'A' + 10;
	return -1;
}

static int om_parse_mac(const char *s, om_word n, om_u8 mac[6])
{
	unsigned int i, zero = 1, ff = 1;
	if (n != 17) return -1;
	for (i = 0; i < 6; i++) {
		int hi = om_nibble(s[i * 3]), lo = om_nibble(s[i * 3 + 1]);
		if (hi < 0 || lo < 0 || (i < 5 && s[i * 3 + 2] != ':')) return -1;
		mac[i] = (om_u8)((hi << 4) | lo);
		zero &= mac[i] == 0; ff &= mac[i] == 0xff;
	}
	return (mac[0] & 1U) || zero || ff ? -1 : 0;
}

static void om_parse_env(const om_u8 *raw, struct om_identity *id)
{
	om_word off = 4;
	om_memzero(id, sizeof(*id));
	id->crc_valid = om_load_le32(raw) == om_crc32(raw + 4, OM_ENV_CRC_END - 4);
	if (!id->crc_valid) return;
	while (off < OM_ENV_CRC_END) {
		om_word start = off, eq = 0;
		while (off < OM_ENV_CRC_END && raw[off]) { if (raw[off] == '=' && !eq) eq = off; off++; }
		if (off == start) break;
		if (off >= OM_ENV_CRC_END || !eq) return;
		if (eq - start == 8 && !om_memcmp(raw + start, "wifiaddr", 8)) {
			om_u8 parsed[6];
			id->wifi_count++;
			if (om_parse_mac((const char *)raw + eq + 1, off - eq - 1, parsed)) id->wifi_count = -1;
			else om_memcpy(id->wifi, parsed, 6);
		}
		off++;
	}
}

static int om_contains_compatible(const char *data, om_word n)
{
	om_word off = 0, target_len = om_strlen("mitrastar,hgw-500bna-qcv2");
	while (off < n) {
		om_word end = off;
		while (end < n && data[end]) end++;
		if (end - off == target_len && !om_memcmp(data + off, "mitrastar,hgw-500bna-qcv2", target_len)) return 1;
		if (end == n) break;
		off = end + 1;
	}
	return 0;
}

static int om_hex(char c)
{
	int n = om_nibble(c);
	return n < 0 ? -1 : n;
}

static int om_find_mtd(const char *data, om_word n, const char *wanted, char id[16])
{
	om_word i = 0, wanted_len = om_strlen(wanted);
	while (i + 5 < n) {
		om_word p = i, size = 0, erase = 0, label_start, label_end;
		om_word digit_start, digit_end, out;
		int h;
		while (p < n && data[p] != '\n') p++;
		if (i + 3 < p && data[i] == 'm' && data[i + 1] == 't' && data[i + 2] == 'd') {
			om_word q = i + 3;
			digit_start = q;
			while (q < p && data[q] >= '0' && data[q] <= '9') q++;
			digit_end = q;
			if (digit_end > digit_start && digit_end - digit_start <= 10 && q < p && data[q++] == ':') {
				while (q < p && data[q] == ' ') q++;
				while (q < p && (h = om_hex(data[q])) >= 0) { size = (size << 4) | (om_word)h; q++; }
				while (q < p && data[q] == ' ') q++;
				while (q < p && (h = om_hex(data[q])) >= 0) { erase = (erase << 4) | (om_word)h; q++; }
				while (q < p && data[q] != '"') q++;
				label_start = ++q; while (q < p && data[q] != '"') q++; label_end = q;
				if (size == OM_ENV_SIZE && erase == OM_ENV_SIZE && label_end - label_start == wanted_len &&
					!om_memcmp(data + label_start, wanted, wanted_len)) {
					id[0]='m'; id[1]='t'; id[2]='d'; out=3;
					while (digit_start < digit_end) id[out++] = data[digit_start++];
					id[out]=0;
					return 0;
				}
			}
		}
		i = p + 1;
	}
	return -1;
}

static char *om_append(char *out, const char *s)
{
	while (*s) *out++ = *s++;
	return out;
}

static int om_sysfs_contract(const char *id, const char *label)
{
	char value[64]; long n; char *p;
	p = om_append(om_path, "/sys/class/mtd/"); p = om_append(p, id); p = om_append(p, "/name"); *p = 0;
	n = om_read_all(om_path, value, sizeof(value) - 1); if (n <= 0) return 0; value[n] = 0; while (n && (value[n-1]=='\n'||value[n-1]=='\r')) value[--n]=0; if (!om_streq(value,label)) return 0;
	p = om_append(om_path, "/sys/class/mtd/"); p = om_append(p, id); p = om_append(p, "/type"); *p = 0;
	n = om_read_all(om_path, value, sizeof(value) - 1); if (n <= 0) return 0; value[n] = 0; while (n && (value[n-1]=='\n'||value[n-1]=='\r')) value[--n]=0; if (!om_streq(value,"rom")) return 0;
	p = om_append(om_path, "/sys/class/mtd/"); p = om_append(p, id); p = om_append(p, "/size"); *p = 0;
	n = om_read_all(om_path, value, sizeof(value) - 1); if (n <= 0) return 0; value[n] = 0; while (n && (value[n-1]=='\n'||value[n-1]=='\r')) value[--n]=0; return om_streq(value,"65536");
}

static int om_read_mtd(const char *id, om_u8 *raw)
{
	char *p = om_append(om_path, "/dev/");
	p = om_append(p, id); *p = 0;
	return om_read_all(om_path, raw, OM_ENV_SIZE) == OM_ENV_SIZE ? 0 : -1;
}

static int om_mkdir(const char *path, long mode)
{
	long rc = om_syscall3(OM_NR_MKDIRAT, OM_AT_FDCWD, (long)path, mode);
	return rc == 0 || rc == -OM_EEXIST ? 0 : -1;
}

static int om_publish(const char *tmp, const char *final, const char *data, om_word length)
{
	long fd, rc;
	om_syscall3(OM_NR_UNLINKAT, OM_AT_FDCWD, (long)tmp, 0);
	fd = om_syscall4(OM_NR_OPENAT, OM_AT_FDCWD, (long)tmp,
		OM_O_WRONLY | OM_O_CREAT | OM_O_TRUNC | OM_O_CLOEXEC, 0600);
	if (fd < 0) return -1;
	om_puts_fd((int)fd, data);
	rc = om_syscall2(OM_NR_FCHMOD, fd, 0600);
	if (!rc) rc = om_syscall1(OM_NR_FSYNC, fd);
	om_syscall1(OM_NR_CLOSE, fd);
	if (rc < 0) return -1;
	return om_syscall4(OM_NR_RENAMEAT, OM_AT_FDCWD, (long)tmp, OM_AT_FDCWD, (long)final) < 0 ? -1 : 0;
}

__attribute__((used, noinline, noreturn))
void om_bootenv_main(om_word *stack)
{
	struct om_identity primary, backup;
	char compatible[512], wifi[19];
	long compatible_n, proc_n;
	char primary_id[16], backup_id[16];
	static const char ready[] = "schema=openmitrastar.bootenv-wifiaddr/v1\nsource=mtd1+mtd2-redundant-readonly\nprimary_crc=valid\nbackup_crc=valid\ncopies=match\nkey=wifiaddr\nsecrets=redacted\n";
	static const char hex[] = "0123456789abcdef";
	unsigned int i;

	if (stack[0] != 1) om_refuse("arguments", 2);
	compatible_n = om_read_all("/proc/device-tree/compatible", compatible, sizeof(compatible));
	if (compatible_n <= 0 || !om_contains_compatible(compatible, (om_word)compatible_n)) om_refuse("target", 3);
	proc_n = om_read_all("/proc/mtd", om_proc_mtd, sizeof(om_proc_mtd));
	if (proc_n <= 0) om_refuse("proc-mtd", 4);
	if (om_find_mtd(om_proc_mtd, (om_word)proc_n, "uboot_env", primary_id) ||
		om_find_mtd(om_proc_mtd, (om_word)proc_n, "uboot_env_bak", backup_id)) om_refuse("mtd-labels", 5);
	if (!om_sysfs_contract(primary_id, "uboot_env") || !om_sysfs_contract(backup_id, "uboot_env_bak")) om_refuse("mtd-rom-contract", 6);
	if (om_read_mtd(primary_id, om_primary) || om_read_mtd(backup_id, om_backup)) om_refuse("mtd-read", 7);
	om_parse_env(om_primary, &primary); om_parse_env(om_backup, &backup);
	if (!primary.crc_valid || !backup.crc_valid) om_refuse("crc", 8);
	if (primary.wifi_count != 1 || backup.wifi_count != 1) om_refuse("wifiaddr-count", 9);
	if (om_memcmp(primary.wifi, backup.wifi, 6)) om_refuse("redundant-wifiaddr-mismatch", 10);
	if (om_mkdir("/run/openmitrastar", 0755) || om_mkdir("/run/openmitrastar/bootenv", 0700)) om_refuse("runtime-dir", 11);
	for (i = 0; i < 6; i++) { wifi[i*3]=hex[primary.wifi[i]>>4]; wifi[i*3+1]=hex[primary.wifi[i]&15]; wifi[i*3+2]=i==5?'\n':':'; }
	wifi[18]=0;
	if (om_publish("/run/openmitrastar/bootenv/.wifiaddr.new", "/run/openmitrastar/bootenv/wifiaddr", wifi, 18) ||
		om_publish("/run/openmitrastar/bootenv/.ready.new", "/run/openmitrastar/bootenv/ready", ready, sizeof(ready)-1)) om_refuse("publish", 12);
	om_memzero(om_primary, sizeof(om_primary)); om_memzero(om_backup, sizeof(om_backup)); om_memzero(wifi, sizeof(wifi));
	om_puts_fd(1, "OMBOOTENV_READY source=mtd1+mtd2-redundant-readonly primary_crc=valid backup_crc=valid copies=match key=wifiaddr mode=0600 secrets=redacted\n");
	om_exit(0);
}

__asm__(
".global _start\n"
".type _start,@function\n"
"_start:\n"
"mov r0,sp\n"
"b om_bootenv_main\n"
".size _start,.-_start\n");
