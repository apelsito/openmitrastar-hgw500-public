typedef unsigned long omt_size_t;

static const char boot_marker[] =
    "OPENMITRASTAR_INIT_OK Linux 5.10 ARC700 userspace\n";

static long omt_write(int fd, const void *buffer, omt_size_t length)
{
    register long r0 __asm__("r0") = fd;
    register const void *r1 __asm__("r1") = buffer;
    register omt_size_t r2 __asm__("r2") = length;
    register long r8 __asm__("r8") = 64;

    __asm__ volatile(
        "trap0"
        : "+r"(r0)
        : "r"(r1), "r"(r2), "r"(r8)
        : "memory");

    return r0;
}

__attribute__((noreturn)) void _start(void)
{
    omt_write(1, boot_marker, sizeof(boot_marker) - 1);

    for (;;) {
        __asm__ volatile("nop");
    }
}
