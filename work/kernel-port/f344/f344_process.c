/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "f344_native.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
uint64_t f344_now_ms(void) {
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t))
    return 0;
  return (uint64_t)t.tv_sec * 1000U + (unsigned)t.tv_nsec / 1000000U;
}
int f344_run(char *const argv[], char *out, size_t capacity,
             uint64_t deadline) {
  int pipefd[2], status = 0, rc = -1;
  pid_t pid;
  size_t used = 0;
  bool exited = false, eof = false;
  if (!out || capacity < 2 || pipe(pipefd))
    return -1;
  out[0] = 0;
  pid = fork();
  if (pid < 0) {
    close(pipefd[0]);
    close(pipefd[1]);
    return -1;
  }
  if (!pid) {
    int nullfd = open("/dev/null", O_RDWR);
    setpgid(0, 0);
    dup2(nullfd, 0);
    dup2(pipefd[1], 1);
    dup2(nullfd, 2);
    close(pipefd[0]);
    close(pipefd[1]);
    if (nullfd > 2)
      close(nullfd);
    execvp(argv[0], argv);
    _exit(127);
  }
  setpgid(pid, pid);
  close(pipefd[1]);
  fcntl(pipefd[0], F_SETFL, O_NONBLOCK);
  for (;;) {
    uint64_t now = f344_now_ms();
    if (!now || now >= deadline)
      break;
    ssize_t n = read(pipefd[0], out + used, capacity - 1 - used);
    if (n > 0) {
      used += (size_t)n;
      if (used == capacity - 1) {
        errno = EOVERFLOW;
        goto done;
      }
    } else if (n == 0)
      eof = true;
    else if (errno != EAGAIN && errno != EINTR)
      goto done;
    if (!exited) {
      pid_t got = waitpid(pid, &status, WNOHANG);
      if (got == pid)
        exited = true;
      else if (got < 0)
        goto done;
    }
    if (exited && eof) {
      rc = WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : -1;
      goto done;
    }
    {
      struct pollfd p = {pipefd[0], POLLIN, 0};
      poll(&p, 1, 10);
    }
  }
  errno = ETIMEDOUT;
done:
  out[used] = 0;
  close(pipefd[0]);
  /* A reaped leader can still have descendants holding the output pipe.
   * Every failure retires its owned process group, not just the leader. */
  if (rc)
    kill(-pid, SIGKILL);
  if (!exited) {
    while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {
    }
  }
  return rc;
}
int f344_write_file(const char *path, const void *data, size_t length,
                    unsigned mode) {
  int fd;
  size_t done = 0;
  struct stat st;
  fd = open(path, O_WRONLY | O_CREAT | O_NOFOLLOW | O_CLOEXEC, (mode_t)mode);
  if (fd < 0)
    return -1;
  if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != 0 ||
      st.st_nlink != 1 || fchmod(fd, (mode_t)mode) || ftruncate(fd, 0)) {
    close(fd);
    return -1;
  }
  while (done < length) {
    ssize_t n = write(fd, (const char *)data + done, length - done);
    if (n < 0 && errno == EINTR)
      continue;
    if (n <= 0) {
      close(fd);
      return -1;
    }
    done += (size_t)n;
  }
  if (fsync(fd)) {
    close(fd);
    return -1;
  }
  return close(fd);
}
int f344_read_file(const char *path, void *data, size_t cap, size_t *length,
                   bool private_file) {
  int fd;
  struct stat st;
  size_t used = 0;
  fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
  if (fd < 0)
    return -1;
  if (fstat(fd, &st) || !S_ISREG(st.st_mode) ||
      (private_file && (st.st_uid != 0 || (st.st_mode & 0777) != 0600))) {
    close(fd);
    return -1;
  }
  for (;;) {
    ssize_t n;
    if (used == cap) {
      char extra;
      n = read(fd, &extra, 1);
      if (n < 0 && errno == EINTR)
        continue;
      if (n == 0)
        break;
      close(fd);
      errno = EOVERFLOW;
      return -1;
    }
    n = read(fd, (char *)data + used, cap - used);
    if (n < 0 && errno == EINTR)
      continue;
    if (n < 0) {
      close(fd);
      return -1;
    }
    if (!n)
      break;
    used += (size_t)n;
  }
  close(fd);
  *length = used;
  return 0;
}
int f344_pid_start(pid_t pid, uint64_t *start) {
  char path[64], data[2048], *right, *save, *word, *end;
  size_t length;
  unsigned field;
  unsigned long long value;
  if (pid <= 1)
    return -1;
  snprintf(path, sizeof(path), "/proc/%ld/stat", (long)pid);
  if (f344_read_file(path, data, sizeof(data) - 1, &length, false))
    return -1;
  data[length] = 0;
  right = strrchr(data, ')');
  if (!right) {
    errno = EINVAL;
    return -1;
  }
  word = strtok_r(right + 1, " ", &save);
  if (word && (word[0] == 'Z' || word[0] == 'X')) {
    errno = ESRCH;
    return -1;
  }
  for (field = 3; word && field < 22; field++)
    word = strtok_r(0, " ", &save);
  if (!word || field != 22) {
    errno = EINVAL;
    return -1;
  }
  errno = 0;
  value = strtoull(word, &end, 10);
  if (errno || *end)
    return -1;
  *start = value;
  return 0;
}
int f344_daemon_request(const struct f344_daemon *d, const char *tool,
                        const char *iface, const char *command, char *out,
                        size_t size, uint64_t deadline) {
  uint64_t start;
  char *args[9];
  if (!d || d->pid <= 1 || f344_pid_start(d->pid, &start) ||
      start != d->start_ticks)
    return -1;
  args[0] = (char *)tool;
  args[1] = "-p";
  args[2] = (char *)d->control;
  args[3] = "-i";
  args[4] = (char *)iface;
  args[5] = (char *)command;
  args[6] = 0;
  return f344_run(args, out, size, deadline);
}
