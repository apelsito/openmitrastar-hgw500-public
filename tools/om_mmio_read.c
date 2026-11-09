#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	unsigned long addr;
	unsigned long page_size;
	off_t page_base;
	off_t page_off;
	void *mapping;
	volatile uint32_t *reg;
	char *end;
	int fd;

	if (argc != 2) {
		fprintf(stderr, "usage: %s ADDRESS\n", argv[0]);
		return 2;
	}
	errno = 0;
	addr = strtoul(argv[1], &end, 0);
	if (errno || *end || (addr & 3)) {
		fprintf(stderr, "invalid aligned address: %s\n", argv[1]);
		return 2;
	}
	page_size = (unsigned long)sysconf(_SC_PAGESIZE);
	page_base = (off_t)(addr & ~(page_size - 1));
	page_off = (off_t)(addr - (unsigned long)page_base);
	fd = open("/tmp/om-devmem", O_RDONLY | O_SYNC);
	if (fd < 0) {
		perror("open /tmp/om-devmem");
		return 1;
	}
	mapping = mmap(NULL, page_size, PROT_READ, MAP_SHARED, fd, page_base);
	if (mapping == MAP_FAILED) {
		perror("mmap");
		close(fd);
		return 1;
	}
	reg = (volatile uint32_t *)((char *)mapping + page_off);
	printf("MMIO_READ address=0x%08lx value=0x%08x\n", addr, *reg);
	munmap(mapping, page_size);
	close(fd);
	return 0;
}
