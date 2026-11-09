#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L

/*
 * Host-side semantic test utility. Do not deploy this libc-linked build to
 * the HGW ARC700: use build_om_bridge_fdb_nolibc.sh, which compiles the
 * syscall-only tools/om_bridge_fdb_nolibc.c target artifact.
 */

#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <linux/if_bridge.h>
#include <linux/neighbour.h>
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
#include <net/if.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define APPLY_ACK "OPENMITRASTAR_FDB_RAM_ONLY"
#define FDB_RECORD_SIZE 16U

struct fdb_wire_entry {
	uint8_t mac[6];
	uint8_t port_lo;
	uint8_t is_local;
	uint32_t ageing_ticks;
	uint8_t port_hi;
	uint8_t pad;
	uint16_t unused;
};

struct port_map_entry {
	unsigned int port_no;
	char ifname[IFNAMSIZ];
};

static void usage(const char *prog)
{
	fprintf(stderr,
		"usage:\n"
		"  %s dump BRIDGE [MAC]\n"
		"  %s lookup BRIDGE MAC\n"
		"  %s decode FILE [MAC]\n"
		"  %s replace BRIDGE PORT MAC --apply %s\n"
		"  %s delete BRIDGE PORT MAC --apply %s\n",
		prog, prog, prog, prog, APPLY_ACK, prog, APPLY_ACK);
}

static int parse_mac(const char *text, uint8_t mac[6])
{
	unsigned int b[6];
	char tail;
	int i;

	if (sscanf(text, "%2x:%2x:%2x:%2x:%2x:%2x%c",
		   &b[0], &b[1], &b[2], &b[3], &b[4], &b[5], &tail) != 6)
		return -1;
	for (i = 0; i < 6; i++)
		mac[i] = (uint8_t)b[i];
	return 0;
}

static void format_mac(const uint8_t mac[6], char out[18])
{
	snprintf(out, 18, "%02x:%02x:%02x:%02x:%02x:%02x",
		 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

static unsigned int fdb_port_no(const struct fdb_wire_entry *entry)
{
	return entry->port_lo | ((unsigned int)entry->port_hi << 8);
}

static int read_uint_file(const char *path, unsigned int *value)
{
	FILE *fp;
	char text[64];
	char *end;
	unsigned long parsed;

	fp = fopen(path, "r");
	if (!fp)
		return -1;
	if (!fgets(text, sizeof(text), fp)) {
		fclose(fp);
		return -1;
	}
	fclose(fp);
	errno = 0;
	parsed = strtoul(text, &end, 0);
	if (errno || end == text)
		return -1;
	*value = (unsigned int)parsed;
	return 0;
}

static size_t load_port_map(const char *bridge, struct port_map_entry *map,
			    size_t cap)
{
	char directory[256], path[512];
	DIR *dir;
	struct dirent *entry;
	size_t count = 0;

	snprintf(directory, sizeof(directory), "/sys/class/net/%s/brif", bridge);
	dir = opendir(directory);
	if (!dir)
		return 0;
	while (count < cap && (entry = readdir(dir))) {
		unsigned int port_no;

		if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, ".."))
			continue;
		if (strlen(entry->d_name) >= IFNAMSIZ)
			continue;
		snprintf(path, sizeof(path), "/sys/class/net/%s/brif/%s/port_no",
			 bridge, entry->d_name);
		if (read_uint_file(path, &port_no))
			continue;
		map[count].port_no = port_no;
		memcpy(map[count].ifname, entry->d_name,
		       strlen(entry->d_name) + 1);
		count++;
	}
	closedir(dir);
	return count;
}

static const char *port_name(const struct port_map_entry *map, size_t count,
			     unsigned int port_no)
{
	size_t i;

	for (i = 0; i < count; i++)
		if (map[i].port_no == port_no)
			return map[i].ifname;
	return "unknown";
}

static int dump_stream(FILE *fp, const char *bridge, const uint8_t *filter,
		       int require_match)
{
	struct port_map_entry map[32];
	struct fdb_wire_entry entry;
	size_t map_count = 0;
	unsigned int records = 0, matches = 0;

	if (sizeof(entry) != FDB_RECORD_SIZE) {
		fprintf(stderr, "unexpected __fdb_entry ABI size: %u\n",
			(unsigned int)sizeof(entry));
		return 2;
	}
	if (bridge)
		map_count = load_port_map(bridge, map, 32);

	while (fread(&entry, 1, sizeof(entry), fp) == sizeof(entry)) {
		char mac_text[18];
		unsigned int port = fdb_port_no(&entry);

		records++;
		if (filter && memcmp(entry.mac, filter, 6))
			continue;
		matches++;
		format_mac(entry.mac, mac_text);
		printf("OMFDB bridge=%s mac=%s port_no=%u port=%s local=%u age_ticks=%u\n",
		       bridge ? bridge : "-", mac_text, port,
		       port_name(map, map_count, port), entry.is_local ? 1U : 0U,
		       entry.ageing_ticks);
	}
	if (ferror(fp)) {
		perror("read fdb");
		return 1;
	}
	printf("OMFDB_SUM bridge=%s records=%u matches=%u record_size=%u\n",
	       bridge ? bridge : "-", records, matches, FDB_RECORD_SIZE);
	if (require_match && !matches)
		return 3;
	return 0;
}

static int dump_bridge(const char *bridge, const uint8_t *filter,
		       int require_match)
{
	char path[256];
	FILE *fp;
	int rc;

	snprintf(path, sizeof(path), "/sys/class/net/%s/brforward", bridge);
	fp = fopen(path, "rb");
	if (!fp) {
		perror(path);
		return 1;
	}
	rc = dump_stream(fp, bridge, filter, require_match);
	fclose(fp);
	return rc;
}

static int addattr_l(struct nlmsghdr *nlh, size_t maxlen, int type,
		     const void *data, size_t len)
{
	size_t attr_len = RTA_LENGTH(len);
	size_t new_len = NLMSG_ALIGN(nlh->nlmsg_len) + RTA_ALIGN(attr_len);
	struct rtattr *rta;

	if (new_len > maxlen)
		return -1;
	rta = (struct rtattr *)((char *)nlh + NLMSG_ALIGN(nlh->nlmsg_len));
	rta->rta_type = type;
	rta->rta_len = attr_len;
	memcpy(RTA_DATA(rta), data, len);
	nlh->nlmsg_len = new_len;
	return 0;
}

static int port_belongs_to_bridge(const char *bridge, const char *port)
{
	char path[256], target[256];
	char *base;
	ssize_t len;

	snprintf(path, sizeof(path), "/sys/class/net/%s/master", port);
	len = readlink(path, target, sizeof(target) - 1);
	if (len < 0)
		return 0;
	target[len] = '\0';
	base = strrchr(target, '/');
	return base && !strcmp(base + 1, bridge);
}

static int netlink_ack(int fd, uint32_t seq)
{
	char buf[4096];
	ssize_t len;
	struct nlmsghdr *nlh;

	for (;;) {
		len = recv(fd, buf, sizeof(buf), 0);
		if (len < 0) {
			perror("netlink recv");
			return 1;
		}
		for (nlh = (struct nlmsghdr *)buf; NLMSG_OK(nlh, (unsigned int)len);
		     nlh = NLMSG_NEXT(nlh, len)) {
			struct nlmsgerr *err;

			if (nlh->nlmsg_seq != seq)
				continue;
			if (nlh->nlmsg_type != NLMSG_ERROR)
				continue;
			err = NLMSG_DATA(nlh);
			if (!err->error)
				return 0;
			errno = -err->error;
			perror("bridge fdb netlink");
			return 1;
		}
	}
}

static int modify_fdb(int add, const char *bridge, const char *port,
		      const uint8_t mac[6])
{
	struct {
		struct nlmsghdr nlh;
		struct ndmsg ndm;
		char attrs[128];
	} req;
	struct sockaddr_nl addr;
	unsigned int bridge_idx, port_idx;
	uint32_t seq = 0x4f4d4644U;
	int fd;

	bridge_idx = if_nametoindex(bridge);
	port_idx = if_nametoindex(port);
	if (!bridge_idx || !port_idx) {
		fprintf(stderr, "unknown bridge or port\n");
		return 2;
	}
	if (!port_belongs_to_bridge(bridge, port)) {
		fprintf(stderr, "%s is not enslaved to %s\n", port, bridge);
		return 2;
	}

	memset(&req, 0, sizeof(req));
	req.nlh.nlmsg_len = NLMSG_LENGTH(sizeof(req.ndm));
	req.nlh.nlmsg_type = add ? RTM_NEWNEIGH : RTM_DELNEIGH;
	req.nlh.nlmsg_flags = NLM_F_REQUEST | NLM_F_ACK;
	if (add)
		req.nlh.nlmsg_flags |= NLM_F_CREATE | NLM_F_REPLACE;
	req.nlh.nlmsg_seq = seq;
	req.ndm.ndm_family = AF_BRIDGE;
	req.ndm.ndm_ifindex = (int)port_idx;
	req.ndm.ndm_state = add ? NUD_NOARP : 0;
	req.ndm.ndm_flags = NTF_MASTER;
	if (addattr_l(&req.nlh, sizeof(req), NDA_LLADDR, mac, 6) ||
	    addattr_l(&req.nlh, sizeof(req), NDA_MASTER,
		      &bridge_idx, sizeof(bridge_idx))) {
		fprintf(stderr, "netlink request overflow\n");
		return 2;
	}

	fd = socket(AF_NETLINK, SOCK_RAW, NETLINK_ROUTE);
	if (fd < 0) {
		perror("netlink socket");
		return 1;
	}
	memset(&addr, 0, sizeof(addr));
	addr.nl_family = AF_NETLINK;
	if (sendto(fd, &req, req.nlh.nlmsg_len, 0,
		   (struct sockaddr *)&addr, sizeof(addr)) < 0) {
		perror("netlink send");
		close(fd);
		return 1;
	}
	if (netlink_ack(fd, seq)) {
		close(fd);
		return 1;
	}
	close(fd);
	return 0;
}

int main(int argc, char **argv)
{
	uint8_t mac[6], *filter = NULL;
	char mac_text[18];
	FILE *fp;
	int rc;

	if (argc >= 3 && !strcmp(argv[1], "dump")) {
		if (argc == 4) {
			if (parse_mac(argv[3], mac)) {
				fprintf(stderr, "invalid MAC\n");
				return 2;
			}
			filter = mac;
		} else if (argc != 3) {
			usage(argv[0]);
			return 2;
		}
		return dump_bridge(argv[2], filter, 0);
	}
	if (argc == 4 && !strcmp(argv[1], "lookup")) {
		if (parse_mac(argv[3], mac)) {
			fprintf(stderr, "invalid MAC\n");
			return 2;
		}
		return dump_bridge(argv[2], mac, 1);
	}
	if ((argc == 3 || argc == 4) && !strcmp(argv[1], "decode")) {
		if (argc == 4) {
			if (parse_mac(argv[3], mac)) {
				fprintf(stderr, "invalid MAC\n");
				return 2;
			}
			filter = mac;
		}
		fp = fopen(argv[2], "rb");
		if (!fp) {
			perror(argv[2]);
			return 1;
		}
		rc = dump_stream(fp, NULL, filter, argc == 4);
		fclose(fp);
		return rc;
	}
	if (argc == 7 && (!strcmp(argv[1], "replace") ||
			  !strcmp(argv[1], "delete"))) {
		if (strcmp(argv[5], "--apply") || strcmp(argv[6], APPLY_ACK)) {
			usage(argv[0]);
			return 2;
		}
		if (parse_mac(argv[4], mac)) {
			fprintf(stderr, "invalid MAC\n");
			return 2;
		}
		rc = modify_fdb(!strcmp(argv[1], "replace"), argv[2], argv[3], mac);
		if (rc)
			return rc;
		format_mac(mac, mac_text);
		printf("OMFDB_%s bridge=%s port=%s mac=%s state=%s classification=RAM_ONLY\n",
		       !strcmp(argv[1], "replace") ? "REPLACE" : "DELETE",
		       argv[2], argv[3], mac_text,
		       !strcmp(argv[1], "replace") ? "static-nonlocal" : "removed");
		return 0;
	}
	usage(argv[0]);
	return 2;
}
