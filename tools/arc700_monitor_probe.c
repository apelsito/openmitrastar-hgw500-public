// SPDX-License-Identifier: GPL-2.0-only
/* Minimal radiotap probe-request injector for an authorized RAM-only test. */

#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_packet.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

static int get_interface(const char *name, int *index, unsigned char mac[6])
{
	struct ifreq request;
	int fd;

	fd = socket(AF_INET, SOCK_DGRAM, 0);
	if (fd < 0)
		return -1;
	memset(&request, 0, sizeof(request));
	strncpy(request.ifr_name, name, IFNAMSIZ - 1);
	if (ioctl(fd, SIOCGIFINDEX, &request) < 0) {
		close(fd);
		return -1;
	}
	*index = request.ifr_ifindex;
	if (ioctl(fd, SIOCGIFHWADDR, &request) < 0) {
		close(fd);
		return -1;
	}
	memcpy(mac, request.ifr_hwaddr.sa_data, 6);
	close(fd);
	return 0;
}

int main(int argc, char **argv)
{
	static const unsigned char prefix[] = {
		/* radiotap v0, length 8, no present fields */
		0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00,
		/* probe request, duration */
		0x40, 0x00, 0x00, 0x00,
		/* DA broadcast */
		0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
	};
	static const unsigned char suffix[] = {
		/* BSSID broadcast, sequence */
		0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00, 0x00,
		/* wildcard SSID */
		0x00, 0x00,
		/* supported rates: 1, 2, 5.5, 11 Mbps */
		0x01, 0x04, 0x82, 0x84, 0x8b, 0x96,
	};
	struct sockaddr_ll address;
	unsigned char frame[sizeof(prefix) + 6 + sizeof(suffix)];
	unsigned char mac[6];
	const char *interface = argc > 1 ? argv[1] : "wlan0";
	int ifindex;
	int fd;
	int i;
	ssize_t sent;

	if (get_interface(interface, &ifindex, mac) < 0) {
		perror("interface");
		return 2;
	}
	memcpy(frame, prefix, sizeof(prefix));
	memcpy(frame + sizeof(prefix), mac, sizeof(mac));
	memcpy(frame + sizeof(prefix) + sizeof(mac), suffix, sizeof(suffix));

	fd = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
	if (fd < 0) {
		perror("socket");
		return 3;
	}
	memset(&address, 0, sizeof(address));
	address.sll_family = AF_PACKET;
	address.sll_protocol = htons(ETH_P_ALL);
	address.sll_ifindex = ifindex;

	for (i = 0; i < 3; ++i) {
		sent = sendto(fd, frame, sizeof(frame), 0,
			      (struct sockaddr *)&address, sizeof(address));
		if (sent != (ssize_t)sizeof(frame)) {
			fprintf(stderr, "sendto[%d]=%ld errno=%d\n",
				i, (long)sent, errno);
			close(fd);
			return 4;
		}
	}
	close(fd);
	printf("MONITOR_PROBE_TX_PASS frames=3 bytes=%u ifindex=%d mac=%02x:%02x:%02x:%02x:%02x:%02x\n",
	       (unsigned int)sizeof(frame), ifindex,
	       mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
	return 0;
}
