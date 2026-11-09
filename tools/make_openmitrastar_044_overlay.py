#!/usr/bin/env python3
"""Generate OpenMitraStar 0.4.4 with no stock CGI upload backend.

This keeps the 0.4.2 modern UI and bin-aware backup mode, but replaces the
firmware upload path with a first-party /api/flash endpoint. The browser sends
the selected firmware as application/octet-stream, so the router does not need
multipart parsing or the old firmware.cgi binary.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools" / "make_openmitrastar_042_overlay.py"

spec = importlib.util.spec_from_file_location("omt042", BASE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
base = mod.base

base.VERSION = "openmitrastar-0.4.4-modern-ui-no-cgi-flash"
base.VERSION_DIR = base.ROOT / "versions" / base.VERSION
base.OVERLAY = base.VERSION_DIR / "overlay"
base.SRC_TS = base.VERSION_DIR / "src"

base.INDEX_HTML = base.INDEX_HTML.replace(
    '<form method="post" enctype="multipart/form-data" action="/api/flash" class="flash"><input type="hidden" name="act" value="1"><input type="file" name="upgradeFileName"><button class="primary">Flash webformat .bin</button></form>',
    '<form id="flash-form" class="flash"><input type="file" name="upgradeFileName" id="upgradeFileName" accept=".bin,application/octet-stream"><select name="target" title="Destination partition"><option value="live">live</option><option value="safety">safety</option></select><button class="primary">Flash webformat .bin</button></form>',
)

base.MINIHTTPD = """ # mini_httpd configuration file
data_dir=/var/www
port=80
host=0.0.0.0
cgipat=**/api/*
charset=UTF-8
certfile=/etc/minihttpd.pem
"""

base.MINIHTTPD_SSL = """ # mini_httpd configuration file
data_dir=/var/www
port=443
host=0.0.0.0
cgipat=**/api/*
charset=UTF-8
ssl
certfile=/etc/minihttpd.pem
"""

base.API_FLASH = r"""#!/bin/sh
. /var/www/api/_lib
tmp="/tmp/topaz-linux.lzma.img"
result="/tmp/result_upgrade"
max_size=7995392

query_value() {
  key="$1"
  printf '%s' "$QUERY_STRING" | tr '&' '\n' | sed -n "s/^$key=//p" | head -n1 | sed 's/+/ /g;s/%2F/\//g;s/%3A/:/g;s/%2E/./g;s/%2D/-/g;s/%5F/_/g;s/%20/ /g'
}

fail() {
  header_json
  msg="$(printf '%s' "$1" | tr '\r\n' '  ' | json_escape)"
  echo "{\"ok\":false,\"error\":\"$msg\"}"
  exit 0
}

[ "$REQUEST_METHOD" = "POST" ] || fail "POST required"
[ -n "$CONTENT_LENGTH" ] || fail "missing Content-Length"

case "$CONTENT_LENGTH" in *[!0-9]*|"") fail "invalid Content-Length";; esac
[ "$CONTENT_LENGTH" -gt 0 ] || fail "empty firmware image"
[ "$CONTENT_LENGTH" -le "$max_size" ] || fail "firmware image too large"

target="$(query_value target)"
case "$target" in live|safety) ;; "") target="live" ;; *) fail "invalid target partition";; esac

rm -f "$tmp" "$result"
cat > "$tmp"
actual="$(wc -c < "$tmp" 2>/dev/null | tr -d ' ')"
[ "$actual" = "$CONTENT_LENGTH" ] || fail "incomplete upload"

if command -v chkimage >/dev/null 2>&1; then
  chkimage -A arc -O linux -T kernel -v "$tmp" >/tmp/openmitrastar-flash-validate.log 2>&1 || {
    err="$(cat /tmp/openmitrastar-flash-validate.log 2>/dev/null | tr '\r\n' '  ')"
    fail "chkimage rejected firmware: $err"
  }
else
  magic="$(dd if="$tmp" bs=4 count=1 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n')"
  [ "$magic" = "27051956" ] || fail "uImage magic not found"
fi

/etc/default/led.sh fwupgrade >/dev/null 2>&1 &
sh /etc/default/FWupgrade.sh "$tmp" "$target" >/tmp/openmitrastar-flash-run.log 2>&1
backend="$(cat "$result" /tmp/openmitrastar-flash-run.log 2>/dev/null | tr '\r\n' '  ' | json_escape)"
if printf '%s' "$backend" | grep -q complete; then
  (sleep 2; reboot -d 6 >/dev/null 2>&1) &
  header_json
  echo "{\"ok\":true,\"target\":\"$target\",\"message\":\"firmware accepted; reboot scheduled\",\"backend\":\"$backend\"}"
else
  fail "firmware backend did not report complete: $backend"
fi
"""

base.FWUPGRADE_SH = r"""#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts
export PATH

RESULT="/tmp/result_upgrade"
LOG="/tmp/openmitrastar-fwupgrade.log"

fail() {
  echo "error: $1" > "$RESULT"
  echo "error: $1" >> "$LOG"
  exit 1
}

image="$1"
target="$2"
: > "$RESULT"
: > "$LOG"

[ -n "$image" ] || fail "missing firmware image path"
[ -f "$image" ] || fail "firmware image not found"
case "$target" in
  live|safety) ;;
  *) fail "invalid target partition" ;;
esac

size="$(wc -c < "$image" 2>/dev/null | tr -d ' ')"
case "$size" in *[!0-9]*|"") fail "invalid firmware size" ;; esac
[ "$size" -gt 0 ] || fail "empty firmware image"
[ "$size" -le 7995392 ] || fail "firmware image too large"

if command -v chkimage >/dev/null 2>&1; then
  chkimage -A arc -O linux -T kernel -v "$image" >> "$LOG" 2>&1 || fail "chkimage rejected firmware"
fi

sync
call_qcsapi flash_image_update "$image" "$target" > "$RESULT" 2>> "$LOG"
rc="$?"
sync

if [ "$rc" != "0" ]; then
  echo "call_qcsapi flash_image_update rc=$rc" >> "$LOG"
  exit "$rc"
fi

grep -q complete "$RESULT" 2>/dev/null || {
  echo "backend did not report complete" >> "$LOG"
  exit 1
}

exit 0
"""

base.APP_TS = base.APP_TS.replace(
    ' $("#rollback").addEventListener("click", async () => { if (!confirm("Activate rollback flag and reboot?")) return; $("#output").textContent = JSON.stringify(await api("/api/rollback", { method: "POST" }), null, 2); });',
    ''' $("#rollback").addEventListener("click", async () => { if (!confirm("Activate rollback flag and reboot?")) return; $("#output").textContent = JSON.stringify(await api("/api/rollback", { method: "POST" }), null, 2); });
 const flash = document.querySelector<HTMLFormElement>("#flash-form");
 flash?.addEventListener("submit", async e => {
  e.preventDefault();
  const file = (flash.querySelector<HTMLInputElement>("input[type=file]")?.files || [])[0];
  const target = flash.querySelector<HTMLSelectElement>("select[name=target]")?.value || "live";
  if (!file) { $("#output").textContent = "Select a firmware .bin first."; return; }
  if (file.size <= 0 || file.size > 7995392) { $("#output").textContent = "Invalid firmware size."; return; }
  if (!confirm(`Flash ${file.name} to ${target}?`)) return;
  const res = await fetch(`/api/flash?target=${encodeURIComponent(target)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
  const text = await res.text();
  try { $("#output").textContent = JSON.stringify(JSON.parse(text), null, 2); } catch { $("#output").textContent = text; }
 });''',
)

base.APP_JS = base.APP_JS.replace(
    '$("#rollback").addEventListener("click",async()=>{confirm("Activate rollback flag and reboot?")&&($("#output").textContent=JSON.stringify(await api("/api/rollback",{method:"POST"}),null,2))})',
    '$("#rollback").addEventListener("click",async()=>{confirm("Activate rollback flag and reboot?")&&($("#output").textContent=JSON.stringify(await api("/api/rollback",{method:"POST"}),null,2))});let f=$("#flash-form");f&&f.addEventListener("submit",async e=>{e.preventDefault();let file=f.querySelector("input[type=file]")?.files?.[0],target=f.querySelector("select[name=target]")?.value||"live";if(!file)return $("#output").textContent="Select a firmware .bin first.";if(file.size<=0||file.size>7995392)return $("#output").textContent="Invalid firmware size.";if(!confirm(`Flash ${file.name} to ${target}?`))return;let r=await fetch(`/api/flash?target=${encodeURIComponent(target)}`,{method:"POST",headers:{"Content-Type":"application/octet-stream"},body:file}),t=await r.text();try{$("#output").textContent=JSON.stringify(JSON.parse(t),null,2)}catch{$("#output").textContent=t}})',
)

_copy_runtime = base.copy_runtime
_write_web = base.write_web


def copy_runtime_044() -> None:
    _copy_runtime()
    base.write(base.OVERLAY / "etc" / "minihttpd.conf", base.MINIHTTPD)
    base.write(base.OVERLAY / "etc" / "minihttpd_ssl.conf", base.MINIHTTPD_SSL)
    base.write(base.OVERLAY / "etc" / "default" / "FWupgrade.sh", base.FWUPGRADE_SH, 0o755)
    base.write(
        base.OVERLAY / "etc" / "openmitrastar-release",
        "OPENMITRASTAR_VERSION=openmitrastar-0.4.4-modern-ui-no-cgi-flash\n"
        "OPENMITRASTAR_MODE=modern-ui-no-cgi-flash\n",
    )


def write_web_044() -> None:
    _write_web()
    www = base.OVERLAY / "var" / "www"
    base.write(www / "api" / "flash", base.API_FLASH, 0o755)
    for old in (www / "firmware.cgi", www / "firmware.html"):
        if old.exists():
            old.unlink()


base.copy_runtime = copy_runtime_044
base.write_web = write_web_044


if __name__ == "__main__":
    raise SystemExit(base.main())
