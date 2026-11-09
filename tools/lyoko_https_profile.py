"""Pinned prospective HTTPS configuration; no deployment or radio operations."""
from __future__ import annotations

import hashlib

CONFIG_PATH = "etc/minihttpd-https.conf"
BINARY_PATH = "usr/sbin/mini_httpd-tls"
CIPHERS = ":".join([
    "TLS13-AES128-GCM-SHA256", "TLS13-AES256-GCM-SHA384", "TLS13-CHACHA20-POLY1305-SHA256",
    "ECDHE-RSA-AES128-GCM-SHA256", "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-AES128-GCM-SHA256", "ECDHE-ECDSA-AES256-GCM-SHA384",
    "DHE-RSA-AES128-GCM-SHA256", "DHE-RSA-AES256-GCM-SHA384",
])
OLD_ROUTE = b"cgipat=**.cgi|cgi-bin/*|api/status\n"
NEW_ROUTE = b"cgipat=**.cgi|cgi-bin/*|api/status|api/v1/*\n"
LEGACY_CONFIG = b"""# OpenMitraStar TLS 1.2 administration lane; runtime-only combined PEM.
data_dir=/www
port=443
host=192.168.1.90
cgipat=**.cgi|cgi-bin/*|api/status
charset=UTF-8
pidfile=/run/openmitrastar/web/mini_httpd-https.pid
ssl
certfile=/run/openmitrastar/secrets/https.pem
cipher=ECDHE+AESGCM:DHE+AESGCM
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def modernize_config(data: bytes) -> bytes:
    if data != LEGACY_CONFIG:
        raise ValueError("HTTPS config differs from the pinned F314 profile")
    return data.replace(b"TLS 1.2 administration", b"TLS 1.2/1.3 administration").replace(
        OLD_ROUTE, NEW_ROUTE).replace(b"cipher=ECDHE+AESGCM:DHE+AESGCM\n", b"cipher=" + CIPHERS.encode("ascii") + b"\n")


def routing_before_config() -> bytes:
    """Isolate old routing with the already-qualified new TLS cipher syntax."""
    return modernize_config(LEGACY_CONFIG).replace(NEW_ROUTE, OLD_ROUTE)


def loopback_config(data: bytes, port: int) -> bytes:
    """Change only endpoint and temporary cert/pid locations for host tests."""
    if data not in (modernize_config(LEGACY_CONFIG), routing_before_config()):
        raise ValueError("unrecognized HTTPS test profile")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("host test requires an unprivileged port")
    for before, after in (
        (b"port=443\n", f"port={port}\n".encode("ascii")),
        (b"host=192.168.1.90\n", b"host=127.0.0.1\n"),
        (b"pidfile=/run/openmitrastar/web/mini_httpd-https.pid\n", b"pidfile=/run/mini_httpd.pid\n"),
        (b"certfile=/run/openmitrastar/secrets/https.pem\n", b"certfile=/run/https.pem\n"),
    ):
        if data.count(before) != 1:
            raise ValueError("ambiguous HTTPS host-test substitution")
        data = data.replace(before, after)
    return data
