// Minimal OpenMitraStar runtime button daemon for RAM-only HGW500 parity tests.
// Listens to Linux input events already debounced by qtn-topaz-recovery.c.
// GPIO2 long press is emitted by the kernel as KEY_RFKILL; short press is OEM
// no-op and is intentionally not visible here.

#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef KEY_RFKILL
#define KEY_RFKILL 247
#endif

static const char *log_path = "/run/openmitrastar/buttond.log";
static volatile sig_atomic_t running = 1;

static void on_signal(int sig)
{
	(void)sig;
	running = 0;
}

static void append_log(const char *msg)
{
	int fd;

	fd = open(log_path, O_WRONLY | O_CREAT | O_APPEND, 0644);
	if (fd < 0)
		return;
	dprintf(fd, "%s\n", msg);
	close(fd);
}

static int file_contains(const char *path, const char *needle)
{
	FILE *fp;
	char buf[256];
	int found = 0;

	fp = fopen(path, "r");
	if (!fp)
		return 0;
	while (fgets(buf, sizeof(buf), fp)) {
		if (strstr(buf, needle)) {
			found = 1;
			break;
		}
	}
	fclose(fp);
	return found;
}

static int write_file(const char *path, const char *value)
{
	int fd;
	ssize_t len;

	fd = open(path, O_WRONLY);
	if (fd < 0)
		return -1;
	len = write(fd, value, strlen(value));
	close(fd);
	return len == (ssize_t)strlen(value) ? 0 : -1;
}

static int radio_enabled(void)
{
	if (file_contains("/run/openmitrastar/radio2g/state", "ready"))
		return 1;
	return system("/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$'") == 0;
}

static void sync_wlan2g_led(void)
{
	if (radio_enabled())
		write_file("/sys/class/leds/openmitrastar:green:wlan2g/brightness", "255\n");
	else
		write_file("/sys/class/leds/openmitrastar:green:wlan2g/brightness", "0\n");
}

static void toggle_wifi2g(void)
{
	if (radio_enabled()) {
		append_log("wifi2g-toggle phase=stop");
		(void)system("/usr/sbin/om-radio-stop >>/run/openmitrastar/buttond.log 2>&1");
		write_file("/sys/class/leds/openmitrastar:green:wlan2g/brightness", "0\n");
	} else {
		append_log("wifi2g-toggle phase=start");
		(void)system("/usr/sbin/om-radio2g-diag-start >>/run/openmitrastar/buttond.log 2>&1");
		sync_wlan2g_led();
	}
}

int main(int argc, char **argv)
{
	const char *dev = argc > 1 ? argv[1] : "/dev/input/event0";
	int fd;
	struct input_event ev;

	mkdir("/run/openmitrastar", 0755);
	signal(SIGTERM, on_signal);
	signal(SIGINT, on_signal);

	fd = open(dev, O_RDONLY);
	if (fd < 0) {
		dprintf(STDERR_FILENO, "open %s failed: %s\n", dev, strerror(errno));
		return 1;
	}

	append_log("buttond-start");
	sync_wlan2g_led();

	while (running) {
		ssize_t n = read(fd, &ev, sizeof(ev));

		if (n < 0) {
			if (errno == EINTR)
				continue;
			append_log("read-error");
			break;
		}
		if (n != sizeof(ev))
			continue;
		if (ev.type != EV_KEY || ev.value != 1)
			continue;
		if (ev.code == KEY_RFKILL) {
			append_log("event key=KEY_RFKILL action=wifi2g-toggle");
			toggle_wifi2g();
		} else if (ev.code == KEY_PROG1) {
			append_log("event key=KEY_PROG1 action=wifi5g-toggle-pending");
		}
	}

	append_log("buttond-stop");
	close(fd);
	return 0;
}
