// SPDX-License-Identifier: GPL-2.0-only
/* Minimal init_module/finit_module loader for the RAM-only ARC rescue image. */
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

static int load_with_init_module(int fd, const char *params)
{
	struct stat st;
	void *image;
	long rc;

	if (fstat(fd, &st) < 0) {
		perror("fstat");
		return 1;
	}
	if (st.st_size <= 0) {
		fprintf(stderr, "module is empty\n");
		return 1;
	}
	image = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
	if (image == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	rc = syscall(SYS_init_module, image, (unsigned long)st.st_size, params);
	if (rc < 0) {
		fprintf(stderr, "init_module: %s\n", strerror(errno));
		munmap(image, (size_t)st.st_size);
		return 1;
	}
	munmap(image, (size_t)st.st_size);
	return 0;
}

int main(int argc, char **argv)
{
	const char *params = "";
	int fd;

	if (argc < 2 || argc > 3) {
		fprintf(stderr, "usage: %s module.ko [parameters]\n", argv[0]);
		return 2;
	}
	if (argc == 3)
		params = argv[2];
	fd = open(argv[1], O_RDONLY | O_CLOEXEC);
	if (fd < 0) {
		perror(argv[1]);
		return 1;
	}

#ifdef SYS_finit_module
	if (syscall(SYS_finit_module, fd, params, 0) == 0) {
		close(fd);
		return 0;
	}
	if (errno != ENOSYS) {
		fprintf(stderr, "finit_module: %s\n", strerror(errno));
		close(fd);
		return 1;
	}
	lseek(fd, 0, SEEK_SET);
#endif

	argc = load_with_init_module(fd, params);
	close(fd);
	return argc;
}
