/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F344_NATIVE_H
#define F344_NATIVE_H
#include "f344_transaction.h"
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#define F344_CONFIG_MAX 8192
struct f344_profile {
  struct f344_target target;
  char directory[512];
  unsigned char ap_ssid[33], sta_ssid[33];
  size_t ap_ssid_len, sta_ssid_len;
  char ap_config[F344_CONFIG_MAX], sta_config[F344_CONFIG_MAX];
  size_t ap_length, sta_length;
};
struct f344_daemon {
  pid_t pid;
  uint64_t start_ticks;
  char config[512], control[512];
  uint8_t loaded_config_digest[32];
  bool bootstrap_unlink_allowed;
};
struct f344_native {
  struct f344_profile target, original;
  struct f344_daemon ap, sta;
  struct f344_state before;
  char transaction[512];
  uint64_t global_deadline, phase_deadline;
  int socket_fd;
  bool rollback, configuration_loaded;
  uint8_t management_mac[6];
  const struct f344_profile *running_profile;
};
uint64_t f344_now_ms(void);
int f344_run(char *const argv[], char *out, size_t capacity, uint64_t deadline);
int f344_write_file(const char *, const void *, size_t, unsigned mode);
int f344_read_file(const char *, void *, size_t, size_t *, bool private_file);
int f344_read_profile(const char *, struct f344_profile *);
int f344_render_profile(const struct f344_profile *, const char *directory,
                        char *ap_path, size_t, char *sta_path, size_t);
int f344_render_ap_follow(const struct f344_profile *, const char *directory,
                          char *ap_path, size_t);
int f344_management(struct f344_native *, struct f344_state *);
int f344_radio_observe(struct f344_native *, struct f344_state *);
int f344_layout_observe(struct f344_state *);
int f344_if_flags(struct f344_native *, const char *, bool up);
int f344_bridge_member(struct f344_native *, const char *, bool add);
int f344_channel_set(struct f344_native *, const uint8_t *);
int f344_primary_mac(struct f344_native *, const char *, uint8_t *);
int f344_pid_start(pid_t, uint64_t *);
int f344_daemon_request(const struct f344_daemon *, const char *, const char *,
                        const char *, char *, size_t, uint64_t);
#endif
