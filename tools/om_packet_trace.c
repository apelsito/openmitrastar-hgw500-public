#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <errno.h>
#include <linux/if_ether.h>
#include <linux/if_packet.h>
#include <linux/if.h>
#include <netinet/ip.h>
#include <netinet/udp.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static long long monotonic_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static void print_mac(const unsigned char *mac)
{
	printf("%02x:%02x:%02x:%02x:%02x:%02x",
	       mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

int main(int argc, char **argv)
{
	unsigned char buf[4096];
	struct sockaddr_ll bind_addr = {0}, from = {0};
	struct ifreq ifr = {0};
	long long deadline, next_report;
	unsigned long long rx_packets = 0, tx_packets = 0;
	unsigned long long rx_bytes = 0, tx_bytes = 0;
	unsigned long long arp = 0, dhcp = 0, dns = 0, tcp = 0;
	int fd, seconds = 30;

	if (argc < 2 || argc > 3) {
		fprintf(stderr, "usage: %s IFACE [SECONDS]\n", argv[0]);
		return 2;
	}
	if (argc == 3) {
		seconds = atoi(argv[2]);
		if (seconds < 1 || seconds > 600)
			return 2;
	}

	fd = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
	if (fd < 0) {
		perror("socket");
		return 1;
	}
	strncpy(ifr.ifr_name, argv[1], IFNAMSIZ - 1);
	if (ioctl(fd, SIOCGIFINDEX, &ifr) < 0) {
		perror("SIOCGIFINDEX");
		close(fd);
		return 1;
	}
	bind_addr.sll_family = AF_PACKET;
	bind_addr.sll_protocol = htons(ETH_P_ALL);
	bind_addr.sll_ifindex = ifr.ifr_ifindex;
	if (bind(fd, (struct sockaddr *)&bind_addr, sizeof(bind_addr)) < 0) {
		perror("bind");
		close(fd);
		return 1;
	}

	deadline = monotonic_ms() + (long long)seconds * 1000;
	next_report = monotonic_ms() + 1000;
	printf("OMPKT_BEGIN iface=%s seconds=%d\n", argv[1], seconds);
	fflush(stdout);

	while (monotonic_ms() < deadline) {
		struct pollfd pfd = {.fd = fd, .events = POLLIN};
		socklen_t from_len = sizeof(from);
		ssize_t len;
		int outgoing, interesting = 0;
		uint16_t ethertype;
		size_t off = ETH_HLEN;

		if (poll(&pfd, 1, 200) <= 0)
			goto report;
		len = recvfrom(fd, buf, sizeof(buf), 0,
			       (struct sockaddr *)&from, &from_len);
		if (len < ETH_HLEN)
			goto report;
		outgoing = from.sll_pkttype == PACKET_OUTGOING;
		if (outgoing) {
			tx_packets++;
			tx_bytes += len;
		} else {
			rx_packets++;
			rx_bytes += len;
		}

		ethertype = ((uint16_t)buf[12] << 8) | buf[13];
		if (ethertype == ETH_P_8021Q && len >= 18) {
			ethertype = ((uint16_t)buf[16] << 8) | buf[17];
			off = 18;
		}
		if (ethertype == ETH_P_ARP) {
			arp++;
			printf("OMPKT iface=%s dir=%s eth=arp len=%zd smac=",
			       argv[1], outgoing ? "TX" : "RX", len);
			print_mac(buf + 6);
			printf(" dmac=");
			print_mac(buf);
			putchar('\n');
		} else if (ethertype == ETH_P_IP && len >= (ssize_t)(off + sizeof(struct iphdr))) {
			const struct iphdr *ip = (const struct iphdr *)(buf + off);
			size_t l4off = off + ip->ihl * 4;
			uint16_t sport = 0, dport = 0;
			uint8_t tcp_flags = 0;

			if (ip->protocol == IPPROTO_UDP && len >= (ssize_t)(l4off + sizeof(struct udphdr))) {
				const struct udphdr *udp = (const struct udphdr *)(buf + l4off);
				sport = ntohs(udp->source);
				dport = ntohs(udp->dest);
				if (sport == 67 || sport == 68 || dport == 67 || dport == 68) {
					dhcp++;
					interesting = 1;
				} else if (sport == 53 || dport == 53) {
					dns++;
					interesting = 1;
				}
			} else if (ip->protocol == IPPROTO_TCP && len >= (ssize_t)(l4off + 20)) {
				sport = ((uint16_t)buf[l4off] << 8) | buf[l4off + 1];
				dport = ((uint16_t)buf[l4off + 2] << 8) | buf[l4off + 3];
				tcp_flags = buf[l4off + 13];
				tcp++;
				if (tcp_flags & (0x02 | 0x04 | 0x01))
					interesting = 1;
			}
			if (interesting) {
				char src[INET_ADDRSTRLEN], dst[INET_ADDRSTRLEN];
				inet_ntop(AF_INET, &ip->saddr, src, sizeof(src));
				inet_ntop(AF_INET, &ip->daddr, dst, sizeof(dst));
				printf("OMPKT iface=%s dir=%s eth=ipv4 src=%s:%u dst=%s:%u proto=%u flags=%02x len=%zd smac=",
				       argv[1], outgoing ? "TX" : "RX", src, sport, dst, dport,
				       ip->protocol, tcp_flags, len);
				print_mac(buf + 6);
				printf(" dmac=");
				print_mac(buf);
				putchar('\n');
			}
		}

	report:
		if (monotonic_ms() >= next_report) {
			printf("OMPKT_SUM iface=%s rx_packets=%llu tx_packets=%llu rx_bytes=%llu tx_bytes=%llu arp=%llu dhcp=%llu dns=%llu tcp=%llu\n",
			       argv[1], rx_packets, tx_packets, rx_bytes, tx_bytes,
			       arp, dhcp, dns, tcp);
			fflush(stdout);
			next_report += 1000;
		}
	}
	close(fd);
	printf("OMPKT_END iface=%s rx_packets=%llu tx_packets=%llu rx_bytes=%llu tx_bytes=%llu arp=%llu dhcp=%llu dns=%llu tcp=%llu\n",
	       argv[1], rx_packets, tx_packets, rx_bytes, tx_bytes,
	       arp, dhcp, dns, tcp);
	return 0;
}
