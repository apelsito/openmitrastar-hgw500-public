/* SPDX-License-Identifier: GPL-2.0-only */
#define _GNU_SOURCE
#include "f344_native.h"
#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_arp.h>
#include <linux/if_bridge.h>
#include <linux/sockios.h>
#include <linux/wireless.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
extern int sha256_vector(size_t, const uint8_t *[], const size_t *, uint8_t *);
static int request(struct f344_native *n, const char *name,
                   unsigned long command, struct ifreq *ifr) {
  if (strlen(name) >= IFNAMSIZ)
    return -1;
  memset(ifr, 0, sizeof(*ifr));
  strcpy(ifr->ifr_name, name);
  return ioctl(n->socket_fd, command, ifr);
}
static int member(const char *name) {
  char path[128];
  struct stat st;
  snprintf(path, sizeof(path), "/sys/class/net/br0/brif/%s", name);
  return stat(path, &st) == 0;
}
int f344_primary_mac(struct f344_native *n, const char *name, uint8_t *out) {
  struct ifreq ifr;
  if (request(n, name, SIOCGIFHWADDR, &ifr) ||
      ifr.ifr_hwaddr.sa_family != ARPHRD_ETHER)
    return -1;
  memcpy(out, ifr.ifr_hwaddr.sa_data, 6);
  return 0;
}
int f344_management(struct f344_native *n, struct f344_state *s) {
  struct ifreq ifr;
  uint8_t values[64] = {0}, mac[6];
  const uint8_t *data[] = {values};
  size_t sizes[] = {sizeof(values)};
  unsigned flags, offset = 0;
  FILE *routes;
  char line[512], iface[32];
  unsigned long destination, gateway, mask;
  unsigned route_flags;
  bool gateway_seen = false;
  if (f344_primary_mac(n, "br0", mac))
    return -1;
  memcpy(values, mac, 6);
  offset = 6;
  if (!n->before.valid)
    memcpy(n->management_mac, mac, 6);
  if (request(n, "br0", SIOCGIFADDR, &ifr) || ifr.ifr_addr.sa_family != AF_INET)
    return -1;
  memcpy(values + offset, &((struct sockaddr_in *)&ifr.ifr_addr)->sin_addr, 4);
  offset += 4;
  if (request(n, "br0", SIOCGIFNETMASK, &ifr))
    return -1;
  memcpy(values + offset, &((struct sockaddr_in *)&ifr.ifr_netmask)->sin_addr,
         4);
  offset += 4;
  if (request(n, "br0", SIOCGIFMTU, &ifr))
    return -1;
  memcpy(values + offset, &ifr.ifr_mtu, 4);
  offset += 4;
  if (request(n, "br0", SIOCGIFFLAGS, &ifr))
    return -1;
  flags = ifr.ifr_flags & IFF_UP;
  memcpy(values + offset, &flags, 4);
  offset += 4;
  if (request(n, "eth0", SIOCGIFFLAGS, &ifr))
    return -1;
  flags = ifr.ifr_flags & IFF_UP;
  memcpy(values + offset, &flags, 4);
  offset += 4;
  if (request(n, "wlan0", SIOCGIFFLAGS, &ifr))
    return -1;
  flags = ifr.ifr_flags & IFF_UP;
  memcpy(values + offset, &flags, 4);
  offset += 4;
  values[offset++] = (uint8_t)member("eth0");
  values[offset++] = (uint8_t)member("wlan0");
  if (!values[offset - 1] || !values[offset - 2])
    return -1;
  routes = fopen("/proc/net/route", "r");
  if (!routes)
    return -1;
  while (fgets(line, sizeof(line), routes)) {
    unsigned ref, use, metric, mtu, window, irtt;
    if (sscanf(line, "%31s %lx %lx %x %u %u %u %lx %u %u %u", iface,
               &destination, &gateway, &route_flags, &ref, &use, &metric, &mask,
               &mtu, &window, &irtt) != 11)
      continue;
    if (!strcmp(iface, "br0") && destination == 0 && mask == 0 &&
        (route_flags & 1)) {
      uint32_t gw = (uint32_t)gateway;
      if (gateway_seen) {
        fclose(routes);
        return -1;
      }
      gateway_seen = true;
      memcpy(values + offset, &gw, 4);
    }
  }
  fclose(routes);
  offset += 4;
  values[offset] = (uint8_t)gateway_seen;
  if (sha256_vector(1, data, sizes, s->management_digest))
    return -1;
  s->valid |= F344_VALID_MANAGEMENT;
  return 0;
}
int f344_if_flags(struct f344_native *n, const char *name, bool up) {
  struct ifreq ifr;
  if (strcmp(name, "wifi0") && strcmp(name, "wifi1"))
    return -1;
  if (request(n, name, SIOCGIFFLAGS, &ifr)) {
    if (!up && errno == ENODEV)
      return 0;
    return -1;
  }
  if (up)
    ifr.ifr_flags |= IFF_UP;
  else
    ifr.ifr_flags &= (short)~IFF_UP;
  return ioctl(n->socket_fd, SIOCSIFFLAGS, &ifr);
}
int f344_bridge_member(struct f344_native *n, const char *name, bool add) {
  struct ifreq index, bridge;
  if (strcmp(name, "wifi0") && strcmp(name, "wifi1"))
    return -1;
  if (member(name) == add)
    return 0;
  if (request(n, name, SIOCGIFINDEX, &index))
    return -1;
  memset(&bridge, 0, sizeof(bridge));
  strcpy(bridge.ifr_name, "br0");
  bridge.ifr_ifindex = index.ifr_ifindex;
  return ioctl(n->socket_fd, add ? SIOCBRADDIF : SIOCBRDELIF, &bridge);
}
static int state_values(struct f344_state *s, unsigned *offset) {
  static const char *keys[] = {"workflow_enabled",
                               "core_started",
                               "primary_present",
                               "primary_mode",
                               "primary_up",
                               "secondary_present",
                               "secondary_mode",
                               "secondary_up",
                               "repeater",
                               "extender",
                               "other_vaps",
                               "open_gate",
                               "three_address_bridge",
                               "channel_input_offset",
                               "four_address",
                               "bandwidth", "csa_known", "csa_pending",
                               "channel_hold", "csa_drained", "csa_generation", "csa_readers", "csa_reuse_supported"};
  char data[1024], *save, *line;
  size_t length;
  unsigned values[23] = {0}, seen = 0, i;
  if (f344_read_file("/sys/devices/qdrv/mode_state", data, sizeof(data) - 1,
                     &length, false))
    return -1;
  data[length] = 0;
  line = strtok_r(data, "\n", &save);
  if (!line || strcmp(line, "schema=openmitrastar.f344-mode/v1"))
    return -1;
  while ((line = strtok_r(0, "\n", &save))) {
    char *equal = strchr(line, '='), *end;
    unsigned long value;
    if (!equal)
      return -1;
    *equal = 0;
    errno = 0;
    value = strtoul(equal + 1, &end, 10);
    if (errno || *end || value > UINT32_MAX)
      return -1;
    for (i = 0; i < 23; i++)
      if (!strcmp(line, keys[i])) {
        if (seen & (1U << i))
          return -1;
        seen |= 1U << i;
        values[i] = (unsigned)value;
        break;
      }
  }
  if (seen != 0x7fffff || values[0] != 1 || values[1] != 1 || values[3] > 2 ||
      values[6] > 2 || values[13] > 1)
    return -1;
  for (i = 0; i < 23; i++)
    if (i != 3 && i != 6 && i != 10 && i != 15 && i != 20 && i != 21 && values[i] > 1)
      return -1;
  if (values[15] != 0 && values[15] != 20 && values[15] != 40 &&
      values[15] != 80)
    return -1;
  s->bandwidth = values[15];
  s->topology.csa_known = values[16];
  s->topology.csa_pending = values[17];
  s->topology.channel_hold = values[18];
  s->topology.csa_drained = values[19];
  s->topology.csa_generation = values[20];
  s->topology.csa_readers = values[21];
  s->topology.csa_reuse_supported = values[22];
  s->topology.valid = s->topology.core_started = true;
  s->topology.primary_present = values[2];
  s->topology.primary_mode = values[3];
  s->topology.primary_up = values[4];
  s->topology.secondary_present = values[5];
  s->topology.secondary_mode = values[6];
  s->topology.secondary_up = values[7];
  s->topology.repeater = values[8];
  s->topology.extender = values[9];
  s->topology.other_vaps = values[10];
  s->topology.open_gate = values[11];
  s->three_address_bridge = values[12];
  *offset = values[13];
  s->four_address_negotiated = values[14];
  s->mode = !values[2]                  ? F344_MODE_NONE
            : values[3] == F344_MODE_AP ? F344_MODE_AP
            : values[8] && values[5]    ? F344_MODE_REPEATER
                                        : F344_MODE_STA;
  s->valid |= 1;
  return 0;
}
int f344_layout_observe(struct f344_state *state) {
  unsigned offset;
  return state_values(state, &offset);
}
int f344_channel_set(struct f344_native *n, const uint8_t *mask) {
  struct iwreq wrq;
  uint8_t input[32], output[32];
  struct f344_state state = {0};
  unsigned offset;
  if (state_values(&state, &offset) || state.topology.primary_up ||
      state.topology.secondary_up || f344_channel_encode(mask, offset, input))
    return -1;
  memset(&wrq, 0, sizeof(wrq));
  strcpy(wrq.ifr_name, "wifi0");
  wrq.u.data.pointer = input;
  wrq.u.data.length = 32;
  if (ioctl(n->socket_fd, SIOCIWFIRSTPRIV + 6, &wrq))
    return -1;
  wrq.u.data.pointer = output;
  wrq.u.data.length = 32;
  if (ioctl(n->socket_fd, SIOCIWFIRSTPRIV + 7, &wrq) ||
      wrq.u.data.length != 32 || memcmp(mask, output, 32))
    return -1;
  return 0;
}
int f344_radio_observe(struct f344_native *n, struct f344_state *s) {
  struct iwreq wrq;
  unsigned offset;
  int64_t frequency;
  unsigned e;
  if (state_values(s, &offset))
    return -1;
  if (!s->topology.primary_present)
    return 0;
  if (f344_primary_mac(n, "wifi0", s->primary_mac))
    return -1;
  if (s->topology.secondary_present &&
      f344_primary_mac(n, "wifi1", s->secondary_mac))
    return -1;
  s->valid |= 64;
  memset(&wrq, 0, sizeof(wrq));
  strcpy(wrq.ifr_name, "wifi0");
  wrq.u.data.pointer = s->channel_mask;
  wrq.u.data.length = 32;
  if (ioctl(n->socket_fd, SIOCIWFIRSTPRIV + 7, &wrq) || wrq.u.data.length != 32)
    return -1;
  memset(&wrq, 0, sizeof(wrq));
  strcpy(wrq.ifr_name, "wifi0");
  if (ioctl(n->socket_fd, SIOCGIWFREQ, &wrq))
    return -1;
  if (wrq.u.freq.e < 0 || wrq.u.freq.e > 9 || wrq.u.freq.m < 0)
    return -1;
  frequency = wrq.u.freq.m;
  for (e = 0; e < (unsigned)wrq.u.freq.e; e++)
    frequency *= 10;
  if (frequency < 5000000000LL || frequency > 6000000000LL)
    return -1;
  s->frequency_mhz = (unsigned)(frequency / 1000000);
  s->valid |= 2;
  s->primary_bridged = member("wifi0");
  s->secondary_bridged = member("wifi1");
  s->valid |= 32;
  return 0;
}
