// SPDX-License-Identifier: GPL-2.0-only
/* Bounded metadata-only L2 trace for the authorized OpenMitraStar bridge. */

#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_packet.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <netinet/ip.h>
#include <netinet/udp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

static unsigned long now_ms(void)
{
	struct timeval tv;
	gettimeofday(&tv, NULL);
	return (unsigned long)tv.tv_sec * 1000UL + tv.tv_usec / 1000UL;
}

int main(int argc, char **argv)
{
	const char *name = argc > 1 ? argv[1] : "wifi0";
	int seconds = argc > 2 ? atoi(argv[2]) : 30;
	unsigned char frame[4096];
	struct sockaddr_ll bind_addr, from;
	struct ifreq request;
	struct timeval timeout = { 1, 0 };
	unsigned long deadline;
	unsigned int interesting = 0, dhcp = 0, arp = 0, icmp = 0;
	int fd;

	if (seconds < 1 || seconds > 60)
		return 2;
	fd = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
	if (fd < 0) {
		perror("socket");
		return 3;
	}
	memset(&request, 0, sizeof(request));
	strncpy(request.ifr_name, name, IFNAMSIZ - 1);
	if (ioctl(fd, SIOCGIFINDEX, &request) < 0) {
		perror("SIOCGIFINDEX");
		return 4;
	}
	memset(&bind_addr, 0, sizeof(bind_addr));
	bind_addr.sll_family = AF_PACKET;
	bind_addr.sll_protocol = htons(ETH_P_ALL);
	bind_addr.sll_ifindex = request.ifr_ifindex;
	if (bind(fd, (struct sockaddr *)&bind_addr, sizeof(bind_addr)) < 0) {
		perror("bind");
		return 5;
	}
	setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
	deadline = now_ms() + (unsigned long)seconds * 1000UL;
	printf("OML2TRACE_START interface=%s seconds=%d metadata_only=1\n", name, seconds);
	while (now_ms() < deadline) {
		socklen_t from_len = sizeof(from);
		ssize_t len = recvfrom(fd, frame, sizeof(frame), 0,
			(struct sockaddr *)&from, &from_len);
		unsigned int off = ETH_HLEN;
		unsigned int type;
		if (len < 0) {
			if (errno == EAGAIN || errno == EWOULDBLOCK)
				continue;
			perror("recvfrom");
			return 6;
		}
		if (len < ETH_HLEN)
			continue;
		type = ((unsigned int)frame[12] << 8) | frame[13];
		if (type == 0x8100 && len >= ETH_HLEN + 4) {
			type = ((unsigned int)frame[16] << 8) | frame[17];
			off += 4;
		}
		if (type == ETH_P_ARP) {
			arp++;
			if (interesting++ < 64)
				printf("OML2TRACE event=arp interface=%s packet_type=%u bytes=%ld\n",
					name, from.sll_pkttype, (long)len);
			continue;
		}
		if (type == ETH_P_IP && len >= (ssize_t)(off + sizeof(struct iphdr))) {
			struct iphdr *ip = (struct iphdr *)(frame + off);
			unsigned int ihl = ip->ihl * 4U;
			if (ip->protocol == IPPROTO_ICMP) {
				icmp++;
				if (interesting++ < 64)
					printf("OML2TRACE event=icmp interface=%s packet_type=%u bytes=%ld\n",
						name, from.sll_pkttype, (long)len);
			} else if (ip->protocol == IPPROTO_UDP &&
				len >= (ssize_t)(off + ihl + sizeof(struct udphdr))) {
				struct udphdr *udp = (struct udphdr *)(frame + off + ihl);
				unsigned int src = ntohs(udp->source), dst = ntohs(udp->dest);
				if (src == 67 || src == 68 || dst == 67 || dst == 68) {
					dhcp++;
					if (interesting++ < 64)
						printf("OML2TRACE event=dhcp interface=%s packet_type=%u src=%u dst=%u bytes=%ld\n",
							name, from.sll_pkttype, src, dst, (long)len);
				}
			}
		}
	}
	close(fd);
	printf("OML2TRACE_DONE interface=%s interesting=%u dhcp=%u arp=%u icmp=%u\n",
		name, interesting, dhcp, arp, icmp);
	return 0;
}
