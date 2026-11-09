/* SPDX-License-Identifier: GPL-2.0-only
 * Native Linux backend. It uses only the managed 5GHz interfaces and daemon
 * control sockets. No DHCP, Ethernet power, bootcfg or persistent flash write.
 */
#define _GNU_SOURCE
#include "f344_native.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/if_arp.h>
#include <linux/sockios.h>
#include <linux/wireless.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#define STATE_ROOT "/run/openmitrastar/f344"
#define AP_TOOL "/usr/sbin/hostapd-cli-qtn"
#define STA_TOOL "/usr/sbin/wpa_cli-f344"
#define AP_PROGRAM "/usr/sbin/hostapd-qtn"
#define STA_PROGRAM "/usr/sbin/wpa_supplicant-f344"
extern int sha256_vector(size_t, const uint8_t *[], const size_t *, uint8_t *);
struct registry {
  uint32_t magic, size, ready;
  uint64_t generation;
  char boot_id[37];
  struct f344_profile profile;
  struct f344_daemon ap, sta;
  uint8_t integrity[32];
};
static struct f344_native native;
static struct registry saved;
static int join_path(char *out, size_t capacity, const char *directory,
                     const char *suffix) {
  size_t left = strlen(directory), right = strlen(suffix);
  if (left + right + 1 > capacity)
    return -1;
  memcpy(out, directory, left);
  memcpy(out + left, suffix, right + 1);
  return 0;
}
static int config_digest(const char *path, uint8_t *digest) {
  char data[F344_CONFIG_MAX + 1536];
  size_t length;
  const uint8_t *parts[] = {(const uint8_t *)data};
  size_t sizes[1];
  int rc;
  if (f344_read_file(path, data, sizeof(data), &length, true))
    return -1;
  sizes[0] = length;
  rc = sha256_vector(1, parts, sizes, digest);
  memset(data, 0, sizeof(data));
  return rc;
}
static int boot_id(char *out) {
  char data[40];
  size_t length;
  if (f344_read_file("/proc/sys/kernel/random/boot_id", data, sizeof(data),
                     &length, false) ||
      length != 37 || data[36] != '\n')
    return -1;
  memcpy(out, data, 36);
  out[36] = 0;
  return 0;
}
static int control_write(const char *path, const char *text) {
  int fd = open(path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
  size_t length = strlen(text);
  ssize_t n;
  if (fd < 0)
    return -1;
  do {
    n = write(fd, text, length);
  } while (n < 0 && errno == EINTR);
  close(fd);
  return n == (ssize_t)length ? 0 : -1;
}
static int qdrv_command(const char *command) {
  char reply[64];
  size_t length;
  if (control_write("/sys/devices/qdrv/control", command) ||
      f344_read_file("/sys/devices/qdrv/control", reply, sizeof(reply) - 1,
                     &length, false))
    return -1;
  reply[length] = 0;
  return strcmp(reply, "ok\n") && strcmp(reply, "ok") ? -1 : 0;
}
static int text_field(const char *text, const char *key, const char *value) {
  size_t n = strlen(key), v = strlen(value);
  const char *p = text;
  while (*p) {
    const char *end = strchr(p, '\n');
    size_t len = end ? (size_t)(end - p) : strlen(p);
    if (len == n + 1 + v && !memcmp(p, key, n) && p[n] == '=' &&
        !memcmp(p + n + 1, value, v))
      return 1;
    if (!end)
      break;
    p = end + 1;
  }
  return 0;
}
static int ok_reply(const char *text) {
  return !strcmp(text, "OK\n") || !strcmp(text, "OK");
}
static int process_matches(const struct f344_daemon *d, const char *program) {
  char path[64], exe[768], args[4096];
  size_t length, at = 0;
  uint64_t ticks;
  ssize_t n;
  bool config = false;
  uint8_t digest[32];
  struct stat st;
  if (d->pid <= 1 || f344_pid_start(d->pid, &ticks) || ticks != d->start_ticks)
    return 0;
  snprintf(path, sizeof(path), "/proc/%ld/exe", (long)d->pid);
  n = readlink(path, exe, sizeof(exe) - 1);
  if (n < 0)
    return 0;
  exe[n] = 0;
  if (strcmp(exe, program))
    return 0;
  snprintf(path, sizeof(path), "/proc/%ld/cmdline", (long)d->pid);
  if (f344_read_file(path, args, sizeof(args), &length, false))
    return 0;
  while (at < length) {
    size_t part = strnlen(args + at, length - at);
    if (part == length - at)
      return 0;
    if (!strcmp(args + at, d->config))
      config = true;
    at += part + 1;
  }
  if (lstat(d->config, &st)) {
    if (errno != ENOENT || !d->bootstrap_unlink_allowed)
      return 0;
  } else if (config_digest(d->config, digest) ||
             memcmp(digest, d->loaded_config_digest, 32))
    return 0;
  return config;
}
static int profile_safe(const struct f344_profile *p) {
  return p->target.mode >= F344_MODE_AP &&
         p->target.mode <= F344_MODE_REPEATER && p->ap_ssid_len <= 32 &&
         p->sta_ssid_len <= 32 && p->ap_length < F344_CONFIG_MAX &&
         p->sta_length < F344_CONFIG_MAX && !p->ap_config[p->ap_length] &&
         !p->sta_config[p->sta_length] &&
         memchr(p->directory, 0, sizeof(p->directory));
}
static int registry_read(void) {
  size_t length;
  char current_boot[37];
  uint8_t digest[32];
  const uint8_t *parts[] = {(const uint8_t *)&saved};
  size_t sizes[] = {offsetof(struct registry, integrity)};
  if (f344_read_file(STATE_ROOT "/active.bin", &saved, sizeof(saved), &length,
                     true) ||
      length != sizeof(saved) || saved.magic != 0xf344ac71U ||
      saved.size != sizeof(saved) || !saved.generation ||
      !profile_safe(&saved.profile))
    return -1;
  if (saved.ready > 1 || sha256_vector(1, parts, sizes, digest) ||
      memcmp(digest, saved.integrity, 32))
    return -1;
  if (boot_id(current_boot) ||
      memcmp(current_boot, saved.boot_id, sizeof(current_boot)))
    return -1;
  if (!memchr(saved.ap.config, 0, sizeof(saved.ap.config)) ||
      !memchr(saved.ap.control, 0, sizeof(saved.ap.control)) ||
      !memchr(saved.sta.config, 0, sizeof(saved.sta.config)) ||
      !memchr(saved.sta.control, 0, sizeof(saved.sta.control)))
    return -1;
  return 0;
}
static int registry_write(const struct f344_profile *p,
                          const struct f344_daemon *ap,
                          const struct f344_daemon *sta, bool ready) {
  struct registry *r = calloc(1, sizeof(*r));
  int rc;
  const uint8_t *parts[1];
  size_t sizes[] = {offsetof(struct registry, integrity)};
  if (!r || saved.generation == UINT64_MAX) {
    free(r);
    return -1;
  }
  r->magic = 0xf344ac71U;
  r->size = sizeof(*r);
  r->ready = ready;
  r->generation = saved.generation + 1;
  r->profile = *p;
  r->ap = *ap;
  r->sta = *sta;
  if (boot_id(r->boot_id)) {
    free(r);
    return -1;
  }
  parts[0] = (const uint8_t *)r;
  if (sha256_vector(1, parts, sizes, r->integrity)) {
    memset(r, 0, sizeof(*r));
    free(r);
    return -1;
  }
  rc = f344_write_file(STATE_ROOT "/active.next", r, sizeof(*r), 0600);
  if (!rc)
    rc = rename(STATE_ROOT "/active.next", STATE_ROOT "/active.bin");
  memset(r, 0, sizeof(*r));
  free(r);
  return rc;
}
static int ssid_matches(struct f344_native *n, const char *name,
                        const uint8_t *ssid, size_t length) {
  struct iwreq wrq;
  uint8_t actual[33] = {0};
  memset(&wrq, 0, sizeof(wrq));
  strcpy(wrq.ifr_name, name);
  wrq.u.essid.pointer = actual;
  wrq.u.essid.length = 32;
  return !ioctl(n->socket_fd, SIOCGIWESSID, &wrq) &&
         wrq.u.essid.length == length && !memcmp(actual, ssid, length);
}
static int complete_observation(struct f344_native *n, struct f344_state *s) {
  const struct f344_profile *p = n->running_profile;
  char reply[4096];
  bool known = true, profile = true;
  memset(s, 0, sizeof(*s));
  if (f344_management(n, s) || f344_radio_observe(n, s))
    return -1;
  if (!s->topology.csa_known || s->topology.csa_pending)
    return 0;
  if (!p || !n->configuration_loaded || s->mode != p->target.mode)
    return 0;
  s->configured_bandwidth = p->target.bandwidth;
  if (p->target.mode != F344_MODE_STA) {
    const char *iface =
        p->target.mode == F344_MODE_REPEATER ? "wifi1" : "wifi0";
    if (!process_matches(&n->ap, AP_PROGRAM) ||
        f344_daemon_request(&n->ap, AP_TOOL, iface, "status", reply,
                            sizeof(reply), n->phase_deadline) ||
        !strstr(reply, "state="))
      known = false;
    else {
      s->ap_enabled = text_field(reply, "state", "ENABLED");
      if (s->ap_enabled && !ssid_matches(n, iface, p->ap_ssid, p->ap_ssid_len))
        profile = false;
    }
  }
  if (p->target.mode != F344_MODE_AP) {
    if (!process_matches(&n->sta, STA_PROGRAM) ||
        f344_daemon_request(&n->sta, STA_TOOL, "wifi0", "status", reply,
                            sizeof(reply), n->phase_deadline) ||
        !strstr(reply, "wpa_state="))
      known = false;
    else {
      s->upstream_completed = text_field(reply, "wpa_state", "COMPLETED");
      if (s->upstream_completed &&
          !ssid_matches(n, "wifi0", p->sta_ssid, p->sta_ssid_len))
        profile = false;
    }
  }
  if (known)
    s->valid |= 8;
  if (profile && known) {
    s->valid |= 16;
    memcpy(s->profile_digest, p->target.profile_digest, 32);
  }
  memset(reply, 0, sizeof(reply));
  return 0;
}
static int snapshot(void *context, struct f344_state *s) {
  struct f344_native *n = context;
  if (registry_read() || saved.ready != 1)
    return -1;
  n->original = saved.profile;
  n->ap = saved.ap;
  n->sta = saved.sta;
  n->running_profile = &n->original;
  n->configuration_loaded = true;
  if (complete_observation(n, s) || s->valid != F344_SNAPSHOT_VALID)
    return -1;
  s->snapshot_cookie = 1;
  n->before = *s;
  return 0;
}
static int inspect(void *context, struct f344_state *s) {
  struct f344_native *n = context;
  memset(s, 0, sizeof(*s));
  return f344_management(n, s);
}
static int stop_daemon(struct f344_native *n, struct f344_daemon *d,
                       const char *program, const char *tool,
                       const char *iface) {
  char reply[128];
  uint64_t ticks;
  int status;
  pid_t got;
  if (!d->pid)
    return 0;
  got = waitpid(d->pid, &status, WNOHANG);
  if (got == d->pid) {
    d->pid = 0;
    return 0;
  }
  if (f344_pid_start(d->pid, &ticks)) {
    if (errno == ENOENT || errno == ESRCH) {
      d->pid = 0;
      return 0;
    }
    return -1;
  }
  if (!process_matches(d, program) ||
      f344_daemon_request(d, tool, iface, "terminate", reply, sizeof(reply),
                          n->phase_deadline) ||
      !ok_reply(reply))
    return -1;
  while (f344_now_ms() && f344_now_ms() < n->phase_deadline) {
    struct timespec pause = {0, 10000000};
    int status;
    pid_t got = waitpid(d->pid, &status, WNOHANG);
    if (got == d->pid || f344_pid_start(d->pid, &ticks) ||
        ticks != d->start_ticks) {
      d->pid = 0;
      return 0;
    }
    nanosleep(&pause, 0);
  }
  return -1;
}
static int spawn_daemon(struct f344_native *n, struct f344_daemon *d,
                        const char *program, bool repeater) {
  pid_t pid;
  unsigned tries;
  if (config_digest(d->config, d->loaded_config_digest))
    return -1;
  pid = fork();
  if (pid < 0)
    return -1;
  if (!pid) {
    int null = open("/dev/null", O_RDWR);
    setpgid(0, 0);
    dup2(null, 0);
    dup2(null, 1);
    dup2(null, 2);
    if (null > 2)
      close(null);
    if (!strcmp(program, AP_PROGRAM))
      execl(program, program, "-q", d->config, (char *)0);
    else if (repeater)
      execl(program, program, "-q", "-iwifi0", "-bbr0", "-Dmadwifi", "-c",
            d->config, "-r", (char *)0);
    else
      execl(program, program, "-q", "-iwifi0", "-bbr0", "-Dmadwifi", "-c",
            d->config, (char *)0);
    _exit(127);
  }
  setpgid(pid, pid);
  d->pid = pid;
  for (tries = 0; tries < 100 && f344_now_ms() < n->phase_deadline; tries++) {
    struct timespec pause = {0, 1000000};
    if (!f344_pid_start(pid, &d->start_ticks))
      return 0;
    nanosleep(&pause, 0);
  }
  kill(-pid, SIGKILL);
  while (waitpid(pid, 0, 0) < 0 && errno == EINTR) {
  }
  d->pid = 0;
  return -1;
}
static int station_ready(struct f344_native *n, const struct f344_profile *p,
                         unsigned *frequency) {
  char reply[4096];
  for (;;) {
    struct timespec pause = {0, 100000000};
    struct f344_state observed = {0};
    uint64_t now = f344_now_ms();
    if (!now || now >= n->phase_deadline)
      return -1;
    if (process_matches(&n->sta, STA_PROGRAM) &&
        !f344_daemon_request(&n->sta, STA_TOOL, "wifi0", "status", reply,
                             sizeof(reply), n->phase_deadline) &&
        text_field(reply, "wpa_state", "COMPLETED") &&
        !f344_radio_observe(n, &observed) &&
        f344_mask_non_dfs(observed.channel_mask) &&
        ssid_matches(n, "wifi0", p->sta_ssid, p->sta_ssid_len)) {
      *frequency = observed.frequency_mhz;
      memset(reply, 0, sizeof(reply));
      return 0;
    }
    nanosleep(&pause, 0);
  }
}
static int run_private(struct f344_native *n, const char *command,
                       const char *value) {
  char reply[512];
  char *args[] = {"/usr/sbin/iwpriv-qtn", "wifi0", (char *)command,
                  (char *)value, 0};
  return f344_run(args, reply, sizeof(reply), n->phase_deadline);
}
static int private_readback(struct f344_native *n, const char *command,
                            unsigned expected) {
  char reply[512], *value, *end;
  char *args[] = {"/usr/sbin/iwpriv-qtn", "wifi0", (char *)command, 0};
  unsigned long actual;
  if (f344_run(args, reply, sizeof(reply), n->phase_deadline))
    return -1;
  value = strrchr(reply, ':');
  if (!value)
    return -1;
  errno = 0;
  actual = strtoul(value + 1, &end, 10);
  if (errno || end == value + 1)
    return -1;
  while (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r')
    end++;
  return *end || actual != expected ? -1 : 0;
}
static int execute(void *context, enum f344_action action,
                   const struct f344_target *t,
                   const struct f344_state *original, bool rollback) {
  struct f344_native *n = context;
  const struct f344_profile *p = rollback ? &n->original : &n->target;
  char command[256], reply[512];
  struct f344_state state = {0};
  uint64_t now = f344_now_ms();
  int rc;
  if (!now || now >= n->global_deadline)
    return -1;
  if (rollback && !n->rollback) {
    n->rollback = true;
    n->phase_deadline = now + 60000;
    if (n->phase_deadline > n->global_deadline)
      n->phase_deadline = n->global_deadline;
  }
  if (now >= n->phase_deadline)
    return -1;
  switch (action) {
  case F344_GUARD_MANAGEMENT: {
    struct ifreq ifr;
    memset(&ifr, 0, sizeof(ifr));
    strcpy(ifr.ifr_name, "br0");
    ifr.ifr_hwaddr.sa_family = ARPHRD_ETHER;
    memcpy(ifr.ifr_hwaddr.sa_data, n->management_mac, 6);
    if (ioctl(n->socket_fd, SIOCSIFHWADDR, &ifr))
      return -1;
    return control_write("/sys/module/qdrv/parameters/openmitrastar_mode_channel_hold",
                         "1\n");
  }
  case F344_STOP_SECURITY:
    if (stop_daemon(n, &n->ap, AP_PROGRAM, AP_TOOL,
                    n->running_profile && n->running_profile->target.mode ==
                                              F344_MODE_REPEATER
                        ? "wifi1"
                        : "wifi0"))
      return -1;
    if (stop_daemon(n, &n->sta, STA_PROGRAM, STA_TOOL, "wifi0"))
      return -1;
    n->configuration_loaded = false;
    return 0;
  case F344_DOWN_VAPS:
    if (f344_if_flags(n, "wifi1", false))
      return -1;
    if (f344_if_flags(n, "wifi0", false))
      return -1;
    return 0;
  case F344_CLOSE_OPEN_GATE:
    return control_write("/sys/module/qdrv/parameters/openmitrastar_rf_enable",
                         "0\n");
  case F344_DRAIN_CSA:
    for (;;) {
      struct f344_state state = {0};
      struct timespec pause = {0, 10000000};
      uint64_t now = f344_now_ms();
      int rc;
      if (!now || now >= n->phase_deadline || now >= n->global_deadline)
        return -1;
      rc = qdrv_command("mode 0 drain-csa\n");
      if (f344_layout_observe(&state) || !state.topology.csa_known ||
          !state.topology.channel_hold || state.topology.open_gate ||
          state.topology.primary_up || state.topology.secondary_up)
        return -1;
      if (!rc && state.topology.csa_drained && !state.topology.csa_pending)
        return 0;
      if (!state.topology.csa_pending) return -1;
      nanosleep(&pause, 0);
    }
  case F344_DETACH_WIFI:
    if (f344_bridge_member(n, "wifi1", false))
      return -1;
    return f344_bridge_member(n, "wifi0", false);
  case F344_REPEATER_CLEAR:
    if (f344_radio_observe(n, &state))
      return -1;
    if (!state.topology.primary_present || !state.topology.repeater)
      return 0;
    return run_private(n, "repeater", "0");
  case F344_DELETE_VAPS:
    return qdrv_command("stop 0 all\n");
  case F344_CREATE_PRIMARY:
    snprintf(command, sizeof(command),
             "start 0 %s wifi0 %02x:%02x:%02x:%02x:%02x:%02x\n",
             t->mode == F344_MODE_AP ? "ap" : "sta", original->primary_mac[0],
             original->primary_mac[1], original->primary_mac[2],
             original->primary_mac[3], original->primary_mac[4],
             original->primary_mac[5]);
    return qdrv_command(command);
  case F344_SET_CHANNEL_POLICY: {
    char channel[16];
    char *args[] = {"/usr/sbin/iwconfig-qtn", "wifi0", "channel", channel, 0};
    if (run_private(n, "mode",
                    t->bandwidth == 80   ? "11ac80"
                    : t->bandwidth == 40 ? "11ac40"
                                         : "11ac"))
      return -1;
    if (f344_layout_observe(&state) || state.bandwidth != t->bandwidth)
      return -1;
    if (f344_channel_set(n, t->channel_mask))
      return -1;
    /* The AP bootstrap disables scanning in shared ic state. Restore the
     * native station scan path only after SETCHANLIST has been read back. */
    if (run_private(n, "scan_no_dfs", "1") ||
        private_readback(n, "get_scan_dfs", 1) ||
        run_private(n, "disablescan", t->mode == F344_MODE_AP ? "1" : "0") ||
        private_readback(n, "get_disablescan", t->mode == F344_MODE_AP))
      return -1;
    snprintf(channel, sizeof(channel), "%u",
             t->mode == F344_MODE_AP ? (t->ap_frequency_mhz - 5000) / 5 : 0);
    return f344_run(args, reply, sizeof(reply), n->phase_deadline);
  }
  case F344_REPEATER_ENABLE:
    return run_private(n, "repeater", "1");
  case F344_CREATE_SECONDARY:
    return qdrv_command("start 0 ap wifi1\n");
  case F344_SET_BRIDGE_POLICY:
    return qdrv_command((rollback || t->mode == F344_MODE_AP) &&
                                !original->three_address_bridge
                            ? "bridge 0 disable\n" : "bridge 0 enable\n");
  case F344_ATTACH_WIFI:
    if (f344_bridge_member(n, "wifi0", true))
      return -1;
    if (t->mode == F344_MODE_REPEATER && f344_bridge_member(n, "wifi1", true))
      return -1;
    return 0;
  case F344_CONFIGURE_SECURITY:
    memset(&n->ap, 0, sizeof(n->ap));
    memset(&n->sta, 0, sizeof(n->sta));
    rc = f344_render_profile(p, n->transaction, n->ap.config,
                             sizeof(n->ap.config), n->sta.config,
                             sizeof(n->sta.config));
    if (rc)
      return rc;
    if (join_path(n->ap.control, sizeof(n->ap.control), n->transaction,
                  "/ap-control") ||
        join_path(n->sta.control, sizeof(n->sta.control), n->transaction,
                  "/sta-control"))
      return -1;
    n->running_profile = p;
    return 0;
  case F344_OPEN_GATE:
    if (control_write("/sys/module/qdrv/parameters/openmitrastar_mode_channel_hold",
                      "0\n"))
      return -1;
    return control_write("/sys/module/qdrv/parameters/openmitrastar_rf_enable", "1\n");
  case F344_START_SECURITY:
    if (t->mode != F344_MODE_AP &&
        spawn_daemon(n, &n->sta, STA_PROGRAM, t->mode == F344_MODE_REPEATER))
      return -1;
    if (t->mode == F344_MODE_REPEATER) {
      struct f344_profile *follow = malloc(sizeof(*follow));
      unsigned frequency;
      if (!follow)
        return -1;
      if (station_ready(n, p, &frequency)) {
        free(follow);
        return -1;
      }
      *follow = *p;
      follow->target.ap_frequency_mhz = frequency;
      /* The AP follows the actual authenticated upstream channel, not a
       * stale channel from its saved AP template. The live STA file must
       * not be rewritten after the supplicant has consumed it. */
      follow->target.mode = F344_MODE_REPEATER;
      rc = f344_render_ap_follow(follow, n->transaction, n->ap.config,
                                 sizeof(n->ap.config));
      memset(follow, 0, sizeof(*follow));
      free(follow);
      if (rc)
        return -1;
    }
    if (t->mode != F344_MODE_STA && spawn_daemon(n, &n->ap, AP_PROGRAM, false))
      return -1;
    n->configuration_loaded = true;
    return 0;
  }
  return -1;
}
static int wait_target(void *context, const struct f344_target *t,
                       struct f344_state *s) {
  struct f344_native *n = context;
  for (;;) {
    struct timespec pause = {0, 100000000};
    uint64_t now = f344_now_ms();
    if (!now || now >= n->phase_deadline)
      return -1;
    if (!complete_observation(n, s) && f344_target_observed(t, s))
      return 0;
    nanosleep(&pause, 0);
  }
}
static int initialize(void) {
  char compatible[256];
  size_t length;
  struct stat st;
  if (geteuid() != 0)
    return -1;
  umask(077);
  setenv("PATH", "/usr/sbin:/usr/bin:/sbin:/bin", 1);
  if (f344_read_file("/proc/device-tree/compatible", compatible,
                     sizeof(compatible), &length, false) ||
      !memmem(compatible, length, "mitrastar,hgw-500bna-qcv2",
              sizeof("mitrastar,hgw-500bna-qcv2")))
    return -1;
  if (mkdir("/run/openmitrastar", 0700) && errno != EEXIST)
    return -1;
  if (mkdir(STATE_ROOT, 0700) && errno != EEXIST)
    return -1;
  if (lstat(STATE_ROOT, &st) || !S_ISDIR(st.st_mode) || st.st_uid != 0 ||
      (st.st_mode & 0777) != 0700)
    return -1;
  native.socket_fd = socket(AF_INET, SOCK_DGRAM | SOCK_CLOEXEC, 0);
  if (native.socket_fd < 0)
    return -1;
  native.global_deadline = f344_now_ms() + 120000;
  native.phase_deadline = f344_now_ms() + 60000;
  return 0;
}
static int write_part(const char *directory, const char *name, const void *data,
                      size_t length) {
  char path[768];
  int n = snprintf(path, sizeof(path), "%s/%s", directory, name);
  return n < 0 || (size_t)n >= sizeof(path)
             ? -1
             : f344_write_file(path, data, length, 0600);
}
static unsigned key_count(const char *text, const char *key) {
  size_t wanted = strlen(key);
  unsigned count = 0;
  while (*text) {
    const char *end = strchr(text, '\n'), *p = text, *equal;
    size_t length = end ? (size_t)(end - text) : strlen(text);
    while (length && (*p == ' ' || *p == '\t')) {
      p++;
      length--;
    }
    equal = memchr(p, '=', length);
    if (equal && (size_t)(equal - p) == wanted && !memcmp(p, key, wanted))
      count++;
    if (!end)
      break;
    text = end + 1;
  }
  return count;
}
static int launch_bootstrap_ap(const char *configuration) {
  char raw[F344_CONFIG_MAX], number[32], resolved[PATH_MAX];
  const char *real_configuration = resolved;
  size_t length;
  struct iwreq wrq;
  uint8_t ssid[33] = {0};
  struct f344_state state = {0};
  struct registry old;
  if (!realpath(configuration, resolved) ||
      strlen(resolved) >= sizeof(native.ap.config) ||
      f344_read_file(configuration, raw, sizeof(raw) - 1, &length, true) ||
      memchr(raw, 0, length))
    return -1;
  raw[length] = 0;
  if (key_count(raw, "driver") != 1 || key_count(raw, "interface") != 1 ||
      key_count(raw, "bridge") != 1 || key_count(raw, "ctrl_interface") != 1 ||
      key_count(raw, "bss") || key_count(raw, "bssid") ||
      !text_field(raw, "driver", "madwifi") ||
      !text_field(raw, "interface", "wifi0") ||
      !text_field(raw, "bridge", "br0") ||
      !text_field(raw, "ctrl_interface", "/var/run/hostapd"))
    return -1;
  /* Bootstrap only creates a record for the exact process about to exec.
   * It never adopts credentials from an already-running legacy daemon. */
  if (!registry_read()) {
    old = saved;
    if (old.ap.pid > 1 && process_matches(&old.ap, AP_PROGRAM))
      return -1;
    if (old.sta.pid > 1 && process_matches(&old.sta, STA_PROGRAM))
      return -1;
  }
  if (f344_management(&native, &state) || f344_radio_observe(&native, &state) ||
      state.mode != F344_MODE_AP || state.topology.secondary_present ||
      state.topology.extender)
    return -1;
  memset(&wrq, 0, sizeof(wrq));
  strcpy(wrq.ifr_name, "wifi0");
  wrq.u.essid.pointer = ssid;
  wrq.u.essid.length = 32;
  if (ioctl(native.socket_fd, SIOCGIWESSID, &wrq) || !wrq.u.essid.length ||
      wrq.u.essid.length > 32)
    return -1;
  strcpy(native.transaction, STATE_ROOT "/boot-XXXXXX");
  if (!mkdtemp(native.transaction))
    return -1;
  if (write_part(native.transaction, "mode", "ap\n", 3) ||
      write_part(native.transaction, "ap_ssid", ssid, wrq.u.essid.length) ||
      write_part(native.transaction, "ap.conf", raw, length))
    return -1;
  snprintf(number, sizeof(number), "%u\n", state.bandwidth);
  if (write_part(native.transaction, "bandwidth", number, strlen(number)))
    return -1;
  snprintf(number, sizeof(number), "%u\n", state.frequency_mhz);
  if (write_part(native.transaction, "frequency", number, strlen(number)) ||
      f344_read_profile(native.transaction, &native.target))
    return -1;
  memcpy(native.target.target.channel_mask, state.channel_mask, 32);
  native.ap.pid = getpid();
  if (f344_pid_start(native.ap.pid, &native.ap.start_ticks))
    return -1;
  strcpy(native.ap.config, real_configuration);
  strcpy(native.ap.control, "/var/run/hostapd");
  native.ap.bootstrap_unlink_allowed = true;
  if (config_digest(configuration, native.ap.loaded_config_digest) ||
      registry_write(&native.target, &native.ap, &native.sta, false))
    return -1;
  close(native.socket_fd);
  /* CLOEXEC closes the transaction lock. The legacy boot script retains
   * the same foreground PID, log redirection and control socket path. */
  execl(AP_PROGRAM, AP_PROGRAM, "-q", real_configuration, (char *)0);
  return -1;
}
static int confirm_bootstrap(void) {
  struct f344_state state;
  if (registry_read() || saved.ready ||
      saved.profile.target.mode != F344_MODE_AP)
    return -1;
  native.original = saved.profile;
  native.ap = saved.ap;
  native.sta = saved.sta;
  native.configuration_loaded = true;
  native.running_profile = &native.original;
  if (complete_observation(&native, &state) ||
      !f344_target_observed(&native.original.target, &state))
    return -1;
  return registry_write(&native.original, &native.ap, &native.sta, true);
}
int main(int argc, char **argv) {
  int lockfd, rc;
  struct f344_result result;
  struct f344_state observed;
  struct f344_ops ops = {&native, snapshot, inspect, execute, wait_target};
  if (argc < 2 || (!strcmp(argv[1], "--help"))) {
    puts("Usage: om-f344-mode --inspect | --apply PRIVATE_PROFILE_DIRECTORY | "
         "--invalidate | --launch-ap CONFIG | --confirm-bootstrap");
    return argc < 2 ? 64 : 0;
  }
  if (strcmp(argv[1], "--inspect") && strcmp(argv[1], "--apply") &&
      strcmp(argv[1], "--invalidate") && strcmp(argv[1], "--launch-ap") &&
      strcmp(argv[1], "--confirm-bootstrap"))
    return 64;
  if (initialize())
    return 65;
  lockfd =
      open(STATE_ROOT "/lock", O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (lockfd < 0 || flock(lockfd, LOCK_EX | LOCK_NB)) {
    close(native.socket_fd);
    if (lockfd >= 0)
      close(lockfd);
    return 66;
  }
  if (!strcmp(argv[1], "--invalidate")) {
    rc = unlink(STATE_ROOT "/active.bin");
    if (rc && errno == ENOENT)
      rc = 0;
    goto done;
  }
  if (!strcmp(argv[1], "--launch-ap")) {
    rc = argc == 3 ? launch_bootstrap_ap(argv[2]) : -1;
    goto done;
  }
  if (!strcmp(argv[1], "--confirm-bootstrap")) {
    rc = argc == 2 ? confirm_bootstrap() : -1;
    goto done;
  }
  if (!strcmp(argv[1], "--inspect")) {
    rc = snapshot(&native, &observed);
    if (rc) {
      puts("{\"schema\":\"openmitrastar.f344-mode/v1\","
           "\"managed_snapshot\":false,\"mode\":null,"
           "\"upstream_completed\":null,\"ap_enabled\":null,"
           "\"traffic_verified\":false}");
      goto done;
    }
    printf("{\"schema\":\"openmitrastar.f344-mode/"
           "v1\",\"managed_snapshot\":%s,\"mode\":%u,\"upstream_completed\":%s,"
           "\"ap_enabled\":%s,\"warm_transition_supported\":%s,"
           "\"csa_reuse_qualified\":false,\"traffic_verified\":false}\n",
           rc ? "false" : "true", rc ? 0 : (unsigned)observed.mode,
           !rc && observed.upstream_completed ? "true" : "false",
           !rc && observed.ap_enabled ? "true" : "false",
           !rc && observed.topology.csa_reuse_supported ? "true" : "false");
    goto done;
  }
  if (argc != 3 || f344_read_profile(argv[2], &native.target)) {
    rc = 67;
    goto done;
  }
  native.target.target.profile_cookie = 2;
  strcpy(native.transaction, STATE_ROOT "/txn-XXXXXX");
  if (!mkdtemp(native.transaction)) {
    rc = 68;
    goto done;
  }
  alarm(125);
  rc = f344_apply(&ops, &native.target.target, &result);
  alarm(0);
  if (result.outcome == F344_APPLIED_READBACK ||
      result.outcome == F344_ROLLED_BACK_READBACK) {
    if (registry_write(native.running_profile, &native.ap, &native.sta, true)) {
      rc = -1;
      result.outcome = F344_ROLLBACK_FAILED;
    }
  }
  printf(
      "{\"schema\":\"openmitrastar.f344-transaction/"
      "v1\",\"outcome\":%u,\"error\":%d,\"actions\":%u,\"rollback_actions\":%u,"
      "\"traffic_verified\":false,\"physical_acceptance\":\"USER_DEFERRED\"}\n",
      result.outcome, result.error, result.actions, result.rollback_actions);
done:
  close(native.socket_fd);
  flock(lockfd, LOCK_UN);
  close(lockfd);
  memset(&native, 0, sizeof(native));
  memset(&saved, 0, sizeof(saved));
  return rc ? 1 : 0;
}
