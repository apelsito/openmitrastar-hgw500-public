#!/bin/sh
# OpenMitraStar HGW-500BNA-QCv2 RAM-only L2 bridge stage.
#
# This stage intentionally implements the OEM videobridge/AP role only:
#   eth0 + wlan0 -> br0, management DHCP client on br0.
# It contains no WAN, NAT, DHCP-server, flash or persistent-write path.

set -u

ACK_VALUE=OPENMITRASTAR_RAM_ONLY_L2_BRIDGE
MODE=dry-run
ETH_IF=
WIFI_IF=
BR_IF=
MANAGEMENT=
REQUESTED_IP=
RECOVERY_IP=
RECOVERY_NETMASK=
EXPECTED_KERNEL=
EXPECTED_ETH_MAC=
EXPECTED_WIFI_MAC=
TOOLBOX=
TOOLBOX_SHA256=
KERNEL_CONFIG=
KERNEL_CONFIG_SHA256=
CONTROL_PLANE=
ACK=
MUTATED=0
ETH_WAS_UP=0
WIFI_WAS_UP=0

usage()
{
	cat <<'EOF'
Usage:
  openmitrastar_l2_bridge_stage.sh [--dry-run|--preflight|--apply]
    --ethernet eth0 --wifi wlan0 --bridge br0
    --management dhcp --requested-ip 192.168.1.90
    --recovery-ip 192.168.1.200 --recovery-netmask 255.255.255.0
    --expected-kernel <uname-r>
    --expected-ether-mac <lowercase-mac>
    --expected-wifi-mac <lowercase-mac>
    --toolbox /tmp/openmitrastar-l2-stage/ram_l2_tools
    --toolbox-sha256 <sha256>
    --kernel-config /tmp/openmitrastar-l2-stage/kernel.config
    --kernel-config-sha256 <sha256>
    [--control-plane uart]
    [--ack OPENMITRASTAR_RAM_ONLY_L2_BRIDGE]

Default mode is dry-run.  Apply requires UART control and the exact ACK.
EOF
}

die()
{
	echo "OML2_REFUSED: $*" >&2
	exit 2
}

valid_name()
{
	case "$1" in
		''|*[!A-Za-z0-9_.-]*) return 1 ;;
		*) return 0 ;;
	esac
}

valid_ipv4()
{
	old_ifs=$IFS
	IFS=.
	set -- $1
	IFS=$old_ifs
	[ "$#" -eq 4 ] || return 1
	for octet in "$@"; do
		case "$octet" in ''|*[!0-9]*) return 1 ;; esac
		[ "$octet" -le 255 ] || return 1
	done
}

valid_mac()
{
	old_ifs=$IFS
	IFS=:
	set -- $1
	IFS=$old_ifs
	[ "$#" -eq 6 ] || return 1
	for byte in "$@"; do
		case "$byte" in
			[0-9a-f][0-9a-f]) ;;
			*) return 1 ;;
		esac
	done
}

valid_sha256()
{
	[ "${#1}" -eq 64 ] || return 1
	case "$1" in *[!0-9a-f]*) return 1 ;; *) return 0 ;; esac
}

need_arg()
{
	[ "$#" -ge 2 ] || die "missing value for $1"
}

while [ "$#" -gt 0 ]; do
	case "$1" in
		--dry-run) MODE=dry-run; shift ;;
		--preflight) MODE=preflight; shift ;;
		--apply) MODE=apply; shift ;;
		--ethernet) need_arg "$@"; ETH_IF=$2; shift 2 ;;
		--wifi) need_arg "$@"; WIFI_IF=$2; shift 2 ;;
		--bridge) need_arg "$@"; BR_IF=$2; shift 2 ;;
		--management) need_arg "$@"; MANAGEMENT=$2; shift 2 ;;
		--requested-ip) need_arg "$@"; REQUESTED_IP=$2; shift 2 ;;
		--recovery-ip) need_arg "$@"; RECOVERY_IP=$2; shift 2 ;;
		--recovery-netmask) need_arg "$@"; RECOVERY_NETMASK=$2; shift 2 ;;
		--expected-kernel) need_arg "$@"; EXPECTED_KERNEL=$2; shift 2 ;;
		--expected-ether-mac) need_arg "$@"; EXPECTED_ETH_MAC=$2; shift 2 ;;
		--expected-wifi-mac) need_arg "$@"; EXPECTED_WIFI_MAC=$2; shift 2 ;;
		--toolbox) need_arg "$@"; TOOLBOX=$2; shift 2 ;;
		--toolbox-sha256) need_arg "$@"; TOOLBOX_SHA256=$2; shift 2 ;;
		--kernel-config) need_arg "$@"; KERNEL_CONFIG=$2; shift 2 ;;
		--kernel-config-sha256) need_arg "$@"; KERNEL_CONFIG_SHA256=$2; shift 2 ;;
		--control-plane) need_arg "$@"; CONTROL_PLANE=$2; shift 2 ;;
		--ack) need_arg "$@"; ACK=$2; shift 2 ;;
		-h|--help) usage; exit 0 ;;
		*) die "unknown argument: $1" ;;
	esac
done

for value in "$ETH_IF" "$WIFI_IF" "$BR_IF" "$EXPECTED_KERNEL"; do
	valid_name "$value" || die "missing or invalid concrete interface/kernel value"
done
[ "$ETH_IF" = eth0 ] || die "v1 requires exact Ethernet interface eth0"
[ "$WIFI_IF" = wlan0 ] || die "v1 requires exact Wi-Fi interface wlan0"
[ "$BR_IF" = br0 ] || die "v1 requires exact bridge interface br0"
[ "$MANAGEMENT" = dhcp ] || die "v1 supports management DHCP client only"
valid_ipv4 "$REQUESTED_IP" || die "invalid requested IPv4 address"
valid_ipv4 "$RECOVERY_IP" || die "invalid recovery IPv4 address"
valid_ipv4 "$RECOVERY_NETMASK" || die "invalid recovery netmask"
valid_mac "$EXPECTED_ETH_MAC" || die "expected Ethernet MAC must be lowercase"
valid_mac "$EXPECTED_WIFI_MAC" || die "expected Wi-Fi MAC must be lowercase"
valid_sha256 "$TOOLBOX_SHA256" || die "invalid toolbox SHA-256"
valid_sha256 "$KERNEL_CONFIG_SHA256" || die "invalid kernel-config SHA-256"
case "$TOOLBOX" in /tmp/openmitrastar-l2-stage/*) ;; *) die "toolbox must be below /tmp/openmitrastar-l2-stage" ;; esac
case "$KERNEL_CONFIG" in /tmp/openmitrastar-l2-stage/*) ;; *) die "kernel config must be below /tmp/openmitrastar-l2-stage" ;; esac
case "$TOOLBOX$KERNEL_CONFIG" in *..*) die "parent traversal is forbidden" ;; esac

print_plan()
{
	cat <<EOF
OML2_PLAN schema=openmitrastar.l2-bridge-stage/v1 mode=$MODE
classification=RAM-ONLY-NO-FLASH
role=videobridge-ap-not-hgu
members=$ETH_IF,$WIFI_IF bridge=$BR_IF
management=dhcp requested_ip=$REQUESTED_IP recovery_ip=$RECOVERY_IP
bridge_policy=stp-off,forward-delay-0,ageing-7200
multicast_policy=igmp-snooping-on,multicast-router-off,querier-off
qos_policy=transparent-no-rewrite; runtime packet proof still required
ipv4_forwarding=off nat=absent dhcp_server=absent
flash_supported=false persistent_writes_supported=false
apply_requires=uart+$ACK_VALUE
EOF
}

if [ "$MODE" = dry-run ]; then
	print_plan
	echo OML2_DRY_RUN_PASS=1
	exit 0
fi

BB=$TOOLBOX

bb_has()
{
	"$BB" --list | "$BB" grep -qx "$1"
}

bb_sha256()
{
	"$BB" sha256sum "$1" | {
		read -r digest rest
		echo "$digest"
	}
}

require_kernel_contract()
{
	"$BB" grep -qx 'CONFIG_BRIDGE=y' "$KERNEL_CONFIG" || die "CONFIG_BRIDGE=y missing"
	"$BB" grep -qx 'CONFIG_BRIDGE_IGMP_SNOOPING=y' "$KERNEL_CONFIG" || die "IGMP snooping support missing"
	"$BB" grep -qx '# CONFIG_NETFILTER is not set' "$KERNEL_CONFIG" || die "NETFILTER must be disabled for the first no-NAT stage"
	"$BB" grep -qx '# CONFIG_BRIDGE_VLAN_FILTERING is not set' "$KERNEL_CONFIG" || die "v1 requires transparent bridge VLAN filtering off"
	"$BB" grep -qx 'CONFIG_VLAN_8021Q=y' "$KERNEL_CONFIG" || die "802.1Q frame support missing"
}

preflight()
{
	[ -x "$BB" ] || die "toolbox missing or not executable"
	[ -f "$KERNEL_CONFIG" ] || die "uploaded kernel config missing"
	for applet in brctl ifconfig route udhcpc sha256sum grep ls cat echo chmod sleep id uname mkdir pidof; do
		bb_has "$applet" || die "toolbox applet missing: $applet"
	done
	[ "$(bb_sha256 "$BB")" = "$TOOLBOX_SHA256" ] || die "toolbox hash mismatch"
	[ "$(bb_sha256 "$KERNEL_CONFIG")" = "$KERNEL_CONFIG_SHA256" ] || die "kernel-config hash mismatch"
	[ "$("$BB" id -u)" = 0 ] || die "root is required"
	[ "$("$BB" uname -r)" = "$EXPECTED_KERNEL" ] || die "kernel release mismatch"
	"$BB" grep -q 'OpenMitraStar Linux 5.10 RAM-only rescue' /etc/motd || die "RAM-rescue marker missing"
	"$BB" grep -Eq ' - (rootfs|ramfs|tmpfs) ' /proc/1/mountinfo || die "root filesystem is not RAM-backed"
	set -- /dev/mtd*
	[ "$1" = '/dev/mtd*' ] || die "MTD device node exposed; stage refuses"
	if [ -r /proc/mtd ] && "$BB" grep -q '^mtd[0-9]' /proc/mtd; then
		die "MTD partition exposed; stage refuses"
	fi
	require_kernel_contract
	[ -e "/sys/class/net/$ETH_IF" ] || die "$ETH_IF missing"
	[ -e "/sys/class/net/$WIFI_IF" ] || die "$WIFI_IF missing"
	[ ! -e "/sys/class/net/$BR_IF" ] || die "$BR_IF already exists; v1 will not adopt unknown state"
	[ "$("$BB" cat "/sys/class/net/$ETH_IF/type")" = 1 ] || die "$ETH_IF is not Ethernet type"
	[ "$("$BB" cat "/sys/class/net/$WIFI_IF/type")" = 1 ] || die "$WIFI_IF is not Ethernet type"
	[ "$("$BB" cat "/sys/class/net/$ETH_IF/address")" = "$EXPECTED_ETH_MAC" ] || die "$ETH_IF MAC mismatch"
	[ "$("$BB" cat "/sys/class/net/$WIFI_IF/address")" = "$EXPECTED_WIFI_MAC" ] || die "$WIFI_IF MAC mismatch"
	[ ! -e "/sys/class/net/$ETH_IF/master" ] || die "$ETH_IF already enslaved"
	[ ! -e "/sys/class/net/$WIFI_IF/master" ] || die "$WIFI_IF already enslaved"
	"$BB" ifconfig "$ETH_IF" | "$BB" grep -Eq "inet (addr:)?$RECOVERY_IP([[:space:]]|$)" || die "recovery IP is not currently on $ETH_IF"
	if "$BB" pidof udhcpd >/dev/null 2>&1 || "$BB" pidof dnsmasq >/dev/null 2>&1; then
		die "a DHCP server is running"
	fi
	if "$BB" pidof udhcpc >/dev/null 2>&1; then
		die "an existing DHCP client is running"
	fi
	"$BB" ifconfig "$ETH_IF" | "$BB" grep -q 'UP' && ETH_WAS_UP=1
	"$BB" ifconfig "$WIFI_IF" | "$BB" grep -q 'UP' && WIFI_WAS_UP=1
	print_plan
	echo OML2_PREFLIGHT_PASS=1
}

rollback()
{
	echo OML2_ROLLBACK_BEGIN >&2
	"$BB" ifconfig "$BR_IF" 0.0.0.0 down >/dev/null 2>&1 || :
	"$BB" brctl delif "$BR_IF" "$WIFI_IF" >/dev/null 2>&1 || :
	"$BB" brctl delif "$BR_IF" "$ETH_IF" >/dev/null 2>&1 || :
	"$BB" brctl delbr "$BR_IF" >/dev/null 2>&1 || :
	"$BB" ifconfig "$ETH_IF" "$RECOVERY_IP" netmask "$RECOVERY_NETMASK" up >/dev/null 2>&1 || :
	if [ "$WIFI_WAS_UP" = 1 ]; then
		"$BB" ifconfig "$WIFI_IF" up >/dev/null 2>&1 || :
	else
		"$BB" ifconfig "$WIFI_IF" down >/dev/null 2>&1 || :
	fi
	echo OML2_ROLLBACK_END >&2
}

apply_fail()
{
	message=$1
	if [ "$MUTATED" = 1 ]; then rollback; fi
	die "$message"
}

on_signal()
{
	apply_fail "interrupted; volatile network state rolled back"
}

write_udhcpc_script()
{
	cat > /tmp/openmitrastar-l2-stage/udhcpc.script <<EOF
#!/bin/sh
BB=$TOOLBOX
case "\$1" in
  deconfig)
    "\$BB" ifconfig "\$interface" 0.0.0.0 up
    ;;
  bound|renew)
    "\$BB" ifconfig "\$interface" "\$ip" netmask "\${subnet:-255.255.255.0}" up || exit 1
    "\$BB" route del default dev "\$interface" >/dev/null 2>&1 || :
    for gateway in \${router:-}; do
      "\$BB" route add default gw "\$gateway" dev "\$interface" || exit 1
      break
    done
    {
      echo "event=\$1"
      echo "interface=\$interface"
      echo "ip=\$ip"
      echo "subnet=\${subnet:-}"
      echo "router=\${router:-}"
      echo "dns=\${dns:-}"
    } > /tmp/openmitrastar-l2-stage/lease.env
    ;;
esac
exit 0
EOF
	"$BB" chmod 0700 /tmp/openmitrastar-l2-stage/udhcpc.script || die "cannot chmod DHCP script"
}

if [ "$MODE" = preflight ]; then
	preflight
	exit 0
fi

[ "$MODE" = apply ] || die "invalid mode"
[ "$CONTROL_PLANE" = uart ] || die "apply requires --control-plane uart"
[ "$ACK" = "$ACK_VALUE" ] || die "apply requires exact --ack $ACK_VALUE"
preflight
"$BB" mkdir -p /tmp/openmitrastar-l2-stage || die "cannot create RAM state directory"
write_udhcpc_script

trap on_signal HUP INT TERM
"$BB" brctl addbr "$BR_IF" || apply_fail "cannot create $BR_IF"
MUTATED=1
"$BB" brctl stp "$BR_IF" off || apply_fail "cannot disable STP"
"$BB" brctl setfd "$BR_IF" 0 || apply_fail "cannot set forwarding delay"
"$BB" brctl setageing "$BR_IF" 7200 || apply_fail "cannot set OEM ageing time"
"$BB" ifconfig "$ETH_IF" 0.0.0.0 up || apply_fail "cannot prepare $ETH_IF"
"$BB" ifconfig "$WIFI_IF" 0.0.0.0 up || apply_fail "cannot prepare $WIFI_IF"
"$BB" ifconfig "$BR_IF" hw ether "$EXPECTED_ETH_MAC" || apply_fail "cannot pin bridge MAC"
"$BB" brctl addif "$BR_IF" "$ETH_IF" || apply_fail "cannot bridge $ETH_IF"
"$BB" brctl addif "$BR_IF" "$WIFI_IF" || apply_fail "cannot bridge $WIFI_IF"
"$BB" ifconfig "$BR_IF" up || apply_fail "cannot raise $BR_IF"

for knob in multicast_snooping multicast_router multicast_querier; do
	[ -w "/sys/class/net/$BR_IF/bridge/$knob" ] || apply_fail "missing bridge multicast knob: $knob"
done
echo 1 > "/sys/class/net/$BR_IF/bridge/multicast_snooping" || apply_fail "cannot enable IGMP snooping"
echo 0 > "/sys/class/net/$BR_IF/bridge/multicast_router" || apply_fail "cannot disable multicast-router role"
echo 0 > "/sys/class/net/$BR_IF/bridge/multicast_querier" || apply_fail "cannot disable multicast querier"
if [ -w "/sys/class/net/$BR_IF/bridge/multicast_query_use_ifaddr" ]; then
	echo 0 > "/sys/class/net/$BR_IF/bridge/multicast_query_use_ifaddr" || apply_fail "cannot set multicast query source policy"
fi
[ -w /proc/sys/net/ipv4/ip_forward ] || apply_fail "IPv4 forwarding sysctl missing"
echo 0 > /proc/sys/net/ipv4/ip_forward || apply_fail "cannot disable IPv4 forwarding"
for member in "$ETH_IF" "$WIFI_IF"; do
	if [ -w "/proc/sys/net/ipv6/conf/$member/disable_ipv6" ]; then
		echo 1 > "/proc/sys/net/ipv6/conf/$member/disable_ipv6" || apply_fail "cannot disable member IPv6 L3"
	fi
done

"$BB" udhcpc -f -n -q -t 5 -T 3 -i "$BR_IF" -r "$REQUESTED_IP" \
	-s /tmp/openmitrastar-l2-stage/udhcpc.script || apply_fail "management DHCP lease failed"

[ -e "/sys/class/net/$BR_IF/brif/$ETH_IF" ] || apply_fail "$ETH_IF absent from bridge"
[ -e "/sys/class/net/$BR_IF/brif/$WIFI_IF" ] || apply_fail "$WIFI_IF absent from bridge"
member_count=0
for member_path in /sys/class/net/$BR_IF/brif/*; do
	[ -e "$member_path" ] || continue
	member_count=$((member_count + 1))
done
[ "$member_count" -eq 2 ] || apply_fail "unexpected bridge member count: $member_count"
[ "$("$BB" cat /proc/sys/net/ipv4/ip_forward)" = 0 ] || apply_fail "IPv4 forwarding became enabled"
"$BB" ifconfig "$BR_IF" | "$BB" grep -q 'inet ' || apply_fail "management IPv4 missing on bridge"
"$BB" ifconfig "$ETH_IF" | "$BB" grep -q 'inet ' && apply_fail "member $ETH_IF retained L3 address"
"$BB" ifconfig "$WIFI_IF" | "$BB" grep -q 'inet ' && apply_fail "member $WIFI_IF retained L3 address"

{
	echo classification=RAM-ONLY-NO-FLASH
	echo role=videobridge-ap-not-hgu
	echo bridge=$BR_IF
	echo members=$ETH_IF,$WIFI_IF
	echo management=dhcp
	echo nat=absent
	echo ipv4_forwarding=0
	echo multicast_snooping=1
	echo multicast_router=0
} > /tmp/openmitrastar-l2-stage/status
MUTATED=0
trap - HUP INT TERM
echo OML2_APPLY_PASS=1

