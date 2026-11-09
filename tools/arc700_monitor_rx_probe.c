// SPDX-License-Identifier: GPL-2.0-only
/* Passive, metadata-only 802.11 monitor RX proof for authorized hardware. */

#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_packet.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	const char *name = argc > 1 ? argv[1] : "wlan0";
	unsigned char frame[4096];
	struct sockaddr_ll address;
	struct ifreq request;
	struct timeval timeout = { 5, 0 };
	unsigned int radiotap_len;
	unsigned int fc;
	int fd;
	int count = 0;
	ssize_t length;

	fd = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
	if (fd < 0) {
		perror("socket");
		return 2;
	}
	memset(&request, 0, sizeof(request));
	strncpy(request.ifr_name, name, IFNAMSIZ - 1);
	if (ioctl(fd, SIOCGIFINDEX, &request) < 0) {
		perror("SIOCGIFINDEX");
		close(fd);
		return 3;
	}
	memset(&address, 0, sizeof(address));
	address.sll_family = AF_PACKET;
	address.sll_protocol = htons(ETH_P_ALL);
	address.sll_ifindex = request.ifr_ifindex;
	if (bind(fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
		perror("bind");
		close(fd);
		return 4;
	}
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

	while (count < 10) {
		length = recv(fd, frame, sizeof(frame), 0);
		if (length < 0) {
			if (errno == EAGAIN || errno == EWOULDBLOCK)
				break;
			perror("recv");
			close(fd);
			return 5;
		}
		if (length < 10 || frame[0] != 0)
			continue;
		radiotap_len = frame[2] | ((unsigned int)frame[3] << 8);
		if (radiotap_len + 2 > (unsigned int)length)
			continue;
		fc = frame[radiotap_len] |
		     ((unsigned int)frame[radiotap_len + 1] << 8);
		printf("MONITOR_RX_FRAME id=%d bytes=%ld radiotap=%u type=%u subtype=%u\n",
		       count + 1, (long)length, radiotap_len,
		       (fc >> 2) & 0x3, (fc >> 4) & 0xf);
		count++;
	}
	close(fd);
	if (!count) {
		fprintf(stderr, "MONITOR_RX_TIMEOUT frames=0\n");
		return 6;
	}
	printf("MONITOR_RX_PASS frames=%d interface=%s metadata_only=1\n",
	       count, name);
	return 0;
}
