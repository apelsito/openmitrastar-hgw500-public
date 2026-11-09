#!/usr/bin/env python3
"""Generate OpenMitraStar 0.4.1 with a proper full-device UX.

This reuses the 0.4 ROM-cleaning/API base but replaces the placeholder-like UI
with an actual router console: dashboard, WiFi, LAN, security, performance,
expert capability map, and backup mode.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools" / "make_openmitrastar_04_overlay.py"

spec = importlib.util.spec_from_file_location("omt04", BASE_PATH)
base = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(base)

base.VERSION = "openmitrastar-0.4.1-modern-ui-full"
base.VERSION_DIR = base.ROOT / "versions" / base.VERSION
base.OVERLAY = base.VERSION_DIR / "overlay"
base.SRC_TS = base.VERSION_DIR / "src"

base.INDEX_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenMitraStar Console</title>
<link rel="stylesheet" href="/app.css">
</head>
<body>
<div class="shell">
<aside>
<div class="brand"><strong>OpenMitraStar</strong><span>HGW-500BNA-QCv2</span></div>
<nav>
<a href="#dashboard">Dashboard</a>
<a href="#wifi">WiFi</a>
<a href="#lan">LAN</a>
<a href="#security">Security</a>
<a href="#performance">Performance</a>
<a href="#backup">Backup mode</a>
<a href="#expert">Expert</a>
</nav>
</aside>
<main>
<header id="dashboard">
<div><h1>Device console</h1><p>Full configuration surface, low-ROM UI, original drivers intact.</p></div>
<button id="refresh" class="primary">Refresh</button>
</header>
<section class="status-grid" id="status-grid"></section>
<section class="layout">
<article class="panel"><h2>Radio state</h2><div id="radio-list" class="kv"></div></article>
<article class="panel"><h2>Services</h2><div id="services-list" class="kv"></div></article>
</section>
<section class="panel" id="wifi">
<div class="section-head"><div><h2>WiFi full control</h2><p>2.4G and 5G controls map to firmware-backed qweconfig/qcsapi capabilities.</p></div><span class="tag warn">Can disconnect clients</span></div>
<div class="columns">
<form class="control-form" data-api="/api/wifi"><h3>2.4 GHz</h3>
<label>Radio<select name="enable.wlan1"><option value="1">Enabled</option><option value="0">Disabled</option></select><i title="Turns 2.4G on or off. Wrong value disconnects clients.">?</i></label>
<label>SSID<input name="ssid.wlan1" placeholder="Network name"><i title="Changing SSID requires reconnecting clients.">?</i></label>
<label>Security<select name="encryption.wlan1"><option value="11i">WPA2 AES</option><option value="WPAand11i">WPA/WPA2 mixed</option><option value="Basic">Open/WEP legacy</option></select><i title="WPA2 AES is safest. Legacy modes are for compatibility only.">?</i></label>
<label>New passphrase<input name="passphrase.wlan1" type="password" autocomplete="new-password" placeholder="Only if changing"><i title="Not prefilled. Writing a new key disconnects clients.">?</i></label>
<label>Channel<select name="channel.wlan1"><option value="0">Auto</option><option>1</option><option>6</option><option>11</option><option>13</option></select><i title="Auto is safest. Fixed channels can help tests but may reduce throughput.">?</i></label>
<label>Bandwidth<select name="bw.wlan1"><option value="20">20 MHz</option><option value="40">40 MHz</option></select><i title="40 MHz can improve peak speed but hurts dense 2.4G areas.">?</i></label>
<label>WMM<select name="wmm.wlan1"><option value="1">Enabled</option><option value="0">Disabled</option></select><i title="Keep WMM enabled for modern WiFi performance.">?</i></label>
<button class="primary">Apply 2.4G</button></form>
<form class="control-form" data-api="/api/wifi"><h3>5 GHz</h3>
<label>Mode<select name="mode.wifi0"><option value="ap">Access point</option><option value="sta">Station</option></select><i title="Wrong mode can remove AP service.">?</i></label>
<label>Channel<select name="channel.wifi0"><option value="0">Auto</option><option>36</option><option>40</option><option>44</option><option>48</option><option>52</option><option>100</option><option>116</option><option>132</option></select><i title="DFS channels may pause or move after radar detection. ES/EU rules apply.">?</i></label>
<label>Bandwidth<select name="bw.wifi0"><option value="20">20 MHz</option><option value="40">40 MHz</option><option value="80">80 MHz</option></select><i title="80 MHz improves peak speed but can be less stable.">?</i></label>
<label>TX power<input name="tx_power.wifi0" placeholder="driver value"><i title="Higher is not always better. ES/EU EIRP limits apply.">?</i></label>
<label>DFS/OCAC<select name="dfs.wifi0"><option value="1">Enabled</option><option value="0">Disabled</option></select><i title="DFS is mandatory for affected 5G channels.">?</i></label>
<label>PMF<select name="pmf.wifi0"><option value="0">Off</option><option value="1">Capable</option><option value="2">Required</option></select><i title="Required can disconnect legacy clients.">?</i></label>
<label>QHOP<select name="qhop.wlan1"><option value="auto">Auto</option><option value="iptv">IPTV</option><option value="data">Data</option></select><i title="Backhaul/repeater profile. Wrong mode can break pairing.">?</i></label>
<button class="primary">Apply 5G</button></form>
</div></section>
<section class="panel" id="lan">
<div class="section-head"><div><h2>LAN, DHCP and bridge</h2><p>Network identity and client allocation. Backup before changing gateway or bridge.</p></div><span class="tag danger">Lockout risk</span></div>
<form class="control-form wide" data-api="/api/lan">
<label>Bridge IP<input name="br0_ip" placeholder="192.168.1.1"><i title="Wrong IP can make the web unreachable.">?</i></label>
<label>Netmask<input name="br0_mask" placeholder="255.255.255.0"><i title="Must match your LAN plan.">?</i></label>
<label>DHCP<select name="dhcp"><option value="1">Enabled</option><option value="0">Disabled</option></select><i title="Disabling DHCP requires static client config.">?</i></label>
<label>Pool start<input name="dhcp_start" placeholder="192.168.1.33"><i title="Start of automatic lease range.">?</i></label>
<label>Pool end<input name="dhcp_end" placeholder="192.168.1.199"><i title="End of automatic lease range.">?</i></label>
<label>VLAN/bridge raw<input name="bridge_raw" placeholder="expert key/value"><i title="Use only if you know the bridge topology.">?</i></label>
<button class="primary">Apply LAN</button></form></section>
<section class="layout" id="security">
<article class="panel"><h2>Security surface</h2><form id="security-form" class="stack" data-api="/api/services">
<label>Telnet<select name="telnet"><option value="off">Off</option><option value="on">On</option></select><i title="Telnet is plaintext. Keep off unless recovering.">?</i></label>
<label>WPS default<select name="wps"><option value="off">Off</option><option value="on">On</option></select><i title="WPS PIN is weak. Use only when pairing.">?</i></label>
<button class="primary">Apply security</button></form></article>
<article class="panel" id="performance"><h2>Performance profile</h2><form id="services-form" class="stack">
<label>Profile<select name="profile"><option value="fast">Fast: minimal provider services</option><option value="balanced">Balanced</option><option value="stock">Stock compatibility</option></select><i title="Fast stops TR-069, harvesters and packet logging where possible.">?</i></label>
<button class="primary">Apply profile</button></form></article>
</section>
<section class="panel" id="backup">
<div class="section-head"><div><h2>Backup mode</h2><p>Firmware flashing, config export and raw partition dump from the new UI.</p></div><span class="tag ok">Recovery tools</span></div>
<div class="actions"><a class="button" href="/api/backup/config">Download config backup</a><a class="button" href="/api/backup/firmware">Download raw firmware dump</a><button id="rollback" class="danger-button">Rollback + reboot</button></div>
<form method="post" enctype="multipart/form-data" action="/api/flash" class="flash"><input type="hidden" name="act" value="1"><input type="file" name="upgradeFileName"><button class="primary">Flash webformat .bin</button></form>
</section>
<section class="panel" id="expert">
<div class="section-head"><div><h2>Expert capability map</h2><p>Search every exposed capability. Raw qweconfig write remains available for full-device freedom.</p></div><input id="search" placeholder="Search: dfs, qhop, dhcp, tx_power, backup..."></div>
<form id="expert-form" class="raw"><input name="key" placeholder="qweconfig key"><input name="value" placeholder="value"><button class="primary">Raw apply</button></form>
<div id="capabilities"></div></section>
<section class="panel"><h2>API output</h2><pre id="output">Ready.</pre></section>
</main>
</div>
<script src="/app.js"></script>
</body>
</html>
"""

base.APP_CSS = """*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#eef2f5;color:#16202a;font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif}.shell{display:grid;grid-template-columns:230px 1fr;min-height:100vh}aside{position:sticky;top:0;height:100vh;background:#101820;color:#d9e2ec;padding:18px;border-right:1px solid #0b1118}.brand{display:grid;gap:3px;margin-bottom:22px}.brand strong{font-size:18px}.brand span{font-size:12px;color:#9fb0c2}nav{display:grid;gap:4px}nav a{color:#d9e2ec;text-decoration:none;padding:9px 10px;border-radius:6px}nav a:hover{background:#1c2a36}main{min-width:0;padding:18px 22px 40px}header{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:14px}h1,h2,h3,p{margin:0}h1{font-size:26px}h2{font-size:17px}h3{font-size:14px;color:#344557}.panel{background:#fff;border:1px solid #d7e0e8;border-radius:8px;padding:14px;margin-bottom:14px;box-shadow:0 1px 2px #ccd6df80}.layout{display:grid;grid-template-columns:1fr 1fr;gap:14px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:14px}.status-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.metric{background:#fff;border:1px solid #d7e0e8;border-radius:8px;padding:12px}.metric b{display:block;color:#657588;font-size:12px}.metric span{display:block;margin-top:4px;font-size:20px}.section-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:12px}.tag{border-radius:999px;padding:4px 8px;font-size:12px;border:1px solid #cad5df;background:#f6f8fa}.tag.warn{background:#fff7df;border-color:#efd17b;color:#765100}.tag.danger{background:#ffe8e8;border-color:#efaaa8;color:#81231f}.tag.ok{background:#e7f8ef;border-color:#9bd3b3;color:#17663b}.control-form{display:grid;grid-template-columns:1fr;gap:9px;border:1px solid #e3e9ef;border-radius:8px;padding:12px;background:#fbfcfd}.control-form.wide{grid-template-columns:repeat(3,1fr)}.stack{display:grid;gap:9px}.raw,.actions,.flash{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}label{display:grid;gap:4px;color:#405163;font-size:12px;position:relative}label i{position:absolute;right:8px;bottom:8px;display:grid;place-items:center;width:18px;height:18px;border-radius:50%;background:#edf6ff;border:1px solid #94bde7;color:#17466f;font-style:normal;font-weight:700;cursor:help}input,select,button,.button{min-height:36px;border:1px solid #b9c5d1;border-radius:6px;background:#fff;color:#16202a;padding:0 10px;font:inherit}label input,label select{padding-right:34px}button,.button{display:inline-flex;align-items:center;justify-content:center;text-decoration:none;cursor:pointer}.primary,.button{background:#1d64d8;border-color:#1d64d8;color:#fff}.danger-button{background:#b42318;border-color:#b42318;color:#fff}.kv{display:grid}.row,.cap{display:flex;justify-content:space-between;gap:12px;border-top:1px solid #edf1f5;padding:9px 0}.row:first-child,.cap:first-child{border-top:0}.cap p{color:#637488;margin-top:2px}.cap span{max-width:42%;color:#637488}.risk{display:inline-grid;place-items:center;width:18px;height:18px;border-radius:50%;background:#fff6d6;border:1px solid #ddb956;color:#765100;font-weight:700;cursor:help}#search{min-width:260px}pre{margin:0;background:#0f1720;color:#d8e9ff;border-radius:8px;padding:12px;overflow:auto;min-height:56px}@media(max-width:880px){.shell{grid-template-columns:1fr}aside{position:relative;height:auto}.layout,.columns,.status-grid,.control-form.wide{grid-template-columns:1fr}header,.section-head{display:grid}#search{min-width:0;width:100%}}"""

base.APP_TS = r"""type Capability = { id: string; group: string; backend: string; risk: string; legal: string };
type Status = { version?: string; uptime?: string; mem_total_kb?: string; mem_free_kb?: string; bridge?: string; services?: Record<string,string>; radio?: Record<string,string> };
const $ = <T extends Element = Element>(s: string): T => document.querySelector(s) as T;
const api = async <T>(path: string, init?: RequestInit): Promise<T> => { const r = await fetch(path, init); const t = await r.text(); try { return JSON.parse(t) as T; } catch { return { ok: r.ok, raw: t } as T; } };
const state: { caps: Capability[]; status: Status } = { caps: [], status: {} };
function esc(v: unknown) { return String(v ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[c] || c)); }
function metric(k: string, v: string) { return `<div class="metric"><b>${esc(k)}</b><span>${esc(v)}</span></div>`; }
function renderStatus() {
 const s = state.status;
 $("#status-grid").innerHTML = [metric("Version", s.version || "unknown"), metric("Uptime", s.uptime || "unknown"), metric("Mem free", `${s.mem_free_kb || "?"} / ${s.mem_total_kb || "?"} kB`), metric("Bridge", s.bridge || "unknown")].join("");
 const svc = s.services || {}; $("#services-list").innerHTML = Object.keys(svc).map(k => `<div class="row"><span>${esc(k)}</span><code>${esc(svc[k])}</code></div>`).join("");
 const radio = s.radio || {}; $("#radio-list").innerHTML = Object.keys(radio).map(k => `<div class="row"><span>${esc(k)}</span><code>${esc(radio[k])}</code></div>`).join("");
}
function renderCapabilities(filter = "") {
 const q = filter.toLowerCase(), grouped: Record<string, Capability[]> = {};
 state.caps.forEach(c => (grouped[c.group] ||= []).push(c));
 $("#capabilities").innerHTML = Object.keys(grouped).map(g => {
  const items = grouped[g].filter(c => !q || `${c.id} ${c.group} ${c.backend} ${c.risk} ${c.legal}`.toLowerCase().includes(q));
  if (!items.length) return "";
  return `<h3>${esc(g)}</h3>${items.map(c => `<div class="cap"><div><strong>${esc(c.id)}</strong> <span class="risk" title="${esc(c.risk + "\n" + c.legal)}">?</span><p>${esc(c.backend)}</p></div><span>${esc(c.legal)}</span></div>`).join("")}`;
 }).join("");
}
async function loadAll() {
 state.status = await api<Status>("/api/status");
 state.caps = (await api<{capabilities: Capability[]}>("/api/capabilities")).capabilities || [];
 renderStatus(); renderCapabilities(($("#search") as HTMLInputElement).value);
}
async function postForm(path: string, form: HTMLFormElement) {
 const body = new URLSearchParams(new FormData(form) as any);
 $("#output").textContent = JSON.stringify(await api(path, { method: "POST", body }), null, 2);
 await loadAll();
}
function bind() {
 $("#refresh").addEventListener("click", () => loadAll());
 $("#search").addEventListener("input", e => renderCapabilities((e.target as HTMLInputElement).value));
 document.querySelectorAll<HTMLFormElement>(".control-form").forEach(f => f.addEventListener("submit", e => { e.preventDefault(); postForm(f.dataset.api || "/api/wifi", f); }));
 $("#services-form").addEventListener("submit", e => { e.preventDefault(); postForm("/api/services", e.target as HTMLFormElement); });
 $("#security-form").addEventListener("submit", e => { e.preventDefault(); postForm("/api/services", e.target as HTMLFormElement); });
 $("#expert-form").addEventListener("submit", e => { e.preventDefault(); postForm("/api/wifi", e.target as HTMLFormElement); });
 $("#rollback").addEventListener("click", async () => { if (!confirm("Activate rollback flag and reboot?")) return; $("#output").textContent = JSON.stringify(await api("/api/rollback", { method: "POST" }), null, 2); });
}
document.addEventListener("DOMContentLoaded", () => { bind(); loadAll(); });
"""

base.APP_JS = r"""const $=s=>document.querySelector(s),api=async(p,i)=>{const r=await fetch(p,i),t=await r.text();try{return JSON.parse(t)}catch{return{ok:r.ok,raw:t}}},state={caps:[],status:{}};function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]||c))}function metric(k,v){return`<div class="metric"><b>${esc(k)}</b><span>${esc(v)}</span></div>`}function renderStatus(){const s=state.status;$("#status-grid").innerHTML=[metric("Version",s.version||"unknown"),metric("Uptime",s.uptime||"unknown"),metric("Mem free",`${s.mem_free_kb||"?"} / ${s.mem_total_kb||"?"} kB`),metric("Bridge",s.bridge||"unknown")].join("");let o=s.services||{};$("#services-list").innerHTML=Object.keys(o).map(k=>`<div class="row"><span>${esc(k)}</span><code>${esc(o[k])}</code></div>`).join("");o=s.radio||{};$("#radio-list").innerHTML=Object.keys(o).map(k=>`<div class="row"><span>${esc(k)}</span><code>${esc(o[k])}</code></div>`).join("")}function renderCapabilities(f=""){const q=f.toLowerCase(),g={};state.caps.forEach(c=>(g[c.group]||(g[c.group]=[])).push(c));$("#capabilities").innerHTML=Object.keys(g).map(n=>{const it=g[n].filter(c=>!q||`${c.id} ${c.group} ${c.backend} ${c.risk} ${c.legal}`.toLowerCase().includes(q));return it.length?`<h3>${esc(n)}</h3>${it.map(c=>`<div class="cap"><div><strong>${esc(c.id)}</strong> <span class="risk" title="${esc(c.risk+"\n"+c.legal)}">?</span><p>${esc(c.backend)}</p></div><span>${esc(c.legal)}</span></div>`).join("")}`:""}).join("")}async function loadAll(){state.status=await api("/api/status");state.caps=(await api("/api/capabilities")).capabilities||[];renderStatus();renderCapabilities($("#search").value)}async function postForm(p,f){const b=new URLSearchParams(new FormData(f));$("#output").textContent=JSON.stringify(await api(p,{method:"POST",body:b}),null,2);await loadAll()}function bind(){$("#refresh").addEventListener("click",loadAll);$("#search").addEventListener("input",e=>renderCapabilities(e.target.value));document.querySelectorAll(".control-form").forEach(f=>f.addEventListener("submit",e=>(e.preventDefault(),postForm(f.dataset.api||"/api/wifi",f))));$("#services-form").addEventListener("submit",e=>(e.preventDefault(),postForm("/api/services",e.target)));$("#security-form").addEventListener("submit",e=>(e.preventDefault(),postForm("/api/services",e.target)));$("#expert-form").addEventListener("submit",e=>(e.preventDefault(),postForm("/api/wifi",e.target)));$("#rollback").addEventListener("click",async()=>{confirm("Activate rollback flag and reboot?")&&($("#output").textContent=JSON.stringify(await api("/api/rollback",{method:"POST"}),null,2))})}document.addEventListener("DOMContentLoaded",()=>{bind();loadAll()});"""

base.API_WIFI = r"""#!/bin/sh
. /var/www/api/_lib
apply_pair() {
  key="$1"; value="$2"
  [ -z "$key" ] && return 0
  case "$key" in key|value) return 0;; *[!A-Za-z0-9._-]*) echo "skip invalid key $key" >>/tmp/openmitrastar-qweconfig.log; return 0;; esac
  case "$key" in
    channel.wifi0) call_qcsapi -u -q set_channel wifi0 "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
    bw.wifi0) call_qcsapi -u -q set_bw wifi0 "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
    mode.wifi0) call_qcsapi -u -q set_mode wifi0 "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
    tx_power.wifi0) call_qcsapi -u -q set_tx_power wifi0 "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
    *) qweconfig set "$key" "$value" >>/tmp/openmitrastar-qweconfig.log 2>&1;;
  esac
}
if [ "$REQUEST_METHOD" = "POST" ]; then
  read_body
  > /tmp/openmitrastar-qweconfig.log
  if printf '%s' "$BODY" | grep -q '^key='; then
    apply_pair "$(kv key)" "$(kv value)"
  else
    printf '%s' "$BODY" | tr '&' '\n' | while IFS='=' read -r k v; do
      k="$(printf '%s' "$k" | sed 's/+/ /g;s/%2E/./g;s/%5F/_/g;s/%2D/-/g')"
      v="$(printf '%s' "$v" | sed 's/+/ /g;s/%2F/\//g;s/%3A/:/g;s/%2E/./g;s/%2D/-/g;s/%5F/_/g;s/%20/ /g')"
      apply_pair "$k" "$v"
    done
  fi
  header_json
  msg="$(cat /tmp/openmitrastar-qweconfig.log 2>/dev/null | json_escape)"
  echo "{\"ok\":true,\"message\":\"$msg\"}"
  exit 0
fi
header_json
ssid="$(qweconfig get ssid.wlan1 2>/dev/null | json_escape)"
mode="$(qweconfig get mode.wlan1 2>/dev/null | json_escape)"
chan="$(call_qcsapi get_channel wifi0 2>/dev/null | json_escape)"
bw="$(call_qcsapi get_bw wifi0 2>/dev/null | json_escape)"
echo "{\"ssid\":\"$ssid\",\"mode\":\"$mode\",\"wifi0_channel\":\"$chan\",\"wifi0_bw\":\"$bw\"}"
"""

base.API_LAN = r"""#!/bin/sh
. /var/www/api/_lib
if [ "$REQUEST_METHOD" = "POST" ]; then
  read_body
  header_json
  echo '{"ok":true,"message":"LAN form received. Persistent LAN writes are staged for 0.4.2 to avoid lockout; use backup before applying raw bridge keys."}'
  exit 0
fi
header_json
ip="$(ifconfig br0 2>/dev/null | awk '/inet addr/{print $2}' | sed 's/addr://')"
mask="$(ifconfig br0 2>/dev/null | awk '/Mask:/{print $4}' | sed 's/Mask://')"
echo "{\"br0_ip\":\"$ip\",\"br0_mask\":\"$mask\"}"
"""

_copy_runtime = base.copy_runtime


def copy_runtime_041() -> None:
    _copy_runtime()
    base.write(
        base.OVERLAY / "etc" / "openmitrastar-release",
        "OPENMITRASTAR_VERSION=openmitrastar-0.4.1-modern-ui-full\n"
        "OPENMITRASTAR_MODE=modern-ui-full\n",
    )


base.copy_runtime = copy_runtime_041


if __name__ == "__main__":
    raise SystemExit(base.main())
