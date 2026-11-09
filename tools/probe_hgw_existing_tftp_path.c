/* Bounded, synthetic-only UDP/TFTP probe. No firmware, MMIO or file writes. */
#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

int main(void)
{
    static const unsigned char rrq[] = "\0\1om-path-probe.bin\0octet\0";
    struct sockaddr_in server, peer, sender;
    struct timeval timeout = { 2, 0 };
    unsigned char packet[517], ack[4];
    unsigned int expected = 1, bytes = 0, datagrams = 0;
    int fd, have_peer = 0, result = 1;
    alarm(15);
    memset(&server, 0, sizeof(server));
    memset(&peer, 0, sizeof(peer));
    server.sin_family = AF_INET;
    server.sin_port = htons(69);
    if (inet_pton(AF_INET, "192.168.1.49", &server.sin_addr) != 1)
        return 2;
    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0)
        return 3;
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) ||
        sendto(fd, rrq, sizeof(rrq)-1, 0, (struct sockaddr *)&server,
               sizeof(server)) != (ssize_t)(sizeof(rrq)-1))
        goto done;
    while (++datagrams <= 64) {
        socklen_t size = sizeof(sender);
        ssize_t count = recvfrom(fd, packet, sizeof(packet), 0,
                                 (struct sockaddr *)&sender, &size);
        unsigned int block, payload, i;
        if (count < 4 || count > 516 || size != sizeof(sender) ||
            sender.sin_family != AF_INET ||
            sender.sin_addr.s_addr != server.sin_addr.s_addr ||
            packet[0] != 0 || packet[1] != 3)
            goto done;
        if (!have_peer) {
            peer = sender;
            have_peer = 1;
        } else if (sender.sin_port != peer.sin_port) {
            goto done;
        }
        block = ((unsigned int)packet[2] << 8) | packet[3];
        payload = (unsigned int)count - 4;
        if (block == expected) {
            if (bytes + payload > 4096)
                goto done;
            for (i = 0; i < payload; i++)
                if (packet[4+i] != (unsigned char)((bytes+i) & 255))
                    goto done;
            bytes += payload;
            expected++;
        } else if (expected <= 1 || block != expected-1) {
            goto done;
        }
        ack[0] = 0; ack[1] = 4;
        ack[2] = packet[2]; ack[3] = packet[3];
        if (sendto(fd, ack, sizeof(ack), 0, (struct sockaddr *)&peer,
                   sizeof(peer)) != (ssize_t)sizeof(ack))
            goto done;
        if (payload < 512) {
            if (bytes == 4096 && block == 9 && expected == 10) {
                static const char passed[] = "PASS_TFTP_SYNTHETIC bytes=4096 data_blocks=9\n";
                if (write(STDOUT_FILENO, passed, sizeof(passed)-1) == (ssize_t)(sizeof(passed)-1))
                    result = 0;
            }
            goto done;
        }
    }
done:
    if (close(fd))
        result = 1;
    _exit(result);
}
