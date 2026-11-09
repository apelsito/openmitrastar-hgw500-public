#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#define TOPAZ_SYSCTL_BASE 0xe0000000UL
#define TOPAZ_LHOST_INT_EN 0x4cUL
#define TOPAZ_IRQ_GATE_BASE 5U

int main(int argc, char **argv)
{
	unsigned long irq;
	unsigned long page_size;
	off_t page_base;
	off_t page_off;
	volatile uint32_t *reg;
	void *mapping;
	uint32_t before;
	uint32_t after;
	char *end;
	int fd;

	if (argc != 2) {
		fprintf(stderr, "usage: %s IRQ\n", argv[0]);
		return 2;
	}
	errno = 0;
	irq = strtoul(argv[1], &end, 0);
	if (errno || *end || irq < TOPAZ_IRQ_GATE_BASE || irq > 31) {
		fprintf(stderr, "invalid IRQ: %s\n", argv[1]);
		return 2;
	}

	page_size = (unsigned long)sysconf(_SC_PAGESIZE);
	page_base = (off_t)((TOPAZ_SYSCTL_BASE + TOPAZ_LHOST_INT_EN) &
			    ~(page_size - 1));
	page_off = (off_t)((TOPAZ_SYSCTL_BASE + TOPAZ_LHOST_INT_EN) -
			   (unsigned long)page_base);
	fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("open /dev/mem");
		return 1;
	}
	mapping = mmap(NULL, page_size, PROT_READ | PROT_WRITE, MAP_SHARED,
		       fd, page_base);
	if (mapping == MAP_FAILED) {
		perror("mmap /dev/mem");
		close(fd);
		return 1;
	}
	reg = (volatile uint32_t *)((char *)mapping + page_off);
	before = *reg;
	after = before | (UINT32_C(1) << (irq - TOPAZ_IRQ_GATE_BASE));
	*reg = after;
	__sync_synchronize();
	after = *reg;
	printf("TOPAZ_IRQ_GATE irq=%lu before=%08x after=%08x mask=%08x\n",
	       irq, before, after,
	       UINT32_C(1) << (irq - TOPAZ_IRQ_GATE_BASE));
	munmap(mapping, page_size);
	close(fd);
	return 0;
}
