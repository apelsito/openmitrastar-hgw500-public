#define _GNU_SOURCE

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/if_vlan.h>
#include <linux/sockios.h>
#include <net/if.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define MAX_PACKETS 4096
#define MAX_PAYLOAD 1400
#define TOKEN_BYTES 32

static int find_vlan_interface(const char *parent, int vid, char *name, size_t name_size)
{
	FILE *config;
	char line[256];
	char candidate[IFNAMSIZ];
	char device[IFNAMSIZ];
	int candidate_vid;

	config = fopen("/proc/net/vlan/config", "r");
	if (!config)
		return 0;
	while (fgets(line, sizeof(line), config)) {
		memset(candidate, 0, sizeof(candidate));
		memset(device, 0, sizeof(device));
		candidate_vid = -1;
		if (sscanf(line, " %15s | %d | %15s", candidate, &candidate_vid, device) == 3 &&
			candidate_vid == vid && strcmp(device, parent) == 0) {
			strncpy(name, candidate, name_size - 1);
			name[name_size - 1] = '\0';
			fclose(config);
			return 1;
		}
	}
	fclose(config);
	return 0;
}

static void die(const char *message)
{
	fprintf(stderr, "OMF301_VLAN_ERROR=%s errno=%d\n", message, errno);
	exit(1);
}

static int interface_exists(int fd, const char *name)
{
	struct ifreq request;
	memset(&request, 0, sizeof(request));
	strncpy(request.ifr_name, name, IFNAMSIZ - 1);
	return ioctl(fd, SIOCGIFFLAGS, &request) == 0;
}

static void set_address(int fd, const char *name, unsigned long request_code,
		const char *address)
{
	struct ifreq request;
	struct sockaddr_in *socket_address;

	memset(&request, 0, sizeof(request));
	strncpy(request.ifr_name, name, IFNAMSIZ - 1);
	socket_address = (struct sockaddr_in *)&request.ifr_addr;
	socket_address->sin_family = AF_INET;
	if (inet_pton(AF_INET, address, &socket_address->sin_addr) != 1)
		die("invalid-ipv4-address");
	if (ioctl(fd, request_code, &request) != 0)
		die(request_code == SIOCSIFADDR ? "set-address" : "set-netmask");
}

static void set_up(int fd, const char *name)
{
	struct ifreq request;
	memset(&request, 0, sizeof(request));
	strncpy(request.ifr_name, name, IFNAMSIZ - 1);
	if (ioctl(fd, SIOCGIFFLAGS, &request) != 0)
		die("get-interface-flags");
	request.ifr_flags |= IFF_UP;
	if (ioctl(fd, SIOCSIFFLAGS, &request) != 0)
		die("set-interface-up");
}

static int delete_vlan(const char *name, int quiet)
{
	int fd;
	struct vlan_ioctl_args request;

	fd = socket(AF_INET, SOCK_DGRAM, 0);
	if (fd < 0)
		die("open-control-socket");
	if (!interface_exists(fd, name)) {
		close(fd);
		if (!quiet)
			printf("OMF301_VLAN_DELETE=already-absent interface=%s\n", name);
		return 0;
	}
	memset(&request, 0, sizeof(request));
	request.cmd = DEL_VLAN_CMD;
	strncpy(request.device1, name, sizeof(request.device1) - 1);
	if (ioctl(fd, SIOCSIFVLAN, &request) != 0) {
		close(fd);
		die("delete-vlan");
	}
	close(fd);
	if (!quiet)
		printf("OMF301_VLAN_DELETE=pass interface=%s\n", name);
	return 0;
}

static int create_vlan(const char *parent, const char *name, int vid,
		const char *address, const char *netmask)
{
	int fd;
	struct vlan_ioctl_args request;
	char actual_name[IFNAMSIZ];

	if (vid != 4090) {
		errno = EINVAL;
		die("vlan-id-must-be-4090");
	}
	if (strlen(parent) >= IFNAMSIZ || strlen(name) >= IFNAMSIZ) {
		errno = ENAMETOOLONG;
		die("interface-name-too-long");
	}
	fd = socket(AF_INET, SOCK_DGRAM, 0);
	if (fd < 0)
		die("open-control-socket");
	if (!interface_exists(fd, parent)) {
		close(fd);
		errno = ENODEV;
		die("parent-interface-missing");
	}
	if (interface_exists(fd, name)) {
		close(fd);
		errno = EEXIST;
		die("vlan-interface-already-exists");
	}

	memset(&request, 0, sizeof(request));
	request.cmd = ADD_VLAN_CMD;
	strncpy(request.device1, parent, sizeof(request.device1) - 1);
	request.u.VID = vid;
	if (ioctl(fd, SIOCSIFVLAN, &request) != 0) {
		close(fd);
		die("create-vlan");
	}
	memset(actual_name, 0, sizeof(actual_name));
	if (!find_vlan_interface(parent, vid, actual_name, sizeof(actual_name))) {
		close(fd);
		errno = ENODEV;
		die("created-vlan-not-found");
	}
	if (strcmp(actual_name, name) != 0) {
		close(fd);
		delete_vlan(actual_name, 1);
		errno = EINVAL;
		die("unexpected-vlan-interface-name");
	}
	set_address(fd, name, SIOCSIFADDR, address);
	set_address(fd, name, SIOCSIFNETMASK, netmask);
	set_up(fd, name);
	close(fd);
	printf("OMF301_VLAN_CREATE=pass parent=%s interface=%s vid=%d address=%s\n",
		parent, name, vid, address);
	return 0;
}

static int parse_packet(const char *buffer, size_t length, const char *token,
		unsigned int *sequence)
{
	char prefix[96];
	char *end;
	unsigned long value;
	int prefix_length;

	prefix_length = snprintf(prefix, sizeof(prefix), "LYOKO-VLAN1|%s|UP|", token);
	if (prefix_length <= 0 || (size_t)prefix_length >= length)
		return 0;
	if (memcmp(buffer, prefix, (size_t)prefix_length) != 0)
		return 0;
	errno = 0;
	value = strtoul(buffer + prefix_length, &end, 10);
	if (errno || end == buffer + prefix_length || *end != '|' || value >= MAX_PACKETS)
		return 0;
	*sequence = (unsigned int)value;
	return 1;
}

static long monotonic_ms(void)
{
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
		die("clock-gettime");
	return now.tv_sec * 1000L + now.tv_nsec / 1000000L;
}

static int serve(const char *address, int port, const char *token, int expected,
		int payload_bytes, int timeout_seconds, const char *result_path)
{
	int fd;
	int received = 0;
	int sent = 0;
	int invalid = 0;
	int timed_out = 0;
	uint8_t seen[MAX_PACKETS];
	char buffer[MAX_PAYLOAD + 1];
	char reply[MAX_PAYLOAD];
	struct sockaddr_in local;
	long deadline;

	if (strlen(token) != TOKEN_BYTES || expected < 1 || expected > MAX_PACKETS ||
		payload_bytes < 96 || payload_bytes > MAX_PAYLOAD || timeout_seconds < 5 ||
		timeout_seconds > 600) {
		errno = EINVAL;
		die("invalid-server-arguments");
	}
	memset(seen, 0, sizeof(seen));
	fd = socket(AF_INET, SOCK_DGRAM, 0);
	if (fd < 0)
		die("open-udp-socket");
	memset(&local, 0, sizeof(local));
	local.sin_family = AF_INET;
	local.sin_port = htons((uint16_t)port);
	if (inet_pton(AF_INET, address, &local.sin_addr) != 1)
		die("invalid-bind-address");
	if (bind(fd, (struct sockaddr *)&local, sizeof(local)) != 0)
		die("bind-udp-socket");

	deadline = monotonic_ms() + timeout_seconds * 1000L;
	while (received < expected) {
		struct pollfd poll_fd;
		struct sockaddr_in peer;
		socklen_t peer_length = sizeof(peer);
		ssize_t length;
		unsigned int sequence;
		int wait_ms = (int)(deadline - monotonic_ms());
		int prefix_length;

		if (wait_ms <= 0) {
			timed_out = 1;
			break;
		}
		poll_fd.fd = fd;
		poll_fd.events = POLLIN;
		poll_fd.revents = 0;
		if (poll(&poll_fd, 1, wait_ms) <= 0) {
			timed_out = 1;
			break;
		}
		length = recvfrom(fd, buffer, MAX_PAYLOAD, 0,
			(struct sockaddr *)&peer, &peer_length);
		if (length < 0)
			continue;
		buffer[length] = '\0';
		if (!parse_packet(buffer, (size_t)length, token, &sequence) ||
			sequence >= (unsigned int)expected) {
			invalid++;
			continue;
		}
		if (!seen[sequence]) {
			seen[sequence] = 1;
			received++;
		}
		memset(reply, 'x', (size_t)payload_bytes);
		prefix_length = snprintf(reply, (size_t)payload_bytes,
			"LYOKO-VLAN1|%s|DOWN|%u|", token, sequence);
		if (prefix_length <= 0 || prefix_length >= payload_bytes)
			die("format-reply");
		if (sendto(fd, reply, (size_t)payload_bytes, 0,
			(struct sockaddr *)&peer, peer_length) == payload_bytes)
			sent++;
	}
	close(fd);

	{
		FILE *result = fopen(result_path, "w");
		if (!result)
			die("open-result-file");
		fprintf(result,
			"{\"schema\":\"openmitrastar.f301-vlan-endpoint/v1\","
			"\"received_packets\":%d,\"sent_packets\":%d,"
			"\"invalid_packets\":%d,\"timed_out\":%s,\"pass\":%s}\n",
			received, sent, invalid, timed_out ? "true" : "false",
			(received == expected && sent == expected && invalid == 0) ? "true" : "false");
		if (fclose(result) != 0)
			die("close-result-file");
	}
	printf("OMF301_VLAN_SERVER=%s received=%d sent=%d invalid=%d\n",
		(received == expected && sent == expected && invalid == 0) ? "pass" : "fail",
		received, sent, invalid);
	return received == expected && sent == expected && invalid == 0 ? 0 : 1;
}

static int selftest(void)
{
	unsigned int sequence = 0;
	const char *token = "0123456789abcdef0123456789abcdef";
	const char *valid = "LYOKO-VLAN1|0123456789abcdef0123456789abcdef|UP|17|x";
	if (!parse_packet(valid, strlen(valid), token, &sequence) || sequence != 17)
		return 1;
	if (parse_packet("bad", 3, token, &sequence))
		return 1;
	puts("OMF301_VLAN_SELFTEST=pass");
	return 0;
}

int main(int argc, char **argv)
{
	if (argc == 2 && strcmp(argv[1], "selftest") == 0)
		return selftest();
	if (argc == 7 && strcmp(argv[1], "create") == 0)
		return create_vlan(argv[2], argv[3], atoi(argv[4]), argv[5], argv[6]);
	if (argc == 3 && strcmp(argv[1], "delete") == 0)
		return delete_vlan(argv[2], 0);
	if (argc == 9 && strcmp(argv[1], "serve") == 0)
		return serve(argv[2], atoi(argv[3]), argv[4], atoi(argv[5]), atoi(argv[6]),
			atoi(argv[7]), argv[8]);
	fprintf(stderr,
		"usage: %s selftest | create PARENT IFACE 4090 ADDRESS NETMASK | "
		"delete IFACE | serve ADDRESS PORT TOKEN COUNT BYTES TIMEOUT RESULT\n",
		argv[0]);
	return 2;
}
