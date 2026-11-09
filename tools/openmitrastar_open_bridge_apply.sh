#!/bin/sh

set -eu

ACK_VALUE=OPENMITRASTAR_RAM_ONLY_OPEN_BRIDGE
ACK=${1:-}
BB=/tmp/openmitrastar-ap/bundle/bin/busybox
LOG=/tmp/openmitrastar-open-bridge.log

[ "$ACK" = "$ACK_VALUE" ] || exit 2
[ -x "$BB" ] || exit 3
[ ! -e /sys/class/net/br0 ] || exit 4
[ -e /sys/class/net/eth0 ] && [ -e /sys/class/net/wlan0 ] || exit 5

eth_mac=$($BB cat /sys/class/net/eth0/address)
{
    echo 'OMOPEN_BRIDGE_BEGIN=1'
    echo "eth_mac=$eth_mac"
} >"$LOG"

$BB ifconfig wlan0 0.0.0.0 up
$BB brctl addbr br0
$BB brctl stp br0 off
$BB brctl setfd br0 0
$BB brctl setageing br0 7200
$BB ifconfig eth0 0.0.0.0 up
$BB ifconfig br0 hw ether "$eth_mac"
$BB brctl addif br0 eth0
$BB brctl addif br0 wlan0
$BB ifconfig br0 192.168.1.200 netmask 255.255.255.0 up
route del default 2>/dev/null || true
route add default gw 192.168.1.1 dev br0 2>/dev/null || true

{
    $BB brctl show
    $BB ifconfig br0
    echo 'OMOPEN_BRIDGE_PASS=1 management=192.168.1.200 members=eth0,wlan0'
} >>"$LOG" 2>&1
