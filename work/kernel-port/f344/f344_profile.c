/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "f344_native.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
extern int sha256_vector(size_t, const uint8_t *[], const size_t *, uint8_t *);
static int path(char *out, size_t n, const char *dir, const char *name) {
  int count = snprintf(out, n, "%s/%s", dir, name);
  return count < 0 || (size_t)count >= n ? -1 : 0;
}
static int field(const char *dir, const char *name, char *out, size_t cap,
                 size_t *length) {
  char filename[768];
  if (path(filename, sizeof(filename), dir, name))
    return -1;
  return f344_read_file(filename, out, cap, length, true);
}
static int scalar(const char *dir, const char *name, unsigned *value) {
  char text[32], *end;
  size_t n;
  unsigned long result;
  if (field(dir, name, text, sizeof(text) - 1, &n) || memchr(text, 0, n))
    return -1;
  text[n] = 0;
  errno = 0;
  result = strtoul(text, &end, 10);
  if (errno || !n || result > UINT_MAX || (*end && strcmp(end, "\n")))
    return -1;
  *value = (unsigned)result;
  return 0;
}
static int clean_config(const char *input, size_t length, char *out,
                        size_t *out_length, bool ap) {
  size_t at = 0, used = 0;
  if (memchr(input, 0, length))
    return -1;
  while (at < length) {
    size_t end = at, key_start, key_end, key_length;
    bool skip = false;
    while (end < length && input[end] != '\n')
      end++;
    key_start = at;
    while (key_start < end &&
           (input[key_start] == ' ' || input[key_start] == '\t'))
      key_start++;
    key_end = key_start;
    while (key_end < end && input[key_end] != '=')
      key_end++;
    key_length = key_end - key_start;
#define KEY(s)                                                                 \
  (key_length == sizeof(s) - 1 &&                                              \
   !memcmp(input + key_start, (s), sizeof(s) - 1))
    if (ap && (KEY("bss") || KEY("bssid")))
      return -1;
    if (KEY("ctrl_interface") || KEY("ctrl_interface_group") ||
        KEY("update_config") || KEY("country") || KEY("country_code"))
      skip = true;
    if (ap && (KEY("interface") || KEY("driver") || KEY("bridge") ||
               KEY("ssid") || KEY("ssid2") || KEY("channel")))
      skip = true;
#undef KEY
    if (!skip) {
      size_t amount = end - at;
      if (used + amount + 1 >= F344_CONFIG_MAX)
        return -1;
      memcpy(out + used, input + at, amount);
      used += amount;
      out[used++] = '\n';
    }
    at = end < length ? end + 1 : end;
  }
  out[used] = 0;
  *out_length = used;
  return 0;
}
int f344_read_profile(const char *directory, struct f344_profile *p) {
  char canonical[PATH_MAX], mode[24], raw[F344_CONFIG_MAX];
  struct stat st;
  size_t n;
  unsigned i;
  const uint8_t *data[5];
  size_t sizes[5];
  uint8_t metadata[12];
  if (!directory || !p || !realpath(directory, canonical) ||
      strlen(canonical) >= sizeof(p->directory) || lstat(directory, &st) ||
      !S_ISDIR(st.st_mode) || st.st_uid != 0 || (st.st_mode & 0777) != 0700)
    return -1;
  memset(p, 0, sizeof(*p));
  strcpy(p->directory, canonical);
  if (field(directory, "mode", mode, sizeof(mode) - 1, &n) ||
      memchr(mode, 0, n))
    return -1;
  mode[n] = 0;
  if (n && mode[n - 1] == '\n')
    mode[n - 1] = 0;
  if (!strcmp(mode, "ap"))
    p->target.mode = F344_MODE_AP;
  else if (!strcmp(mode, "sta"))
    p->target.mode = F344_MODE_STA;
  else if (!strcmp(mode, "repeater"))
    p->target.mode = F344_MODE_REPEATER;
  else
    return -1;
  if (scalar(directory, "bandwidth", &p->target.bandwidth) ||
      (p->target.bandwidth != 20 && p->target.bandwidth != 40 &&
       p->target.bandwidth != 80))
    return -1;
  if (p->target.mode == F344_MODE_AP) {
    if (scalar(directory, "frequency", &p->target.ap_frequency_mhz) ||
        p->target.ap_frequency_mhz < 5180 ||
        p->target.ap_frequency_mhz > 5240 ||
        (p->target.ap_frequency_mhz - 5180) % 20)
      return -1;
  }
  for (i = 36; i <= 48; i += 4)
    p->target.channel_mask[i / 8] |= 1U << (i % 8);
  if (p->target.mode != F344_MODE_STA) {
    if (field(directory, "ap_ssid", (char *)p->ap_ssid, 33, &p->ap_ssid_len) ||
        !p->ap_ssid_len || p->ap_ssid_len > 32)
      return -1;
    if (field(directory, "ap.conf", raw, sizeof(raw) - 1, &n) || !n ||
        clean_config(raw, n, p->ap_config, &p->ap_length, true))
      return -1;
  }
  if (p->target.mode != F344_MODE_AP) {
    if (field(directory, "sta_ssid", (char *)p->sta_ssid, 33,
              &p->sta_ssid_len) ||
        !p->sta_ssid_len || p->sta_ssid_len > 32)
      return -1;
    if (field(directory, "wpa.conf", raw, sizeof(raw) - 1, &n) || !n ||
        clean_config(raw, n, p->sta_config, &p->sta_length, false))
      return -1;
  }
  memset(metadata, 0, sizeof(metadata));
  metadata[0] = (uint8_t)p->target.mode;
  metadata[1] = (uint8_t)p->target.bandwidth;
  metadata[2] = (uint8_t)p->ap_ssid_len;
  metadata[3] = (uint8_t)p->sta_ssid_len;
  metadata[4] = (uint8_t)p->target.ap_frequency_mhz;
  metadata[5] = (uint8_t)(p->target.ap_frequency_mhz >> 8);
  data[0] = metadata;
  sizes[0] = sizeof(metadata);
  data[1] = p->ap_ssid;
  sizes[1] = p->ap_ssid_len;
  data[2] = p->sta_ssid;
  sizes[2] = p->sta_ssid_len;
  data[3] = (const uint8_t *)p->ap_config;
  sizes[3] = p->ap_length;
  data[4] = (const uint8_t *)p->sta_config;
  sizes[4] = p->sta_length;
  return sha256_vector(5, data, sizes, p->target.profile_digest);
}
static int render_profile(const struct f344_profile *p, const char *directory,
                          char *ap_path, size_t ap_capacity, char *sta_path,
                          size_t sta_capacity, bool render_station) {
  char body[F344_CONFIG_MAX + 1536], ssid_hex[65];
  size_t i;
  int n;
  if (!p || !directory)
    return -1;
  ap_path[0] = sta_path[0] = 0;
  if (p->target.mode != F344_MODE_STA) {
    if (path(ap_path, ap_capacity, directory, "hostapd.conf"))
      return -1;
    for (i = 0; i < p->ap_ssid_len; i++)
      snprintf(ssid_hex + i * 2, 3, "%02x", p->ap_ssid[i]);
    ssid_hex[p->ap_ssid_len * 2] = 0;
    n = snprintf(body, sizeof(body),
                 "driver=madwifi\ninterface=%s\nbridge=br0\nctrl_interface=%s/"
                 "ap-control\nssid2=%s\nchannel=%u\n%s",
                 p->target.mode == F344_MODE_REPEATER ? "wifi1" : "wifi0",
                 directory, ssid_hex,
                 p->target.ap_frequency_mhz
                     ? (p->target.ap_frequency_mhz - 5000) / 5
                     : 0,
                 p->ap_config);
    if (n < 0 || (size_t)n >= sizeof(body) ||
        f344_write_file(ap_path, body, (size_t)n, 0600))
      return -1;
  }
  if (render_station && p->target.mode != F344_MODE_AP) {
    if (path(sta_path, sta_capacity, directory, "wpa.conf"))
      return -1;
    n = snprintf(body, sizeof(body),
                 "ctrl_interface=%s/sta-control\nupdate_config=0\n%s",
                 directory, p->sta_config);
    if (n < 0 || (size_t)n >= sizeof(body) ||
        f344_write_file(sta_path, body, (size_t)n, 0600))
      return -1;
  }
  memset(body, 0, sizeof(body));
  return 0;
}
int f344_render_profile(const struct f344_profile *p, const char *directory,
                        char *ap_path, size_t ap_capacity, char *sta_path,
                        size_t sta_capacity) {
  return render_profile(p, directory, ap_path, ap_capacity, sta_path,
                        sta_capacity, true);
}
int f344_render_ap_follow(const struct f344_profile *p, const char *directory,
                          char *ap_path, size_t ap_capacity) {
  char unused[1];
  return render_profile(p, directory, ap_path, ap_capacity, unused,
                        sizeof(unused), false);
}
