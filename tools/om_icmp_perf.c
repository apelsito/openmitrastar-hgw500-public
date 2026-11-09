// SPDX-License-Identifier: GPL-2.0-only
#define _DEFAULT_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/ip.h>
#include <netinet/ip_icmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <sys/time.h>
#include <sys/types.h>
#include <unistd.h>

static unsigned long long now_us(void)
{
	struct timeval tv;

	gettimeofday(&tv, NULL);
	return (unsigned long long)tv.tv_sec * 1000000ULL + tv.tv_usec;
}

static void sleep_us(unsigned long usec)
{
	struct timeval tv;

	tv.tv_sec = usec / 1000000UL;
	tv.tv_usec = usec % 1000000UL;
	select(0, NULL, NULL, NULL, &tv);
}

static unsigned short checksum(const void *data, size_t length)
{
	const unsigned short *words = data;
	unsigned long sum = 0;

	while (length > 1) {
		sum += *words++;
		length -= 2;
	}
	if (length)
		sum += *(const unsigned char *)words;
	while (sum >> 16)
		sum = (sum & 0xffff) + (sum >> 16);
	return (unsigned short)~sum;
}

static unsigned long parse_ulong(const char *text, unsigned long min,
				 unsigned long max, const char *name)
{
	char *end = NULL;
	unsigned long value = strtoul(text, &end, 10);

	if (!text[0] || !end || *end || value < min || value > max) {
		fprintf(stderr, "invalid %s: %s\n", name, text);
		exit(2);
	}
	return value;
}

int main(int argc, char **argv)
{
	struct sockaddr_in target;
	unsigned long count;
	unsigned long payload_size;
	unsigned long interval_us;
	unsigned long settle_ms;
	unsigned char *packet;
	unsigned char rxbuf[2048];
	unsigned long sent = 0;
	unsigned long received = 0;
	unsigned short ident = (unsigned short)getpid();
	unsigned long long start;
	unsigned long long next_send;
	unsigned long long finish_send = 0;
	unsigned long long deadline;
	unsigned long long end;
	int fd;

	if (argc != 6) {
		fprintf(stderr,
			"usage: %s IPv4 count payload_bytes interval_us settle_ms\n",
			argv[0]);
		return 2;
	}
	count = parse_ulong(argv[2], 1, 100000, "count");
	payload_size = parse_ulong(argv[3], 8, 1400, "payload_bytes");
	interval_us = parse_ulong(argv[4], 100, 1000000, "interval_us");
	settle_ms = parse_ulong(argv[5], 100, 10000, "settle_ms");

	memset(&target, 0, sizeof(target));
	target.sin_family = AF_INET;
	if (inet_pton(AF_INET, argv[1], &target.sin_addr) != 1) {
		fprintf(stderr, "invalid target IPv4\n");
		return 2;
	}

	fd = socket(AF_INET, SOCK_RAW, IPPROTO_ICMP);
	if (fd < 0) {
		perror("socket");
		return 3;
	}
	if (fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) | O_NONBLOCK) < 0) {
		perror("fcntl");
		return 3;
	}
	packet = calloc(1, sizeof(struct icmphdr) + payload_size);
	if (!packet)
		return 3;
	memset(packet + sizeof(struct icmphdr), 0xa5, payload_size);

	start = now_us();
	next_send = start;
	deadline = start + count * interval_us + settle_ms * 1000ULL + 5000000ULL;
	while (now_us() < deadline) {
		unsigned long long now = now_us();
		ssize_t length;

		if (sent < count && now >= next_send) {
			struct icmphdr *icmp = (struct icmphdr *)packet;

			icmp->type = ICMP_ECHO;
			icmp->code = 0;
			icmp->un.echo.id = htons(ident);
			icmp->un.echo.sequence = htons((unsigned short)sent);
			icmp->checksum = 0;
			icmp->checksum = checksum(packet,
						  sizeof(*icmp) + payload_size);
			length = sendto(fd, packet, sizeof(*icmp) + payload_size, 0,
					(struct sockaddr *)&target, sizeof(target));
			if (length >= 0) {
				sent++;
				next_send = start + sent * interval_us;
				if (sent == count)
					finish_send = now_us();
			} else if (errno != EAGAIN && errno != EWOULDBLOCK &&
				   errno != ENOBUFS) {
				perror("sendto");
				break;
			}
		}

		for (;;) {
			struct iphdr *ip;
			struct icmphdr *icmp;
			unsigned int ip_length;

			length = recv(fd, rxbuf, sizeof(rxbuf), 0);
			if (length < 0) {
				if (errno != EAGAIN && errno != EWOULDBLOCK)
					perror("recv");
				break;
			}
			if ((size_t)length < sizeof(*ip) + sizeof(*icmp))
				continue;
			ip = (struct iphdr *)rxbuf;
			ip_length = ip->ihl * 4;
			if (ip_length < sizeof(*ip) ||
			    (size_t)length < ip_length + sizeof(*icmp))
				continue;
			icmp = (struct icmphdr *)(rxbuf + ip_length);
			if (icmp->type == ICMP_ECHOREPLY &&
			    ntohs(icmp->un.echo.id) == ident)
				received++;
		}

		if (sent == count && now_us() >= finish_send + settle_ms * 1000ULL)
			break;
		if (sent < count && now + 200 < next_send)
			sleep_us(100);
		else
			sleep_us(20);
	}
	end = now_us();
	if (!finish_send)
		finish_send = end;

	{
		unsigned long long send_ms = (finish_send - start + 999) / 1000;
		unsigned long long total_ms = (end - start + 999) / 1000;
		unsigned long long wire_bytes = sizeof(struct icmphdr) + payload_size;
		unsigned long long tx_kbps = send_ms ? sent * wire_bytes * 8 / send_ms : 0;
		unsigned long long rx_kbps = total_ms ? received * wire_bytes * 8 / total_ms : 0;
		unsigned long loss_permille = sent ? (sent - received) * 1000UL / sent : 1000;

		printf("OMICMPPERF target=%s sent=%lu received=%lu payload=%lu interval_us=%lu send_ms=%llu total_ms=%llu tx_kbps=%llu rx_kbps=%llu loss_permille=%lu\n",
		       argv[1], sent, received, payload_size, interval_us,
		       send_ms, total_ms, tx_kbps, rx_kbps, loss_permille);
	}

	free(packet);
	close(fd);
	return sent == count && received > 0 ? 0 : 4;
}
