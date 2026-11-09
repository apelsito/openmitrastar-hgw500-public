#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import time


def client_allowed(client_ip: str, allowed_clients: set[str]) -> bool:
    address = ipaddress.ip_address(client_ip)
    return not allowed_clients or address.is_loopback or str(address) in allowed_clients


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "OpenMitraStar-L2/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _client_allowed(self) -> bool:
        allowed = self.server.allowed_clients  # type: ignore[attr-defined]
        if client_allowed(self.client_address[0], allowed):
            return True
        self.send_error(403, "Client address is not allowed")
        return False

    def do_GET(self) -> None:
        if not self._client_allowed():
            return
        if self.path == "/":
            body = (
                b'<a href="/speed.bin">OpenMitraStar L2 download</a>\n'
                b'<p>PUT or POST /upload.bin for upload measurement.</p>\n'
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path != "/speed.bin":
            self.send_error(404)
            return

        total = self.server.payload_bytes  # type: ignore[attr-defined]
        block = b"\0" * 65536
        sent = 0
        started = time.monotonic()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(total))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while sent < total:
                chunk = block[: min(len(block), total - sent)]
                self.wfile.write(chunk)
                sent += len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        elapsed = max(time.monotonic() - started, 1e-6)
        mbps = sent * 8 / elapsed / 1_000_000
        print(
            f"OML2_HTTP_RESULT client={self.client_address[0]} bytes={sent} "
            f"direction=ap-to-client seconds={elapsed:.3f} mbps={mbps:.3f}",
            flush=True,
        )

    def _receive_upload(self) -> None:
        if not self._client_allowed():
            return
        if self.path != "/upload.bin":
            self.send_error(404)
            return
        raw_length = self.headers.get("Content-Length", "")
        try:
            total = int(raw_length)
        except ValueError:
            self.send_error(411, "Content-Length required")
            return
        maximum = self.server.max_upload_bytes  # type: ignore[attr-defined]
        if total <= 0 or total > maximum:
            self.send_error(413, "Upload outside configured bounds")
            return

        received = 0
        started = time.monotonic()
        while received < total:
            chunk = self.rfile.read(min(65536, total - received))
            if not chunk:
                break
            received += len(chunk)
        elapsed = max(time.monotonic() - started, 1e-6)
        mbps = received * 8 / elapsed / 1_000_000
        body = json.dumps(
            {"bytes": received, "seconds": round(elapsed, 6), "mbps": round(mbps, 6)},
            sort_keys=True,
        ).encode("ascii") + b"\n"
        status = 200 if received == total else 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        print(
            f"OML2_HTTP_RESULT client={self.client_address[0]} bytes={received} "
            f"direction=client-to-ap seconds={elapsed:.3f} mbps={mbps:.3f}",
            flush=True,
        )

    def do_POST(self) -> None:
        self._receive_upload()

    def do_PUT(self) -> None:
        self._receive_upload()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8008)
    parser.add_argument("--mib", type=int, default=32)
    parser.add_argument("--max-upload-mib", type=int, default=64)
    parser.add_argument("--allowed-client", action="append", default=[])
    args = parser.parse_args()
    if not 1 <= args.mib <= 256:
        raise SystemExit("--mib must be 1..256")
    if not 1 <= args.max_upload_mib <= 256:
        raise SystemExit("--max-upload-mib must be 1..256")
    try:
        allowed_clients = {str(ipaddress.ip_address(value)) for value in args.allowed_client}
    except ValueError as exc:
        raise SystemExit(f"invalid --allowed-client: {exc}") from exc
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.payload_bytes = args.mib * 1024 * 1024  # type: ignore[attr-defined]
    server.max_upload_bytes = args.max_upload_mib * 1024 * 1024  # type: ignore[attr-defined]
    server.allowed_clients = allowed_clients  # type: ignore[attr-defined]
    allowed_label = ",".join(sorted(allowed_clients)) if allowed_clients else "any"
    print(
        f"OML2_HTTP_READY bind={args.bind} port={args.port} "
        f"download_bytes={server.payload_bytes} max_upload_bytes={server.max_upload_bytes} "
        f"allowed_clients={allowed_label}",
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
