// SPDX-License-Identifier: GPL-2.0-only
/* Read-only PCI BAR register inspector for OpenMitraStar RAM tests. */

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static unsigned long parse_number(const char *text)
{
	char *end;
	unsigned long value;

	errno = 0;
	value = strtoul(text, &end, 0);
	if (errno || !text[0] || *end) {
		fprintf(stderr, "invalid number: %s\n", text);
		exit(2);
	}
	return value;
}

int main(int argc, char **argv)
{
	const char *path;
	unsigned long offset;
	unsigned long width;
	uint32_t value = 0;
	ssize_t count;
	int fd;

	if (argc != 4) {
		fprintf(stderr, "usage: %s RESOURCE OFFSET WIDTH(8|16|32)\n", argv[0]);
		return 2;
	}
	path = argv[1];
	offset = parse_number(argv[2]);
	width = parse_number(argv[3]);
	if (width != 8 && width != 16 && width != 32) {
		fprintf(stderr, "unsupported width: %lu\n", width);
		return 2;
	}

	fd = open(path, O_RDONLY);
	if (fd < 0) {
		perror("open");
		return 3;
	}
	count = pread(fd, &value, width / 8, (off_t)offset);
	if (count != (ssize_t)(width / 8)) {
		if (count < 0)
			perror("pread");
		else
			fprintf(stderr, "short read: %ld\n", (long)count);
		close(fd);
		return 4;
	}
	close(fd);

	if (width == 8)
		value &= 0xff;
	else if (width == 16)
		value &= 0xffff;
	printf("PCI_RESOURCE_READ path=%s offset=0x%lx width=%lu value=0x%0*x\n",
	       path, offset, width, (int)(width / 4), value);
	return 0;
}
