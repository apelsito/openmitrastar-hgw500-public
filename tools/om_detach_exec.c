// SPDX-License-Identifier: GPL-2.0-only
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static int allowed_log(const char *path)
{
	static const char runtime_prefix[] = "/run/openmitrastar/config/";
	static const char test_prefix[] = "/tmp/openmitrastar-config-test/";

	if (!path || strstr(path, ".."))
		return 0;
	return !strncmp(path, runtime_prefix, sizeof(runtime_prefix) - 1) ||
		!strncmp(path, test_prefix, sizeof(test_prefix) - 1);
}

static void close_inherited_fds(int keep_fd)
{
	long limit = sysconf(_SC_OPEN_MAX);
	int fd;

	if (limit < 0 || limit > 4096)
		limit = 1024;
	for (fd = STDERR_FILENO + 1; fd < limit; ++fd) {
		if (fd != keep_fd)
			close(fd);
	}
}

int main(int argc, char **argv)
{
	int status_pipe[2];
	int null_fd;
	int log_fd;
	int child_status;
	int exec_errno = 0;
	ssize_t count;
	pid_t child;

	if (argc < 3 || !allowed_log(argv[1]) || argv[2][0] != '/') {
		fprintf(stderr, "usage: om-detach-exec /run/openmitrastar/config/<log> /absolute/program [args...]\n");
		return 2;
	}
	null_fd = open("/dev/null", O_RDONLY);
	if (null_fd < 0)
		return 3;
	log_fd = open(argv[1], O_WRONLY | O_CREAT | O_APPEND, 0600);
	if (log_fd < 0)
		return 4;
	fchmod(log_fd, 0600);
	if (pipe(status_pipe) < 0)
		return 5;
	fcntl(status_pipe[1], F_SETFD,
	      fcntl(status_pipe[1], F_GETFD) | FD_CLOEXEC);

	child = fork();
	if (child < 0)
		return 6;
	if (child == 0) {
		pid_t grandchild;

		close(status_pipe[0]);
		if (setsid() < 0) {
			exec_errno = errno;
			write(status_pipe[1], &exec_errno, sizeof(exec_errno));
			_exit(126);
		}
		grandchild = fork();
		if (grandchild < 0) {
			exec_errno = errno;
			write(status_pipe[1], &exec_errno, sizeof(exec_errno));
			_exit(126);
		}
		if (grandchild > 0)
			_exit(0);

		umask(077);
		chdir("/");
		dup2(null_fd, STDIN_FILENO);
		dup2(log_fd, STDOUT_FILENO);
		dup2(log_fd, STDERR_FILENO);
		if (null_fd > STDERR_FILENO && null_fd != status_pipe[1])
			close(null_fd);
		if (log_fd > STDERR_FILENO && log_fd != status_pipe[1])
			close(log_fd);
		close_inherited_fds(status_pipe[1]);
		execve(argv[2], &argv[2], environ);
		exec_errno = errno;
		write(status_pipe[1], &exec_errno, sizeof(exec_errno));
		_exit(127);
	}

	close(status_pipe[1]);
	close(null_fd);
	close(log_fd);
	while (waitpid(child, &child_status, 0) < 0 && errno == EINTR)
		;
	count = read(status_pipe[0], &exec_errno, sizeof(exec_errno));
	close(status_pipe[0]);
	if (count > 0) {
		fprintf(stderr, "OM_DETACH_EXEC_FAIL errno=%d\n", exec_errno);
		return 7;
	}
	if (!WIFEXITED(child_status) || WEXITSTATUS(child_status) != 0)
		return 8;
	return 0;
}
