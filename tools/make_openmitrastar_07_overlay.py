#!/usr/bin/env python3
"""Generate the OpenMitraStar 0.7 radio-control overlay from the proven 0.6 base."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "openmitrastar-0.7-radio-control"
RELEASE = "openmitrastar-0.9.1-oem-post-parser"
VDIR = ROOT / "versions" / VERSION
OVERLAY = VDIR / "overlay"
BASE = ROOT / "versions" / "openmitrastar-0.6-ux-first" / "overlay"
SRC = VDIR / "src"

API_LIB = r'''#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/scripts
export PATH
json_escape() { awk 'BEGIN{ORS=""}{gsub(/\\/,"\\\\");gsub(/"/,"\\\"");gsub(/\r/," ");if(NR>1)printf " ";printf "%s",$0}'; }
header_json() { echo "Content-Type: application/json"; echo "Cache-Control: no-store"; echo "X-Content-Type-Options: nosniff"; echo; }
header_bin() { echo "Content-Type: application/octet-stream"; echo "Cache-Control: no-store"; echo "Content-Disposition: attachment; filename=\"$1\""; echo; }
url_decode() { sed 's/+/ /g;s/%20/ /g;s/%2F/\//Ig;s/%3A/:/Ig;s/%2E/./Ig;s/%2D/-/Ig;s/%5F/_/Ig;s/%40/@/Ig;s/%23/#/Ig;s/%25/%/Ig;s/%2B/+/Ig'; }
read_body() { BODY=""; [ -n "$CONTENT_LENGTH" ] && BODY="$(dd bs=1 count="$CONTENT_LENGTH" 2>/dev/null)"; }
qv() { echo "$QUERY_STRING" | tr '&' '\n' | sed -n "s/^$1=//p" | head -1 | url_decode; }
pid_state() { p="$(ps | grep "$1" | grep -v grep | awk 'NR==1{print $1}')"; [ -n "$p" ] && echo "running:$p" || echo stopped; }
is_ipv4() { echo "$1" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; }
safe_text() { echo "$1" | grep -Eq '^[A-Za-z0-9 ._:@#%+=,/-]{1,96}$'; }
qcs() { call_qcsapi "$@" 2>/dev/null | head -1; }
'''

STATUS = r'''#!/bin/sh
. /var/www/api/_lib
header_json
ver="$(sed -n 's/^OPENMITRASTAR_VERSION=//p' /etc/openmitrastar-release 2>/dev/null | json_escape)"
mode="$(sed -n 's/^OPENMITRASTAR_MODE=//p' /etc/openmitrastar-release 2>/dev/null | json_escape)"
mt="$(awk '/MemTotal/{print $2}' /proc/meminfo)"
mu="$(awk '/MemFree/{f=$2}/Buffers/{b=$2}/^Cached:/{c=$2}END{print f+b+c}' /proc/meminfo)"
up="$(cut -d' ' -f1 /proc/uptime | cut -d. -f1)"
set -- $(cat /proc/loadavg 2>/dev/null); l1="$1"; l5="$2"; l15="$3"
br="$(ifconfig br0 2>/dev/null | awk '/inet addr/{print $2}' | sed 's/addr://')"
gw="$(route -n 2>/dev/null | awk '$1=="0.0.0.0"{print $2;exit}')"
[ -n "$gw" ] && connected=true || connected=false
cat <<EOF
{"version":"$ver","mode":"$mode","model":"HGW-500BNA-QCv2","connected":$connected,"uptime_seconds":"$up","mem_total_kb":"$mt","mem_usable_kb":"$mu","load_1m":"$l1","load_5m":"$l5","load_15m":"$l15","bridge":"$br","gateway":"$gw","services":{"SSH":"$(pid_state dropbear)","HTTP":"$(pid_state mini_httpd)","TR-069":"$(pid_state tr69c)","QCSAPI":"$(pid_state qserver)","Registro":"$(pid_state syslogd)"}}
EOF
'''

RADIO = r'''#!/bin/sh
. /var/www/api/_lib
header_json
channel="$(qcs get_channel wifi0)"; bw="$(qcs get_bw wifi0)"; mode="$(qcs get_mode wifi0)"
case "$mode" in *Access*|*access*) mode_value=ap;; *Station*|*station*|*client*) mode_value=sta;; *) mode_value="$mode";; esac
tx="$(qcs get_tx_power wifi0 "$channel")"; clients5="$(qcs get_count_associations wifi0)"
case "$clients5" in ''|*[!0-9]*) clients5=0;; esac
clients24="$(grep -c '^sta:' /proc/wlan0/sta_info 2>/dev/null)"; case "$clients24" in ''|*[!0-9]*) clients24=0;; esac
if grep -q '^qdrv ' /proc/modules; then qdrv=loaded; else qdrv=missing; fi
if grep -q '^rtl8192cd ' /proc/modules; then rtl=loaded; else rtl=missing; fi
if [ -x /sbin/call_qcsapi ]; then qapi=ready; else qapi=missing; fi
dfs="No requerido"; case "$channel" in 52|56|60|64|100|104|108|112) dfs="DFS disponible";; esac
ssid5="$(qcs get_SSID wifi0 | json_escape)"; fw="$(qcs get_firmware_version wifi0 | json_escape)"; region="$(qcs get_regulatory_region wifi0 | json_escape)"
beacon5="$(qcs get_beacon_type wifi0)"; enc5="$(qcs get_IEEE11i_encryption_modes wifi0)"; security5=unknown
case "$beacon5:$enc5" in 11i:*AES*) security5=wpa2_aes;; Basic:*) security5=open;; esac
pass5="$(qcs get_key_passphrase wifi0 0)"; [ ${#pass5} -ge 8 ] && pass5_set=yes || pass5_set=no; unset pass5
scs_raw="$(qcs get_scs_status wifi0)"; case "$scs_raw" in *Enabled*|*\(1\)*) scs=1;; *) scs=0;; esac
qopt() { raw="$(qcs get_option wifi0 "$1")"; case "$raw" in 0|1) echo "$raw";; *[Tt][Rr][Uu][Ee]*|*[Ee]nabled*|*\(1\)*) echo 1;; *[Ff][Aa][Ll][Ss][Ee]*|*[Dd]isabled*|*\(0\)*) echo 0;; *) echo unknown;; esac; }
ssid24="$(qweconfig get ssid.wlan1 2>/dev/null | json_escape)"; ch24="$(qweconfig get channel.wlan1 2>/dev/null | json_escape)"; bw24="$(qweconfig get bandwidth.wlan1 2>/dev/null | json_escape)"
en24="$(qweconfig get enable.wlan1 2>/dev/null | json_escape)"; wps24="$(qweconfig get wpsstate.wlan1 2>/dev/null | json_escape)"; sec24="$(qweconfig get encryption.wlan1 2>/dev/null | json_escape)"
pass24="$(qweconfig get passphrase.wlan1 2>/dev/null)"; [ ${#pass24} -ge 8 ] && pass24_set=yes || pass24_set=no; unset pass24
cat <<EOF
{"band24":{"ssid":"$ssid24","channel":"$ch24","bandwidth":"$bw24","enabled":"$en24","wps":"$wps24","security":"$sec24","passphrase_set":"$pass24_set","clients":"$clients24","band":"$(qweconfig get band.wlan1)","coexist":"$(qweconfig get coexist.wlan1)","beacon":"$(qweconfig get bcnint.wlan1)","dtim":"$(qweconfig get dtimperiod.wlan1)","short_gi":"$(qweconfig get shortgi.wlan1)","frag_threshold":"$(qweconfig get fragthres.wlan1)","rts_threshold":"$(qweconfig get rtsthres.wlan1)","preamble":"$(qweconfig get preamble.wlan1)","wmm":"$(qweconfig get wmm.wlan1)","sideband":"$(qweconfig get extchannel.wlan1)","wmm_apsd":"$(qweconfig get wmm_apsd.wlan1)","max_clients":"$(qweconfig get stanum.wlan1)","protection":"$(qweconfig get disable_protection.wlan1)"},"band5":{"ssid":"$ssid5","mode":"$mode","mode_value":"$mode_value","channel":"$channel","bandwidth":"$bw","tx_power":"$tx","pmf":"$(qcs get_pmf wifi0 | json_escape)","vht":"$(qcs get_vht wifi0 | json_escape)","dtim":"$(qcs get_dtim wifi0 | json_escape)","scs":"$scs","short_gi":"$(qopt short_GI)","wmm":"$(qopt WiFi_MultiMedia)","beamforming":"$(qopt beamforming)","ssid_broadcast":"$(qopt SSID_broadcast)","security":"$security5","passphrase_set":"$pass5_set","wps":"$(qcs get_wps_configured_state wifi0 | json_escape)","region":"$region","firmware":"$fw","dfs_state":"$dfs","clients":"$clients5","enabled":"1"},"drivers":{"qdrv":"$qdrv","rtl8192cd":"$rtl","qcsapi":"$qapi"},"power_table":"tx_power_QSR1000_${region}.txt"}
EOF
'''

CLIENTS = r'''#!/bin/sh
. /var/www/api/_lib
header_json
count="$(qcs get_count_associations wifi0)"; case "$count" in ''|*[!0-9]*) count=0;; esac
[ "$count" -gt 16 ] && count=16
echo -n '{"clients":['
i=0; first=1
while [ "$i" -lt "$count" ]; do
  mac="$(qcs get_associated_device_mac_addr wifi0 "$i" | json_escape)"
  rssi="$(qcs get_rssi_in_dbm_per_association wifi0 "$i" | json_escape)"
  rate="$(qcs get_tx_phy_rate_per_association wifi0 "$i" | json_escape)"
  [ "$first" = 1 ] || echo -n ','; first=0
  echo -n "{\"mac\":\"$mac\",\"rssi\":\"$rssi\",\"tx_rate\":\"$rate\"}"
  i=$((i+1))
done
echo ']}'
'''

TELEMETRY = r'''#!/bin/sh
. /var/www/api/_lib
header_json
net_stats() {
  awk -v dev="$1:" '$1==dev {printf "\"rx_bytes\":\"%s\",\"rx_packets\":\"%s\",\"rx_errors\":\"%s\",\"rx_drops\":\"%s\",\"tx_bytes\":\"%s\",\"tx_packets\":\"%s\",\"tx_errors\":\"%s\",\"tx_drops\":\"%s\"",$2,$3,$4,$5,$10,$11,$12,$13}' /proc/net/dev64 2>/dev/null
}
wireless_stats() {
  awk -v dev="$1:" '$1==dev {gsub(/\./,"",$3);gsub(/\./,"",$4);gsub(/\./,"",$5);printf "\"link\":\"%s\",\"level_dbm\":\"%s\",\"noise_dbm\":\"%s\",\"retries\":\"%s\"",$3,$4,$5,$9}' /proc/net/wireless 2>/dev/null
}
chain() { v="$(qcs get_rssi_by_chain wifi0 "$1")"; case "$v" in ''|*error*|*Error*) echo null;; *) echo "\"$(echo "$v" | json_escape)\"";; esac; }
temp="$(cat /proc/temp_sens 2>/dev/null | head -1 | json_escape)"
cat <<EOF
{"sample_epoch":"$(date +%s)","wifi5":{$(net_stats wifi0),$(wireless_stats wifi0),"chain_rssi":[$(chain 0),$(chain 1),$(chain 2),$(chain 3)]},"wifi24":{$(net_stats wlan0)},"temperature_raw":"$temp","source":"procfs + qcsapi","sampling":"manual"}
EOF
'''

WIFI = r'''#!/bin/sh
. /var/www/api/_lib
fail() { header_json; echo "{\"ok\":false,\"error\":\"$(echo "$1" | json_escape)\"}"; exit 0; }
log_error() { echo "$1" >> "$LOG"; }
validate_pair() {
  key="$1"; value="$2"; [ -z "$value" ] && return 0
  case "$key" in
    band) return 0;;
    enable.wlan1|bandwidth.wlan1) case "$value" in 0|1) return 0;; esac;;
    coexist.wlan1|shortgi.wlan1|preamble.wlan1|wmm.wlan1|extchannel.wlan1|wmm_apsd.wlan1|disable_protection.wlan1) case "$value" in 0|1) return 0;; esac;;
    band.wlan1) case "$value" in 1|2|8|10|11) return 0;; esac;;
    bcnint.wlan1) case "$value" in ''|*[!0-9]*) :;; *) [ "$value" -ge 20 ] && [ "$value" -le 1024 ] && return 0;; esac;;
    dtimperiod.wlan1) case "$value" in ''|*[!0-9]*) :;; *) [ "$value" -ge 1 ] && [ "$value" -le 255 ] && return 0;; esac;;
    fragthres.wlan1) case "$value" in ''|*[!0-9]*) :;; *) [ "$value" -ge 256 ] && [ "$value" -le 2346 ] && return 0;; esac;;
    rtsthres.wlan1) case "$value" in ''|*[!0-9]*) :;; *) [ "$value" -ge 0 ] && [ "$value" -le 2347 ] && return 0;; esac;;
    stanum.wlan1) case "$value" in ''|*[!0-9]*) :;; *) [ "$value" -ge 1 ] && [ "$value" -le 64 ] && return 0;; esac;;
    wpsstate.wlan1) case "$value" in 0|2) return 0;; esac;;
    ssid.wlan1|ssid.wifi0) [ ${#value} -le 32 ] && safe_text "$value" && return 0;;
    passphrase.wlan1|passphrase.wifi0) [ ${#value} -ge 8 ] && [ ${#value} -le 63 ] && safe_text "$value" && return 0;;
    encryption.wlan1) case "$value" in open|wpa2_aes|wpawpa2_aes) return 0;; esac;;
    channel.wlan1) case "$value" in 0|1|2|3|4|5|6|7|8|9|10|11|12|13) return 0;; esac;;
    mode.wifi0) case "$value" in ap|sta) return 0;; esac;;
    channel.wifi0) case "$value" in 0|36|40|44|48|52|56|60|64|100|104|108|112) return 0;; esac;;
    bw.wifi0) case "$value" in 20|40|80) return 0;; esac;;
    pmf.wifi0) case "$value" in 0|1|2) return 0;; esac;;
    vht.wifi0|scs.wifi0) case "$value" in 0|1) return 0;; esac;;
    short_gi.wifi0|wmm.wifi0|beamforming.wifi0|ssid_broadcast.wifi0) case "$value" in 0|1) return 0;; esac;;
    security.wifi0) case "$value" in wpa2_aes|open) return 0;; esac;;
    dtim.wifi0) case "$value" in 1|2|3) return 0;; esac;;
    tx_power.wifi0) case "$value" in ''|*[!0-9]*) :;; *) [ "$value" -ge 1 ] && [ "$value" -le 19 ] && return 0;; esac;;
  esac
  log_error "$key: valor no permitido"
  return 1
}
qwe_set() {
  out="$(qweconfig set "$1" "$2" 2>&1)"; rc=$?
  [ -n "$out" ] && echo "$out" >> "$LOG"
  [ "$rc" = 0 ] || { log_error "$1: qweconfig rc=$rc"; return 1; }
  changed24=1
  return 0
}
qcs_set() {
  out="$(call_qcsapi -u -q "$@" 2>&1)"; rc=$?
  [ -n "$out" ] && echo "$out" >> "$LOG"
  if [ "$rc" != 0 ] || echo "$out" | grep -Eqi 'QCS API error|invalid|error:'; then
    log_error "$1: QCSAPI rc=$rc"
    return 1
  fi
  return 0
}
apply_pair() {
  key="$1"; value="$2"; [ -z "$value" ] && return 0
  case "$key" in
    band) return 0;;
    enable.wlan1|ssid.wlan1|passphrase.wlan1|encryption.wlan1|channel.wlan1|bandwidth.wlan1|wpsstate.wlan1|band.wlan1|coexist.wlan1|bcnint.wlan1|dtimperiod.wlan1|shortgi.wlan1|fragthres.wlan1|rtsthres.wlan1|preamble.wlan1|wmm.wlan1|extchannel.wlan1|wmm_apsd.wlan1|stanum.wlan1|disable_protection.wlan1) qwe_set "$key" "$value";;
    ssid.wifi0) qcs_set set_SSID wifi0 "$value";;
    mode.wifi0) qcs_set set_mode wifi0 "$value";;
    channel.wifi0) qcs_set set_channel wifi0 "$value";;
    bw.wifi0) qcs_set set_bw wifi0 "$value";;
    pmf.wifi0) qcs_set set_pmf wifi0 "$value";;
    vht.wifi0) qcs_set set_vht wifi0 "$value";;
    passphrase.wifi0) qcs_set set_key_passphrase wifi0 0 "$value";;
    security.wifi0) case "$value" in
      wpa2_aes) qcs_set set_beacon_type wifi0 11i && qcs_set set_IEEE11i_authentication_mode wifi0 PSKAuthentication && qcs_set set_IEEE11i_encryption_modes wifi0 AESEncryption;;
      open) qcs_set set_beacon_type wifi0 Basic && qcs_set set_basic_encryption_modes wifi0 None;;
    esac;;
    dtim.wifi0) qcs_set set_dtim wifi0 "$value";;
    scs.wifi0) qcs_set scs_enable wifi0 "$value";;
    short_gi.wifi0) qcs_set set_option wifi0 short_GI "$value";;
    wmm.wifi0) qcs_set set_option wifi0 WiFi_MultiMedia "$value";;
    beamforming.wifi0) qcs_set set_option wifi0 beamforming "$value";;
    ssid_broadcast.wifi0) qcs_set set_option wifi0 SSID_broadcast "$value";;
    tx_power.wifi0) ch="$(qcs get_channel wifi0)"; qcs_set set_tx_power wifi0 "$ch" "$value";;
  esac
}
[ "$REQUEST_METHOD" = POST ] || fail 'POST required'
read_body
LOG=/tmp/openmitrastar-radio-change.log; PAIRS=/tmp/openmitrastar-radio-pairs.$$
: > "$LOG"; echo "$BODY" | awk 'BEGIN { RS="&" } { print }' > "$PAIRS"
invalid=0
while IFS= read -r pair; do
  k="$(echo "${pair%%=*}" | url_decode)"; v="$(echo "${pair#*=}" | url_decode)"
  validate_pair "$k" "$v" || invalid=1
done < "$PAIRS"
if [ "$invalid" = 1 ]; then
  rm -f "$PAIRS"; header_json; msg="$(cat "$LOG" | json_escape)"
  echo "{\"ok\":false,\"error\":\"Validación rechazada: $msg\"}"; exit 0
fi
changed24=0; failed=0
while IFS= read -r pair; do
  k="$(echo "${pair%%=*}" | url_decode)"; v="$(echo "${pair#*=}" | url_decode)"
  apply_pair "$k" "$v" || failed=1
done < "$PAIRS"
rm -f "$PAIRS"
if [ "$changed24" = 1 ]; then
  out="$(qweaction wlan1 commit 2>&1)"; rc=$?; [ -n "$out" ] && echo "$out" >> "$LOG"
  [ "$rc" = 0 ] || { log_error "wlan1 commit: rc=$rc"; failed=1; }
fi
header_json; msg="$(cat "$LOG" | json_escape)"
if [ "$failed" = 1 ]; then
  echo "{\"ok\":false,\"error\":\"Algún cambio no se aplicó: $msg\"}"
else
  echo "{\"ok\":true,\"message\":\"Cambios aplicados y verificados por el backend\",\"backend\":\"$msg\"}"
fi
'''

CAPS = [
 {"id":"wifi.24.enable","label":"Radio 2.4 GHz","group":"WiFi 2.4 GHz","level":"disconnect","description":"Enciende o apaga rtl8192cd.","backend":"qweconfig enable.wlan1","values":"0, 1","legal":"No modifica potencia."},
 {"id":"wifi.24.ssid","label":"SSID 2.4 GHz","group":"WiFi 2.4 GHz","level":"disconnect","description":"Nombre anunciado por la red.","backend":"qweconfig ssid.wlan1","values":"1-32 caracteres","legal":"Sin impacto RF."},
 {"id":"wifi.24.security","label":"Seguridad 2.4 GHz","group":"WiFi 2.4 GHz","level":"disconnect","description":"Cifrado y clave del AP; la clave actual nunca se devuelve al navegador.","backend":"qweconfig encryption.wlan1 + passphrase.wlan1","values":"wpa2_aes, wpawpa2_aes, open","legal":"WPA2 AES recomendado."},
 {"id":"wifi.24.channel","label":"Canal 2.4 GHz","group":"WiFi 2.4 GHz","level":"disconnect","description":"Canal operativo del radio Realtek.","backend":"qweconfig channel.wlan1","values":"Auto, 1-13","legal":"Canales ES/EU."},
 {"id":"wifi.24.bandwidth","label":"Ancho 2.4 GHz","group":"WiFi 2.4 GHz","level":"disconnect","description":"Equilibrio entre pico e interferencia.","backend":"qweconfig bandwidth.wlan1","values":"0 = 20 MHz, 1 = 40 MHz","legal":"Coexistencia 2.4 GHz."},
 {"id":"wifi.24.wps","label":"WPS 2.4 GHz","group":"WiFi 2.4 GHz","level":"disconnect","description":"Estado de emparejamiento WPS del radio Realtek.","backend":"qweconfig wpsstate.wlan1","values":"0 apagado, 2 configurado","legal":"Mantener apagado fuera del emparejamiento."},
 {"id":"wifi.24.band","label":"Estándares 2.4 GHz","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Selecciona las familias 802.11 admitidas por el PHY Realtek.","backend":"qweconfig band.wlan1 + qweaction commit","values":"b, g, n, g/n, b/g/n","legal":"WMM debe permanecer activo para alto rendimiento 802.11n."},
 {"id":"wifi.24.coexist","label":"Coexistencia 20/40","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Permite reducir ancho ante redes vecinas incompatibles.","backend":"qweconfig coexist.wlan1 + qweaction commit","values":"0, 1","legal":"Recomendado en espectro compartido."},
 {"id":"wifi.24.beacon","label":"Intervalo beacon","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Periodo de las balizas del punto de acceso.","backend":"qweconfig bcnint.wlan1 + qweaction commit","values":"20-1024 ms","legal":"100 ms es el valor operativo habitual."},
 {"id":"wifi.24.dtim","label":"DTIM 2.4 GHz","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Frecuencia de entrega multicast/broadcast a clientes dormidos.","backend":"qweconfig dtimperiod.wlan1 + qweaction commit","values":"1-255 balizas","legal":"Menor valor implica menor latencia y más consumo."},
 {"id":"wifi.24.shortgi","label":"Guard interval 2.4 GHz","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Alterna intervalo de guarda corto o largo.","backend":"qweconfig shortgi.wlan1 + qweaction commit","values":"0 largo, 1 corto","legal":"El corto mejora pico; el largo tolera multitrayecto."},
 {"id":"wifi.24.fragment","label":"Umbral de fragmentación","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Tamaño a partir del cual se fragmentan tramas.","backend":"qweconfig fragthres.wlan1 + qweaction commit","values":"256-2346 bytes","legal":"2346 evita fragmentación práctica."},
 {"id":"wifi.24.rts","label":"Umbral RTS","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Activa RTS/CTS por encima del tamaño indicado.","backend":"qweconfig rtsthres.wlan1 + qweaction commit","values":"0-2347 bytes","legal":"2347 equivale a desactivado."},
 {"id":"wifi.24.preamble","label":"Preámbulo 2.4 GHz","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Selecciona preámbulo largo o corto.","backend":"qweconfig preamble.wlan1 + qweaction commit","values":"0 largo, 1 corto","legal":"Largo conserva clientes antiguos."},
 {"id":"wifi.24.wmm","label":"WMM 2.4 GHz","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"QoS por categorías de acceso WiFi.","backend":"qweconfig wmm.wlan1 + qweaction commit","values":"0, 1","legal":"Necesario para velocidades 802.11n."},
 {"id":"wifi.24.sideband","label":"Canal secundario 2.4 GHz","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Posición del canal secundario cuando se usan 40 MHz.","backend":"qweconfig extchannel.wlan1 + qweaction commit","values":"0 superior, 1 inferior","legal":"Solo aplica con ancho 40 MHz."},
 {"id":"wifi.24.apsd","label":"WMM APSD 2.4 GHz","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Entrega programada para ahorro de energía.","backend":"qweconfig wmm_apsd.wlan1 + qweaction commit","values":"0, 1","legal":"Puede afectar clientes antiguos."},
 {"id":"wifi.24.clients","label":"Límite de clientes 2.4 GHz","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Máximo global de asociaciones Realtek.","backend":"qweconfig stanum.wlan1 + qweaction commit","values":"1-64","legal":"Todos comparten el mismo airtime."},
 {"id":"wifi.24.protection","label":"Protección 802.11n","group":"WiFi 2.4 GHz avanzado","level":"disconnect","description":"Protección frente a redes y clientes B/G.","backend":"qweconfig disable_protection.wlan1 + qweaction commit","values":"0 automática, 1 desactivada","legal":"Automática recomendada."},
 {"id":"wifi.5.mode","label":"Modo 5 GHz","group":"WiFi 5 GHz","level":"lockout","description":"AP o cliente/repetidor.","backend":"qcsapi set_mode wifi0","values":"ap, sta","legal":"Puede mover el backhaul."},
 {"id":"wifi.5.channel","label":"Canal 5 GHz","group":"WiFi 5 GHz","level":"disconnect","description":"Canal VHT; los DFS requieren escucha de radar.","backend":"qcsapi set_channel wifi0","values":"Auto, 36-64, 100-112 permitidos","legal":"Región ES y DFS obligatorios."},
 {"id":"wifi.5.bandwidth","label":"Ancho 5 GHz","group":"WiFi 5 GHz","level":"disconnect","description":"Ancho del canal 802.11ac.","backend":"qcsapi set_bw wifi0","values":"20, 40, 80 MHz","legal":"Limitado por canal y región."},
 {"id":"wifi.5.tx_power","label":"Potencia 5 GHz","group":"WiFi 5 GHz","level":"disconnect","description":"Potencia por canal, no ganancia de antena.","backend":"qcsapi set_tx_power wifi0 <canal> <dBm>","values":"1-19 dBm","legal":"Límite conservador basado en tabla QSR1000 ES."},
 {"id":"wifi.5.pmf","label":"PMF 5 GHz","group":"WiFi 5 GHz","level":"disconnect","description":"Protección de tramas de gestión.","backend":"qcsapi set_pmf wifi0","values":"0, 1, 2","legal":"Sin impacto RF."},
 {"id":"wifi.5.vht","label":"VHT / 802.11ac","group":"WiFi 5 GHz","level":"disconnect","description":"Activa capacidades 802.11ac.","backend":"qcsapi set_vht wifi0","values":"0, 1","legal":"Hardware 4x4 ac; no añade WiFi 6."},
 {"id":"wifi.5.security","label":"Seguridad 5 GHz","group":"WiFi 5 GHz","level":"disconnect","description":"Beacon, autenticación, cifrado y clave; la clave actual nunca se devuelve al navegador.","backend":"qcsapi set_beacon_type/set_IEEE11i_*/set_key_passphrase","values":"WPA2 AES, abierta","legal":"WPA2 AES recomendado."},
 {"id":"wifi.5.dtim","label":"DTIM 5 GHz","group":"WiFi 5 GHz","level":"disconnect","description":"Frecuencia de entrega de multicast/broadcast a clientes en ahorro de energía.","backend":"qcsapi set_dtim wifi0","values":"1, 2, 3 balizas","legal":"2 conserva el equilibrio OEM."},
 {"id":"wifi.5.scs","label":"SCS 5 GHz","group":"WiFi 5 GHz","level":"disconnect","description":"Selección inteligente de canal Quantenna basada en interferencia.","backend":"qcsapi scs_enable wifi0","values":"0, 1","legal":"DFS y región siguen siendo obligatorios."},
 {"id":"wifi.5.shortgi","label":"Guard interval 5 GHz","group":"WiFi 5 GHz avanzado","level":"disconnect","description":"Intervalo de guarda del PHY Quantenna.","backend":"qcsapi set_option wifi0 short_GI","values":"0 largo, 1 corto","legal":"El corto mejora pico; el largo tolera multitrayecto."},
 {"id":"wifi.5.wmm","label":"WMM 5 GHz","group":"WiFi 5 GHz avanzado","level":"disconnect","description":"QoS multimedia del radio Quantenna.","backend":"qcsapi set_option wifi0 WiFi_MultiMedia","values":"0, 1","legal":"Requerido para alto rendimiento 802.11ac."},
 {"id":"wifi.5.beamforming","label":"Beamforming 5 GHz","group":"WiFi 5 GHz avanzado","level":"disconnect","description":"Transmisión dirigida hacia estaciones compatibles.","backend":"qcsapi set_option wifi0 beamforming","values":"0, 1","legal":"Capacidad confirmada en libqcsapi OEM."},
 {"id":"wifi.5.broadcast","label":"Visibilidad SSID 5 GHz","group":"WiFi 5 GHz avanzado","level":"disconnect","description":"Anuncia u oculta el SSID primario.","backend":"qcsapi set_option wifi0 SSID_broadcast","values":"0 oculta, 1 visible","legal":"Ocultar no añade seguridad criptográfica."},
 {"id":"radio.driver.qdrv","label":"Driver Quantenna qdrv","group":"Drivers","level":"readonly","description":"Driver propietario 5 GHz ligado a firmware y calibración.","backend":"qdrv.ko + qtn_driver.qtn_ruby.0.bin","values":"Solo lectura en 0.7","legal":"No reemplazar en firmware live."},
 {"id":"radio.driver.rtl","label":"Driver Realtek rtl8192cd","group":"Drivers","level":"readonly","description":"Driver vendor 2.4 GHz 802.11n.","backend":"rtl8192cd.ko","values":"Solo lectura en 0.7","legal":"No exponer MIB crudo."},
 {"id":"telemetry.signal","label":"Señal por cadena","group":"Telemetría","level":"readonly","description":"RSSI agregado y por las cuatro cadenas Quantenna, ruido y SNR estimada.","backend":"/proc/net/wireless + qcsapi get_rssi_by_chain","values":"dBm, lectura manual","legal":"Solo lectura; no ejecuta escaneo RF."},
 {"id":"telemetry.throughput","label":"Caudal por banda","group":"Telemetría","level":"readonly","description":"Calcula bits por segundo entre dos lecturas de contadores de interfaz.","backend":"/proc/net/dev64 + delta en navegador","values":"bps, Kbps, Mbps","legal":"No genera tráfico ni guarda históricos."},
 {"id":"telemetry.datapath","label":"Salud RX/TX","group":"Telemetría","level":"readonly","description":"Errores, drops y reintentos observados en el datapath del kernel.","backend":"/proc/net/dev64 + /proc/net/wireless","values":"Contadores acumulados","legal":"Una subida requiere correlación con carga y tiempo de actividad."},
 {"id":"recovery.live","label":"Firmware live","group":"Recuperación","level":"brick","description":"Partición de firmware activa.","backend":"chkimage + flash_image_update live","values":"Imagen webformat validada","legal":"Safety bloqueada en UI."},
]

def write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    if mode is not None:
        path.chmod(mode)

def main() -> int:
    if OVERLAY.exists():
        shutil.rmtree(OVERLAY)
    shutil.copytree(BASE, OVERLAY)
    # mini_httpd only executes paths matched by cgipat. The inherited pattern
    # covered /api/status but not nested recovery handlers such as
    # /api/backup/config, causing their shell source to be served as text.
    for config_name in ("minihttpd.conf", "minihttpd_ssl.conf"):
        config_path = OVERLAY / "etc" / config_name
        config_text = config_path.read_text(encoding="utf-8")
        config_text = config_text.replace(
            "cgipat=api/*|**.cgi|**.php",
            "cgipat=api/*|api/*/*|**.cgi|**.php",
        )
        write(config_path, config_text)
    for name in ("index.html", "app.css", "visibility.css", "telemetry.css", "app.js"):
        shutil.copy2(SRC / name, OVERLAY / "var" / "www" / name)
    api = OVERLAY / "var" / "www" / "api"
    for name, body in {"_lib":API_LIB,"status":STATUS,"radio":RADIO,"clients":CLIENTS,"telemetry":TELEMETRY,"wifi":WIFI}.items():
        write(api / name, body, 0o755)
    write(OVERLAY / "etc" / "openmitrastar-capabilities.json", json.dumps({"capabilities": CAPS}, ensure_ascii=False, separators=(",", ":")) + "\n")
    write(OVERLAY / "etc" / "openmitrastar-release", f"OPENMITRASTAR_VERSION={RELEASE}\nOPENMITRASTAR_MODE=radio-control-light-oem-compatible\n")
    print(f"generated {OVERLAY}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
