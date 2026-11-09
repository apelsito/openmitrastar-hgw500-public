// SPDX-License-Identifier: GPL-2.0-only
/* ARC700 syscall-only bridge FDB reader; no libc, CRT, TLS or atomics. */

typedef unsigned char om_u8;
typedef unsigned int om_u32;
typedef unsigned long om_word;

#define OM_AT_FDCWD (-100)
#define OM_O_RDONLY 0
#define OM_O_CLOEXEC 02000000
#define OM_NR_OPENAT 56
#define OM_NR_CLOSE 57
#define OM_NR_READ 63
#define OM_NR_WRITE 64
#define OM_NR_EXIT 93
#define OM_FDB_RECORD_SIZE 16U

static om_u8 om_fdb[4096];
static char om_line[256];

static long om_syscall1(long number, long arg0)
{
	register long r0 __asm__("r0") = arg0;
	register long r8 __asm__("r8") = number;
	__asm__ volatile("trap0" : "+r"(r0) : "r"(r8) : "memory");
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
	while (s[n])
		n++;
	return n;
}

static int om_streq(const char *a, const char *b)
{
	while (*a && *a == *b) {
		a++;
		b++;
	}
	return *a == *b;
}

static int om_memcmp(const om_u8 *a, const om_u8 *b, om_word n)
{
	while (n--) {
		if (*a != *b)
			return *a - *b;
		a++;
		b++;
	}
	return 0;
}

static void om_puts_fd(int fd, const char *s)
{
	om_word left = om_strlen(s);
	while (left) {
		long rc = om_syscall3(OM_NR_WRITE, fd, (long)s, left);
		if (rc <= 0)
			return;
		s += rc;
		left -= (om_word)rc;
	}
}

__attribute__((noreturn)) static void om_exit(long status)
{
	om_syscall1(OM_NR_EXIT, status);
	for (;;)
		__asm__ volatile("nop");
}

__attribute__((noreturn)) static void om_refuse(const char *reason, long status)
{
	om_puts_fd(2, "OMFDB_REFUSED reason=");
	om_puts_fd(2, reason);
	om_puts_fd(2, "\n");
	om_exit(status);
}

static long om_read_file(const char *path, void *buffer, om_word capacity)
{
	long fd = om_syscall4(OM_NR_OPENAT, OM_AT_FDCWD, (long)path,
			      OM_O_RDONLY | OM_O_CLOEXEC, 0);
	om_word done = 0;

	if (fd < 0)
		return fd;
	while (done < capacity) {
		long rc = om_syscall3(OM_NR_READ, fd,
				      (long)((om_u8 *)buffer + done), capacity - done);
		if (rc < 0) {
			om_syscall1(OM_NR_CLOSE, fd);
			return rc;
		}
		if (!rc)
			break;
		done += (om_word)rc;
	}
	om_syscall1(OM_NR_CLOSE, fd);
	return (long)done;
}

static int om_nibble(char c)
{
	if (c >= '0' && c <= '9')
		return c - '0';
	if (c >= 'a' && c <= 'f')
		return c - 'a' + 10;
	if (c >= 'A' && c <= 'F')
		return c - 'A' + 10;
	return -1;
}

static int om_parse_mac(const char *s, om_u8 mac[6])
{
	unsigned int i;

	if (om_strlen(s) != 17)
		return -1;
	for (i = 0; i < 6; i++) {
		int hi = om_nibble(s[i * 3]);
		int lo = om_nibble(s[i * 3 + 1]);
		if (hi < 0 || lo < 0 || (i < 5 && s[i * 3 + 2] != ':'))
			return -1;
		mac[i] = (om_u8)((hi << 4) | lo);
	}
	return 0;
}

static om_u32 om_load_le32(const om_u8 *p)
{
	return (om_u32)p[0] | ((om_u32)p[1] << 8) |
		((om_u32)p[2] << 16) | ((om_u32)p[3] << 24);
}

static char *om_append(char *out, const char *text)
{
	while (*text)
		*out++ = *text++;
	return out;
}

static char *om_append_u32(char *out, om_u32 value)
{
	char digits[10];
	unsigned int count = 0;

	if (!value) {
		*out++ = '0';
		return out;
	}
	while (value) {
		om_u32 quotient = 0, remainder = 0;
		int bit;

		for (bit = 31; bit >= 0; bit--) {
			remainder = (remainder << 1) | ((value >> bit) & 1U);
			if (remainder >= 10U) {
				remainder -= 10U;
				quotient |= 1U << bit;
			}
		}
		digits[count++] = (char)('0' + remainder);
		value = quotient;
	}
	while (count)
		*out++ = digits[--count];
	return out;
}

static char *om_append_mac(char *out, const om_u8 *mac)
{
	static const char hex[] = "0123456789abcdef";
	unsigned int i;

	for (i = 0; i < 6; i++) {
		*out++ = hex[mac[i] >> 4];
		*out++ = hex[mac[i] & 15];
		if (i != 5)
			*out++ = ':';
	}
	return out;
}

static int om_parse_port_no(const char *path)
{
	char text[32];
	long length = om_read_file(path, text, sizeof(text) - 1);
	om_u32 value = 0;
	om_word pos = 0;
	int base = 10;

	if (length <= 0)
		return -1;
	text[length] = 0;
	if (length >= 2 && text[0] == '0' && (text[1] == 'x' || text[1] == 'X')) {
		base = 16;
		pos = 2;
	}
	for (; pos < (om_word)length; pos++) {
		int digit;
		if (text[pos] == '\n' || text[pos] == '\r')
			break;
		digit = om_nibble(text[pos]);
		if (digit < 0 || digit >= base)
			return -1;
		value = value * (om_u32)base + (om_u32)digit;
	}
	return (int)value;
}

static const char *om_port_name(unsigned int port_no, int eth_port, int wifi_port)
{
	if ((int)port_no == eth_port)
		return "eth0";
	if ((int)port_no == wifi_port)
		return "wlan0";
	return "unknown";
}

__attribute__((used, noinline, noreturn))
void om_fdb_main(om_word *stack)
{
	om_word argc = stack[0];
	char **argv = (char **)&stack[1];
	om_u8 wanted[6];
	long length;
	om_word off;
	om_u32 records = 0, matches = 0;
	int lookup;
	int eth_port, wifi_port;

	if (argc != 3 && argc != 4)
		om_refuse("usage-dump-or-lookup", 2);
	lookup = om_streq(argv[1], "lookup");
	if ((!lookup && !om_streq(argv[1], "dump")) || !om_streq(argv[2], "br0"))
		om_refuse("only-br0-dump-or-lookup", 2);
	if (lookup) {
		if (argc != 4 || om_parse_mac(argv[3], wanted))
			om_refuse("invalid-mac", 2);
	} else if (argc != 3) {
		om_refuse("dump-takes-no-mac", 2);
	}

	length = om_read_file("/sys/class/net/br0/brforward", om_fdb,
			      sizeof(om_fdb));
	if (length < 0)
		om_refuse("brforward-open", 1);
	if ((om_word)length % OM_FDB_RECORD_SIZE)
		om_refuse("brforward-record-size", 1);
	eth_port = om_parse_port_no("/sys/class/net/br0/brif/eth0/port_no");
	wifi_port = om_parse_port_no("/sys/class/net/br0/brif/wlan0/port_no");

	for (off = 0; off < (om_word)length; off += OM_FDB_RECORD_SIZE) {
		const om_u8 *entry = om_fdb + off;
		unsigned int port = entry[6] | ((unsigned int)entry[12] << 8);
		char *out;

		records++;
		if (lookup && om_memcmp(entry, wanted, 6))
			continue;
		matches++;
		out = om_append(om_line, "OMFDB bridge=br0 mac=");
		out = om_append_mac(out, entry);
		out = om_append(out, " port_no=");
		out = om_append_u32(out, port);
		out = om_append(out, " port=");
		out = om_append(out, om_port_name(port, eth_port, wifi_port));
		out = om_append(out, " local=");
		out = om_append_u32(out, entry[7] ? 1U : 0U);
		out = om_append(out, " age_ticks=");
		out = om_append_u32(out, om_load_le32(entry + 8));
		*out++ = '\n';
		*out = 0;
		om_puts_fd(1, om_line);
	}

	{
		char *out = om_append(om_line, "OMFDB_SUM bridge=br0 records=");
		out = om_append_u32(out, records);
		out = om_append(out, " matches=");
		out = om_append_u32(out, matches);
		out = om_append(out, " record_size=16 runtime=arc700-nolibc-readonly\n");
		*out = 0;
		om_puts_fd(1, om_line);
	}
	om_exit(lookup && !matches ? 3 : 0);
}

__asm__(
".global _start\n"
".type _start,@function\n"
"_start:\n"
"mov r0, sp\n"
"bl om_fdb_main\n"
"nop\n"
);
