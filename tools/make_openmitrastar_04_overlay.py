#!/usr/bin/env python3
"""Generate OpenMitraStar 0.4 modern UI + API overlay.

This version replaces the legacy webroot with a compact static UI and small
CGI-style endpoints served under /api/* without exposing .cgi routes in the UX.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


VERSION = "openmitrastar-0.4-modern-ui-lite"
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOTFS = ROOT / "work" / "revival" / "rootfs"
SRC_WWW = SRC_ROOTFS / "var" / "www"
PREV_OVERLAY = ROOT / "versions" / "revival-0.2.1-openmitrastar-statusfix" / "overlay"
VERSION_DIR = ROOT / "versions" / VERSION
OVERLAY = VERSION_DIR / "overlay"
SRC_TS = VERSION_DIR / "src"


CAPABILITIES = [
    {"id": "wifi.24.enable", "group": "WiFi 2.4G", "backend": "qweconfig/qcsapi", "risk": "Can disconnect 2.4G clients.", "legal": "No RF issue unless channel/power changes."},
    {"id": "wifi.24.ssid", "group": "WiFi 2.4G", "backend": "qweconfig", "risk": "Clients must reconnect after SSID change.", "legal": "No RF issue."},
    {"id": "wifi.24.security", "group": "WiFi 2.4G", "backend": "qweconfig/hostapd", "risk": "WEP/TKIP/WPS are weak; password changes disconnect clients.", "legal": "No RF issue."},
    {"id": "wifi.24.channel", "group": "WiFi 2.4G", "backend": "qweconfig/qcsapi", "risk": "Bad channel can reduce throughput.", "legal": "Use ES/EU allowed 2.4G channels."},
    {"id": "wifi.24.bandwidth", "group": "WiFi 2.4G", "backend": "qweconfig/qcsapi", "risk": "40 MHz can hurt dense environments.", "legal": "RF coexistence rules apply."},
    {"id": "wifi.24.wmm", "group": "WiFi 2.4G", "backend": "qweconfig", "risk": "Disabling can lower modern client performance.", "legal": "No RF issue."},
    {"id": "wifi.24.wps", "group": "WiFi 2.4G", "backend": "qweconfig/hostapd", "risk": "WPS PIN is weak; keep off unless pairing.", "legal": "No RF issue."},
    {"id": "wifi.24.mac_filter", "group": "WiFi 2.4G", "backend": "qweconfig/hostapd", "risk": "Wrong allow list can lock out devices.", "legal": "No RF issue."},
    {"id": "wifi.5.enable", "group": "WiFi 5G", "backend": "qcsapi", "risk": "Can disconnect all 5G clients.", "legal": "No RF issue unless channel/power changes."},
    {"id": "wifi.5.ssid", "group": "WiFi 5G", "backend": "qcsapi/hostapd", "risk": "Clients must reconnect after SSID change.", "legal": "No RF issue."},
    {"id": "wifi.5.channel", "group": "WiFi 5G", "backend": "qcsapi", "risk": "DFS channels can move or pause after radar events.", "legal": "ES/EU DFS/channel limits apply."},
    {"id": "wifi.5.bandwidth", "group": "WiFi 5G", "backend": "qcsapi set_bw", "risk": "80 MHz can be unstable in noisy environments.", "legal": "ES/EU RF limits apply."},
    {"id": "wifi.5.tx_power", "group": "WiFi 5G", "backend": "qcsapi", "risk": "Too low drops clients; too high can be illegal/unstable.", "legal": "ES/EU EIRP limits apply."},
    {"id": "wifi.5.dfs_ocac", "group": "WiFi 5G", "backend": "qcsapi DFS", "risk": "Wrong DFS policy can make channels unavailable.", "legal": "DFS is mandatory on affected channels."},
    {"id": "wifi.5.qhop", "group": "WiFi 5G", "backend": "qweconfig/qfdr", "risk": "Wrong profile can break repeater/IPTV/data mode.", "legal": "Follows channel/power rules."},
    {"id": "wifi.5.pmf", "group": "WiFi 5G", "backend": "qcsapi set_pmf", "risk": "Can disconnect legacy clients.", "legal": "No RF issue."},
    {"id": "wifi.5.beamforming", "group": "WiFi 5G", "backend": "qcsapi", "risk": "Can require radio restart.", "legal": "No RF issue."},
    {"id": "wifi.5.mcs", "group": "WiFi 5G", "backend": "qcsapi set_mcs_rate", "risk": "Fixed high MCS can break distant clients.", "legal": "No RF issue."},
    {"id": "lan.ip", "group": "LAN", "backend": "ifconfig/config", "risk": "Wrong IP can make the device unreachable.", "legal": "No RF issue."},
    {"id": "lan.dhcp", "group": "LAN", "backend": "config/DHCP", "risk": "Bad range/gateway/DNS can break clients.", "legal": "No RF issue."},
    {"id": "lan.bridge", "group": "LAN", "backend": "bridge/vlan scripts", "risk": "Bad bridge/VLAN can cut access.", "legal": "No RF issue."},
    {"id": "services.tr069", "group": "Services", "backend": "process/init", "risk": "Disabling provider management is intended for OpenMitraStar.", "legal": "Local device management."},
    {"id": "services.telnet", "group": "Security", "backend": "inetd", "risk": "Telnet is plaintext; disable when not needed.", "legal": "Local admin surface."},
    {"id": "services.httpd", "group": "Services", "backend": "mini_httpd", "risk": "Stopping HTTP can lock out web UI.", "legal": "No RF issue."},
    {"id": "backup.config", "group": "Backup Mode", "backend": "persistent config files", "risk": "Contains secrets; download only locally.", "legal": "Authorized preservation."},
    {"id": "backup.firmware", "group": "Backup Mode", "backend": "linux_live MTD stream", "risk": "Raw dump may not equal webformat image.", "legal": "Authorized preservation."},
    {"id": "flash.webformat", "group": "Backup Mode", "backend": "stock firmware updater backend", "risk": "Wrong image can brick; validate before apply.", "legal": "Use authorized firmware only."},
    {"id": "expert.qweconfig", "group": "Expert", "backend": "qweconfig raw key/value", "risk": "Can break WiFi/bridge; backup first.", "legal": "RF law applies to RF keys."},
]


APP_TS = r"""type Capability = { id: string; group: string; backend: string; risk: string; legal: string };
type Status = { version?: string; uptime?: string; mem_total_kb?: string; mem_free_kb?: string; bridge?: string; services?: Record<string,string>; radio?: Record<string,string> };

const $ = <T extends Element = Element>(selector: string): T => document.querySelector(selector) as T;
const api = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(path, init);
  const text = await res.text();
  try { return JSON.parse(text) as T; } catch { return ({ ok: res.ok, raw: text } as T); }
};

const state: { caps: Capability[]; status: Status } = { caps: [], status: {} };

function riskPill(text: string) {
  return `<span class="risk" title="${escapeHtml(text)}">?</span>`;
}

function escapeHtml(v: unknown) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c] || c));
}

function groupCaps() {
  return state.caps.reduce<Record<string, Capability[]>>((acc, cap) => {
    (acc[cap.group] ||= []).push(cap);
    return acc;
  }, {});
}

function renderStatus() {
  const s = state.status;
  $("#status-grid").innerHTML = [
    ["Version", s.version || "unknown"],
    ["Uptime", s.uptime || "unknown"],
    ["Mem free", `${s.mem_free_kb || "?"} / ${s.mem_total_kb || "?"} kB`],
    ["Bridge", s.bridge || "unknown"]
  ].map(([k,v]) => `<div class="metric"><b>${k}</b><span>${escapeHtml(v)}</span></div>`).join("");
  const services = s.services || {};
  $("#services-list").innerHTML = Object.keys(services).map(k => `<div class="row"><span>${escapeHtml(k)}</span><code>${escapeHtml(services[k])}</code></div>`).join("");
  const radio = s.radio || {};
  $("#radio-list").innerHTML = Object.keys(radio).map(k => `<div class="row"><span>${escapeHtml(k)}</span><code>${escapeHtml(radio[k])}</code></div>`).join("");
}

function renderCapabilities(filter = "") {
  const q = filter.toLowerCase();
  const groups = groupCaps();
  $("#capabilities").innerHTML = Object.keys(groups).map(group => {
    const items = groups[group].filter(c => !q || `${c.id} ${c.group} ${c.backend} ${c.risk} ${c.legal}`.toLowerCase().includes(q));
    if (!items.length) return "";
    return `<section class="panel"><h2>${escapeHtml(group)}</h2>${items.map(c => `
      <div class="cap">
        <div><strong>${escapeHtml(c.id)}</strong> ${riskPill(`${c.risk}\n${c.legal}`)}<p>${escapeHtml(c.backend)}</p></div>
        <span>${escapeHtml(c.legal)}</span>
      </div>`).join("")}</section>`;
  }).join("");
}

async function loadAll() {
  state.status = await api<Status>("/api/status");
  state.caps = (await api<{ capabilities: Capability[] }>("/api/capabilities")).capabilities || [];
  renderStatus();
  renderCapabilities(($("#search") as HTMLInputElement).value);
}

async function postForm(path: string, form: HTMLFormElement) {
  const body = new URLSearchParams(new FormData(form) as any);
  const res = await api<any>(path, { method: "POST", body });
  $("#output").textContent = JSON.stringify(res, null, 2);
  await loadAll();
}

function bind() {
  $("#search").addEventListener("input", e => renderCapabilities((e.target as HTMLInputElement).value));
  $("#refresh").addEventListener("click", () => loadAll());
  $("#services-form").addEventListener("submit", e => { e.preventDefault(); postForm("/api/services", e.target as HTMLFormElement); });
  $("#expert-form").addEventListener("submit", e => { e.preventDefault(); postForm("/api/wifi", e.target as HTMLFormElement); });
  $("#rollback").addEventListener("click", async () => {
    if (!confirm("Activar rollback y reiniciar?")) return;
    $("#output").textContent = JSON.stringify(await api("/api/rollback", { method: "POST" }), null, 2);
  });
}

document.addEventListener("DOMContentLoaded", () => { bind(); loadAll(); });
"""


APP_JS = r"""const $=s=>document.querySelector(s),api=async(p,i)=>{const r=await fetch(p,i),t=await r.text();try{return JSON.parse(t)}catch{return{ok:r.ok,raw:t}}},state={caps:[],status:{}};function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]||c))}function rp(t){return`<span class="risk" title="${esc(t)}">?</span>`}function groups(){return state.caps.reduce((a,c)=>((a[c.group]||(a[c.group]=[])).push(c),a),{})}function renderStatus(){const s=state.status;$("#status-grid").innerHTML=[["Version",s.version||"unknown"],["Uptime",s.uptime||"unknown"],["Mem free",`${s.mem_free_kb||"?"} / ${s.mem_total_kb||"?"} kB`],["Bridge",s.bridge||"unknown"]].map(([k,v])=>`<div class="metric"><b>${k}</b><span>${esc(v)}</span></div>`).join("");let o=s.services||{};$("#services-list").innerHTML=Object.keys(o).map(k=>`<div class="row"><span>${esc(k)}</span><code>${esc(o[k])}</code></div>`).join("");o=s.radio||{};$("#radio-list").innerHTML=Object.keys(o).map(k=>`<div class="row"><span>${esc(k)}</span><code>${esc(o[k])}</code></div>`).join("")}function renderCapabilities(f=""){const q=f.toLowerCase(),g=groups();$("#capabilities").innerHTML=Object.keys(g).map(n=>{const it=g[n].filter(c=>!q||`${c.id} ${c.group} ${c.backend} ${c.risk} ${c.legal}`.toLowerCase().includes(q));return it.length?`<section class="panel"><h2>${esc(n)}</h2>${it.map(c=>`<div class="cap"><div><strong>${esc(c.id)}</strong> ${rp(`${c.risk}\n${c.legal}`)}<p>${esc(c.backend)}</p></div><span>${esc(c.legal)}</span></div>`).join("")}</section>`:""}).join("")}async function loadAll(){state.status=await api("/api/status");state.caps=(await api("/api/capabilities")).capabilities||[];renderStatus();renderCapabilities($("#search").value)}async function postForm(p,f){const b=new URLSearchParams(new FormData(f));$("#output").textContent=JSON.stringify(await api(p,{method:"POST",body:b}),null,2);await loadAll()}function bind(){$("#search").addEventListener("input",e=>renderCapabilities(e.target.value));$("#refresh").addEventListener("click",loadAll);$("#services-form").addEventListener("submit",e=>(e.preventDefault(),postForm("/api/services",e.target)));$("#expert-form").addEventListener("submit",e=>(e.preventDefault(),postForm("/api/wifi",e.target)));$("#rollback").addEventListener("click",async()=>{confirm("Activar rollback y reiniciar?")&&($("#output").textContent=JSON.stringify(await api("/api/rollback",{method:"POST"}),null,2))})}document.addEventListener("DOMContentLoaded",()=>{bind();loadAll()});"""


INDEX_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenMitraStar</title>
<link rel="stylesheet" href="/app.css">
</head>
<body>
<header><div><h1>OpenMitraStar</h1><p>UI ligera, capacidades completas y backup mode</p></div><button id="refresh">Refrescar</button></header>
<main>
<section class="panel hero"><h2>Dashboard</h2><div id="status-grid" class="grid"></div></section>
<section class="split"><div class="panel"><h2>Radio</h2><div id="radio-list"></div></div><div class="panel"><h2>Servicios</h2><div id="services-list"></div><form id="services-form"><select name="profile"><option value="fast">fast</option><option value="balanced">balanced</option><option value="stock">stock</option></select><button>Aplicar perfil</button></form></div></section>
<section class="panel"><h2>Buscar capacidades</h2><input id="search" placeholder="wifi, dfs, qhop, dhcp, backup, qweconfig..."></section>
<div id="capabilities"></div>
<section class="panel"><h2>Experto raw</h2><p>Escribe una clave qweconfig y valor. Puede dejar el dispositivo mal configurado.</p><form id="expert-form"><input name="key" placeholder="ej. scs.wlan1"><input name="value" placeholder="valor"><button>Aplicar qweconfig</button></form></section>
<section class="panel"><h2>Backup mode</h2><div class="actions"><a class="button" href="/api/backup/config">Descargar config</a><a class="button" href="/api/backup/firmware">Dump firmware raw</a><button id="rollback">Rollback + reboot</button></div><form method="post" enctype="multipart/form-data" action="/api/flash"><input type="hidden" name="act" value="1"><input type="file" name="upgradeFileName"><button>Flashear .bin</button></form></section>
<section class="panel"><h2>Salida API</h2><pre id="output"></pre></section>
</main>
<script src="/app.js"></script>
</body>
</html>
"""


FIRMWARE_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>OpenMitraStar flash</title></head>
<body><h1>OpenMitraStar firmware update</h1><p>Firmware upload processed. The device may reboot if the image was accepted.</p></body></html>
"""


APP_CSS = """*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif;background:#f5f7f9;color:#17202a}header{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:18px 22px;background:#111827;color:white}h1,h2,p{margin:0}h2{font-size:16px;margin-bottom:12px}main{max-width:1160px;margin:0 auto;padding:18px}.panel{background:white;border:1px solid #d9e0e7;border-radius:8px;padding:14px;margin-bottom:14px}.hero{border-left:4px solid #2563eb}.split{display:grid;grid-template-columns:1fr 1fr;gap:14px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.metric,.row,.cap{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;border-top:1px solid #edf1f5;padding:9px 0}.metric{display:block;border:1px solid #edf1f5;border-radius:6px;padding:10px}.metric b{display:block;color:#526070;font-size:12px}.metric span{font-size:18px}code,pre{background:#101827;color:#d1e7ff;border-radius:6px}code{padding:2px 5px}pre{padding:12px;overflow:auto;min-height:44px}input,select,button,.button{height:34px;border:1px solid #b9c4d0;border-radius:6px;padding:0 10px;background:white;color:#17202a;text-decoration:none;display:inline-flex;align-items:center}button,.button{background:#2563eb;color:white;border-color:#2563eb;cursor:pointer}form,.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.risk{display:inline-grid;place-items:center;width:17px;height:17px;border-radius:50%;background:#fff7d6;color:#7a4b00;border:1px solid #e0bd56;font-weight:700;cursor:help}.cap p{color:#526070;margin-top:2px}.cap>span{max-width:40%;color:#526070}@media(max-width:760px){.split,.grid{grid-template-columns:1fr}header{align-items:flex-start;flex-direction:column}.cap{display:block}.cap>span{max-width:none;display:block;margin-top:6px}}"""


API_LIB = r"""#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts
export PATH
json_escape() { sed 's/\\/\\\\/g;s/"/\\"/g'; }
header_json() { echo "Content-Type: application/json"; echo "Cache-Control: no-store"; echo; }
header_bin() { echo "Content-Type: application/octet-stream"; echo "Cache-Control: no-store"; echo "Content-Disposition: attachment; filename=\"$1\""; echo; }
kv() { key="$1"; printf '%s' "$BODY" | tr '&' '\n' | sed -n "s/^$key=//p" | head -n1 | sed 's/+/ /g;s/%2F/\//g;s/%3A/:/g;s/%2E/./g;s/%2D/-/g;s/%5F/_/g;s/%20/ /g'; }
read_body() { BODY=""; [ -n "$CONTENT_LENGTH" ] && BODY="$(dd bs=1 count="$CONTENT_LENGTH" 2>/dev/null)"; }
pid_state() { p="$(ps | grep "$1" | grep -v grep | awk '{print $1}' | tr '\n' ' ')"; [ -n "$p" ] && echo "running:$p" || echo "stopped"; }
"""


API_STATUS = r"""#!/bin/sh
. /var/www/api/_lib
header_json
ver="$(cat /etc/openmitrastar-release 2>/dev/null | tr '\n' ' ' | json_escape)"
mt="$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null)"
mf="$(awk '/MemFree/{print $2}' /proc/meminfo 2>/dev/null)"
up="$(cut -d' ' -f1 /proc/uptime 2>/dev/null)"
br="$(ifconfig br0 2>/dev/null | awk '/inet addr/{print $2}' | sed 's/addr://')"
mode="$(call_qcsapi get_mode wifi0 2>/dev/null | json_escape)"
chan="$(call_qcsapi get_channel wifi0 2>/dev/null | json_escape)"
bw="$(call_qcsapi get_bw wifi0 2>/dev/null | json_escape)"
region="$(call_qcsapi get_regulatory_region wifi0 2>/dev/null | json_escape)"
cat <<EOF
{"version":"$ver","uptime":"$up","mem_total_kb":"$mt","mem_free_kb":"$mf","bridge":"$br","services":{"tr69c":"$(pid_state tr69c)","qharvestd":"$(pid_state qharvestd)","pktlogger":"$(pid_state pktlogger_d)","mini_httpd":"$(pid_state mini_httpd)","telnetd":"$(pid_state telnetd)"},"radio":{"wifi0_mode":"$mode","wifi0_channel":"$chan","wifi0_bw":"$bw","wifi0_region":"$region"}}
EOF
"""


API_CAPS = r"""#!/bin/sh
echo "Content-Type: application/json"
echo "Cache-Control: no-store"
echo
cat /etc/openmitrastar-capabilities.json
"""


API_SERVICES = r"""#!/bin/sh
. /var/www/api/_lib
read_body
profile="$(kv profile)"
[ -z "$profile" ] && profile="balanced"
case "$profile" in
  stock) touch /mnt/ccc/openmitrastar-disable 2>/dev/null ;;
  balanced) rm -f /mnt/ccc/openmitrastar-disable 2>/dev/null; OPENMITRASTAR_PROFILE=balanced /scripts/openmitrastar-apply now 2>/dev/null ;;
  fast) rm -f /mnt/ccc/openmitrastar-disable 2>/dev/null; OPENMITRASTAR_PROFILE=fast /scripts/openmitrastar-apply now 2>/dev/null ;;
esac
header_json
echo "{\"ok\":true,\"profile\":\"$profile\"}"
"""


API_WIFI = r"""#!/bin/sh
. /var/www/api/_lib
if [ "$REQUEST_METHOD" = "POST" ]; then
  read_body
  key="$(kv key)"
  value="$(kv value)"
  if [ -n "$key" ]; then
    case "$key" in *[!A-Za-z0-9._-]*) header_json; echo '{"ok":false,"error":"invalid key"}'; exit 0;; esac
    qweconfig set "$key" "$value" >/tmp/openmitrastar-qweconfig.log 2>&1
    rc=$?
    header_json
    msg="$(cat /tmp/openmitrastar-qweconfig.log 2>/dev/null | json_escape)"
    echo "{\"ok\":$([ $rc -eq 0 ] && echo true || echo false),\"key\":\"$key\",\"message\":\"$msg\"}"
    exit 0
  fi
fi
header_json
ssid="$(qweconfig get ssid.wlan1 2>/dev/null | json_escape)"
mode="$(qweconfig get mode.wlan1 2>/dev/null | json_escape)"
chan="$(call_qcsapi get_channel wifi0 2>/dev/null | json_escape)"
bw="$(call_qcsapi get_bw wifi0 2>/dev/null | json_escape)"
echo "{\"ssid\":\"$ssid\",\"mode\":\"$mode\",\"wifi0_channel\":\"$chan\",\"wifi0_bw\":\"$bw\"}"
"""


API_LAN = r"""#!/bin/sh
. /var/www/api/_lib
header_json
ip="$(ifconfig br0 2>/dev/null | awk '/inet addr/{print $2}' | sed 's/addr://')"
mask="$(ifconfig br0 2>/dev/null | awk '/Mask:/{print $4}' | sed 's/Mask://')"
echo "{\"br0_ip\":\"$ip\",\"br0_mask\":\"$mask\",\"note\":\"LAN persistent writes are exposed through expert/config backup in this build.\"}"
"""


API_BACKUP_CONFIG = r"""#!/bin/sh
. /var/www/api/_lib
header_bin "openmitrastar-config-backup.txt"
echo "# OpenMitraStar config backup"
echo "# Generated on device. Contains secrets; store locally."
for f in /mnt/ccc/config.xml /mnt/ccc/config.default.xml /mnt/ccc/wireless_conf.txt /mnt/jffs2/hostapd.conf /mnt/jffs2/wpa_supplicant.conf /mnt/jffs2/qwe.conf /etc/qwe.conf; do
  [ -f "$f" ] || continue
  echo "----- BEGIN $f -----"
  cat "$f"
  echo "----- END $f -----"
done
"""


API_BACKUP_FIRMWARE = r"""#!/bin/sh
. /var/www/api/_lib
part="$(grep '\"linux_live\"' /proc/mtd 2>/dev/null | awk -F: '{print $1}' | head -n1)"
[ -z "$part" ] && part="$(grep linux /proc/mtd 2>/dev/null | awk -F: '{print $1}' | head -n1)"
header_bin "raw-linux-live-dump.bin"
if [ -n "$part" ] && [ -e "/dev/$part" ]; then
  cat "/dev/$part"
else
  echo "linux_live partition not found"
fi
"""


API_BACKUP_RESTORE = r"""#!/bin/sh
. /var/www/api/_lib
header_json
echo '{"ok":false,"error":"restore upload is intentionally not automatic in 0.4; flash/config restore needs explicit staged validation"}'
"""


API_ROLLBACK = r"""#!/bin/sh
. /var/www/api/_lib
touch /mnt/ccc/openmitrastar-disable 2>/dev/null
(sleep 2; reboot) >/dev/null 2>&1 &
header_json
echo '{"ok":true,"action":"rollback flag written; reboot scheduled"}'
"""


MINIHTTPD = """ # mini_httpd configuration file
data_dir=/var/www
port=80
host=0.0.0.0
cgipat=/api/*|/api/backup/*
charset=UTF-8
certfile=/etc/minihttpd.pem
"""


MINIHTTPD_SSL = """ # mini_httpd configuration file
data_dir=/var/www
port=443
host=0.0.0.0
cgipat=/api/*|/api/backup/*
charset=UTF-8
ssl
certfile=/etc/minihttpd.pem
"""


S92HTTPD = r"""#!/bin/sh
kill_process() {
        pid_name=$1
        pid=`ps | grep "$pid_name" | grep -v grep | awk '{print $1}'`
        [ -n "$pid" ] && kill $pid
}
start() {
	export PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts:/usr/local/bin
	export LD_LIBRARY_PATH=/lib:/usr/lib
	platform_file=/scripts/platform_id
	[ -f $platform_file ] && platform_id=`cat $platform_file` || platform_id=00
	if [ "$platform_id" != "425" ]; then
		if [ ! -f /mnt/jffs2/httpd-disabled ]; then
			echo "Starting OpenMitraStar httpd"
			cp -f /etc/minihttpd.conf /mnt/jffs2/minihttpd.conf
			[ ! -f /mnt/jffs2/admin.conf ] && cp -f /etc/admin.conf /mnt/jffs2/admin.conf
			if [ -f /sbin/mini_httpd ] ; then
				/sbin/mini_httpd -r -u root -C /mnt/jffs2/minihttpd.conf
				/sbin/mini_httpd -r -u root -C /etc/minihttpd_ssl.conf
			fi
		else
			echo "httpd is not enabled"
		fi
	fi
}
stop() { echo "Stopping httpd"; kill_process "mini_httpd"; }
restart() { stop; start; }
case "$1" in start) start;; stop) stop;; restart|reload) restart;; *) echo "Usage: $0 {start|stop|restart}"; exit 1;; esac
exit $?
"""


def write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    if mode is not None:
        path.chmod(mode)


def reset() -> None:
    if OVERLAY.exists():
        shutil.rmtree(OVERLAY)
    if SRC_TS.exists():
        shutil.rmtree(SRC_TS)
    (OVERLAY / "var" / "www" / "api" / "backup").mkdir(parents=True)
    SRC_TS.mkdir(parents=True)


def copy_runtime() -> None:
    for rel in [
        Path("etc") / "openmitrastar.conf",
        Path("scripts") / "openmitrastar-apply",
    ]:
        dst = OVERLAY / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PREV_OVERLAY / rel, dst)

    write(OVERLAY / "etc" / "openmitrastar-release",
          "OPENMITRASTAR_VERSION=openmitrastar-0.4-modern-ui-lite\nOPENMITRASTAR_MODE=modern-ui-lite\n")
    write(OVERLAY / "etc" / "openmitrastar-capabilities.json",
          json.dumps({"capabilities": CAPABILITIES}, separators=(",", ":")))
    write(OVERLAY / "etc" / "minihttpd.conf", MINIHTTPD)
    write(OVERLAY / "etc" / "minihttpd_ssl.conf", MINIHTTPD_SSL)
    write(OVERLAY / "etc" / "init.d" / "S92httpd", S92HTTPD, 0o755)


def write_web() -> None:
    www = OVERLAY / "var" / "www"
    write(SRC_TS / "app.ts", APP_TS)
    write(www / "index.html", INDEX_HTML)
    write(www / "firmware.html", FIRMWARE_TEMPLATE)
    write(www / "app.js", APP_JS)
    write(www / "app.css", APP_CSS)
    write(www / "api" / "_lib", API_LIB, 0o755)
    write(www / "api" / "status", API_STATUS, 0o755)
    write(www / "api" / "capabilities", API_CAPS, 0o755)
    write(www / "api" / "services", API_SERVICES, 0o755)
    write(www / "api" / "wifi", API_WIFI, 0o755)
    write(www / "api" / "lan", API_LAN, 0o755)
    write(www / "api" / "backup" / "config", API_BACKUP_CONFIG, 0o755)
    write(www / "api" / "backup" / "firmware", API_BACKUP_FIRMWARE, 0o755)
    write(www / "api" / "backup" / "restore", API_BACKUP_RESTORE, 0o755)
    write(www / "api" / "rollback", API_ROLLBACK, 0o755)

    # Preserve the proven stock firmware-upload backend, but expose it only as
    # /api/flash so the user-facing web no longer navigates to .cgi pages.
    shutil.copy2(SRC_WWW / "firmware.cgi", www / "api" / "flash")
    (www / "api" / "flash").chmod(0o755)


def write_delete_manifest() -> None:
    write(OVERLAY / ".openmitrastar-delete", "var/www\n")


def main() -> int:
    if not SRC_WWW.exists():
        raise FileNotFoundError(SRC_WWW)
    reset()
    copy_runtime()
    write_web()
    write_delete_manifest()
    print(f"generated {OVERLAY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
