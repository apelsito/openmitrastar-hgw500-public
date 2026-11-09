// SPDX-License-Identifier: GPL-2.0-only
/* ARC700 finit_module diagnostic loader, no libc/runtime. */

typedef unsigned long om_word;

#define OM_NR_OPENAT 56
#define OM_NR_CLOSE 57
#define OM_NR_WRITE 64
#define OM_NR_EXIT 93
#define OM_NR_FINIT_MODULE 273
#define OM_AT_FDCWD (-100)
#define OM_O_RDONLY 0
#define OM_O_CLOEXEC 02000000

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

	__asm__ volatile("trap0" : "+r"(r0)
			 : "r"(r1), "r"(r2), "r"(r8) : "memory");
	return r0;
}

static long om_syscall4(long number, long arg0, long arg1, long arg2,
			long arg3)
{
	register long r0 __asm__("r0") = arg0;
	register long r1 __asm__("r1") = arg1;
	register long r2 __asm__("r2") = arg2;
	register long r3 __asm__("r3") = arg3;
	register long r8 __asm__("r8") = number;

	__asm__ volatile("trap0" : "+r"(r0)
			 : "r"(r1), "r"(r2), "r"(r3), "r"(r8) : "memory");
	return r0;
}

static om_word om_strlen(const char *text)
{
	om_word length = 0;

	while (text[length])
		++length;
	return length;
}

static void om_puts(const char *text)
{
	om_syscall3(OM_NR_WRITE, 1, (long)text, (long)om_strlen(text));
}

static int om_emit_digit(char *out, om_word *pos, unsigned long *value,
			 unsigned long place, int started)
{
	char digit = '0';

	while (*value >= place) {
		*value -= place;
		++digit;
	}
	if (digit != '0' || started || place == 1) {
		out[*pos] = digit;
		++*pos;
		started = 1;
	}
	return started;
}

static void om_put_uint_small(unsigned long value)
{
	char out[5];
	om_word pos = 0;
	int started = 0;

	started = om_emit_digit(out, &pos, &value, 1000, started);
	started = om_emit_digit(out, &pos, &value, 100, started);
	started = om_emit_digit(out, &pos, &value, 10, started);
	om_emit_digit(out, &pos, &value, 1, started);
	om_syscall3(OM_NR_WRITE, 1, (long)out, (long)pos);
}

static void om_put_long(long value)
{
	if (value < 0) {
		om_puts("-");
		value = -value;
	}
	om_put_uint_small((unsigned long)value);
}

__attribute__((noreturn)) static void om_exit(long status)
{
	om_syscall1(OM_NR_EXIT, status);
	for (;;)
		__asm__ volatile("nop");
}

__attribute__((used, noinline, noreturn))
void ram_insmod_main(om_word *stack)
{
	om_word argc = stack[0];
	char **argv = (char **)&stack[1];
	const char *params = "";
	long fd;
	long result;

	if (argc < 2 || argc > 3) {
		om_puts("RAM_INSMOD_USAGE module.ko [parameters]\n");
		om_exit(2);
	}
	if (argc == 3)
		params = argv[2];

	fd = om_syscall4(OM_NR_OPENAT, OM_AT_FDCWD, (long)argv[1],
			 OM_O_RDONLY | OM_O_CLOEXEC, 0);
	if (fd < 0) {
		om_puts("RAM_INSMOD_OPEN_FAIL rc=");
		om_put_long(fd);
		om_puts("\n");
		om_exit(1);
	}

	result = om_syscall3(OM_NR_FINIT_MODULE, fd, (long)params, 0);
	om_syscall1(OM_NR_CLOSE, fd);
	if (result < 0) {
		om_puts("RAM_INSMOD_LOAD_FAIL rc=");
		om_put_long(result);
		om_puts("\n");
		om_exit(1);
	}

	om_puts("RAM_INSMOD_OK\n");
	om_exit(0);
}

__asm__(
".global _start\n"
".type _start,@function\n"
"_start:\n"
"mov r0,sp\n"
"b ram_insmod_main\n"
".size _start,.-_start\n");
