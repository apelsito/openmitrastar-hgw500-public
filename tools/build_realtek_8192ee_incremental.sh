#!/bin/sh
set -eu

# Incremental, offline-only Realtek module builder for the already proven
# OpenMitraStar RAM kernel.  This helper never contacts the router, opens a
# socket, starts TFTP, touches UART, or creates a flash image.

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
src=${TOPAZ_KERNEL_SRC:-/home/user/mitrastar-linux-5.10.260}
out_root=${TOPAZ_BUILD_ROOT:-/home/user/openmitrastar-build}
out=${TOPAZ_RADIOHW_BUILD:-$out_root/radiohw-probe}
jobs=${TOPAZ_JOBS:-12}
skip_build=${REALTEK_SKIP_BUILD:-0}
bundle=${REALTEK_BUNDLE_DIR:-$root/outputs/kernel-port/realtek-loop/current-RAM-ONLY-NO-FLASH}
tc="$root/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
firmware="$root/work/linux510-radio-port/realtek/firmware/rtlwifi/rtl8192eefw.bin"
regdb="$root/outputs/kernel-port/realtek-ap-bundle/firmware/regulatory.db"
base_image="$root/work/tftp/omvl/linux510-radiohw-pci-probe-webformat.bin"
base_vmlinux="$root/outputs/kernel-port/radiohw-probe/linux-5.10.260-openmitrastar-radiohw-pci-probe-RAM-ONLY.vmlinux"
ramtools="$root/outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc"
ramtools_sha=8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6
firmware_sha=c6e5beeeb2a716ce417a9ede5974d0876b18ebf0368c195da8a181f6ba6d9b4b
regdb_sha=e9051546c38849b54e6b6a90ca32151c9e29f23edb7698f2c4a437fc353b3393

canonical_path()
{
	python3 - "$1" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve())
PY
}

root=$(canonical_path "$root")
bundle=$(canonical_path "$bundle")
allowed_bundle_root=$(canonical_path "$root/outputs/kernel-port/realtek-loop")

case "$jobs" in ''|*[!0-9]*) echo "TOPAZ_JOBS must be a positive integer" >&2; exit 2 ;; esac
[ "$jobs" -gt 0 ] || { echo "TOPAZ_JOBS must be greater than zero" >&2; exit 2; }
case "$skip_build" in 0|1) ;; *) echo "REALTEK_SKIP_BUILD must be 0 or 1" >&2; exit 2 ;; esac
case "$bundle" in
	"$allowed_bundle_root"/*RAM-ONLY*) ;;
	*) echo "refusing bundle outside RAM-only output root: $bundle" >&2; exit 3 ;;
esac

for required in \
	"$src/Makefile" "$out/.config" "$out/include/config/kernel.release" \
	"${tc}gcc" "${tc}readelf" "${tc}objdump" \
	"$firmware" "$regdb" "$base_image" "$base_vmlinux" "$ramtools"; do
	test -e "$required" || { echo "missing input: $required" >&2; exit 4; }
done

for required in \
	'CONFIG_MODULES=y' \
	'CONFIG_MODULE_UNLOAD=y' \
	'CONFIG_CRYPTO_CTR=m' \
	'CONFIG_CRYPTO_CCM=m' \
	'CONFIG_CRYPTO_CMAC=m' \
	'CONFIG_CFG80211=m' \
	'CONFIG_MAC80211=m' \
	'CONFIG_RTLWIFI=m' \
	'CONFIG_RTLWIFI_PCI=m' \
	'CONFIG_RTLBTCOEXIST=m' \
	'CONFIG_RTL8192EE=m'; do
	grep -qx "$required" "$out/.config" || {
		echo "missing Kconfig contract: $required" >&2
		exit 5
	}
done

echo "$firmware_sha  $firmware" | sha256sum -c - >/dev/null
echo "$regdb_sha  $regdb" | sha256sum -c - >/dev/null

if [ "$skip_build" = 0 ]; then
	# Keep the build cache. Applying the overlay is deterministic and lets W2
	# change only the driver source while Kbuild recompiles affected objects.
	sh "$root/tools/apply_topaz_linux_510_overlay.sh" "$src"
	make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
	make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" \
		-j"$jobs" modules
fi

release=$(cat "$out/include/config/kernel.release")
case "$release" in
	5.10.260-openmitrastar-radiohw) ;;
	*) echo "unexpected target kernel release: $release" >&2; exit 6 ;;
esac

module_cfg80211="$out/net/wireless/cfg80211.ko"
module_ctr="$out/crypto/ctr.ko"
module_ccm="$out/crypto/ccm.ko"
module_cmac="$out/crypto/cmac.ko"
module_libarc4="$out/lib/crypto/libarc4.ko"
module_mac80211="$out/net/mac80211/mac80211.ko"
module_rtlwifi="$out/drivers/net/wireless/realtek/rtlwifi/rtlwifi.ko"
module_btcoexist="$out/drivers/net/wireless/realtek/rtlwifi/btcoexist/btcoexist.ko"
module_rtl_pci="$out/drivers/net/wireless/realtek/rtlwifi/rtl_pci.ko"
module_rtl8192ee="$out/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/rtl8192ee.ko"

for module in "$module_ctr" "$module_ccm" "$module_cmac" \
	"$module_cfg80211" "$module_libarc4" "$module_mac80211" \
	"$module_rtlwifi" "$module_btcoexist" "$module_rtl_pci" \
	"$module_rtl8192ee"; do
	test -s "$module" || { echo "missing built module: $module" >&2; exit 7; }
	"${tc}readelf" -h "$module" | grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
	/usr/sbin/modinfo -F vermagic "$module" | grep -Fq "$release"
done

/usr/sbin/modinfo -F alias "$module_rtl8192ee" | \
	grep -Fqi 'pci:v000010ECd0000818B'
test "$(/usr/sbin/modinfo -F firmware "$module_rtl8192ee")" = \
	'rtlwifi/rtl8192eefw.bin'

# Architecture gate for the current blocker: no raw u16 dereference may read
# the byte-oriented efuse shadow map.  The destination MAC is copied bytewise.
efuse="$src/drivers/net/wireless/realtek/rtlwifi/efuse.c"
for needle in \
	'eeprom_id = get_unaligned_le16(&hwinfo[0]);' \
	'rtlefuse->eeprom_vid = get_unaligned_le16(&hwinfo[params[1]]);' \
	'rtlefuse->eeprom_did = get_unaligned_le16(&hwinfo[params[2]]);' \
	'rtlefuse->eeprom_svid = get_unaligned_le16(&hwinfo[params[3]]);' \
	'rtlefuse->eeprom_smid = get_unaligned_le16(&hwinfo[params[4]]);' \
	'memcpy(rtlefuse->dev_addr, &hwinfo[params[5]], ETH_ALEN);' \
	'rtlefuse->eeprom_version = get_unaligned_le16(&hwinfo[params[7]]);'; do
	grep -Fq "$needle" "$efuse" || {
		echo "unaligned-access source gate missing: $needle" >&2
		exit 8
	}
done
if sed -n '/^int rtl_get_hwinfo(/,/^}/p' "$efuse" | \
	grep -Eq '\*\(u16 \*\).*hwinfo|\*\(\(u16 \*\).*hwinfo'; then
	echo "raw u16 hwinfo dereference remains in rtl_get_hwinfo" >&2
	exit 8
fi
wifi_h="$src/drivers/net/wireless/realtek/rtlwifi/wifi.h"
grep -Fq 'u8 dev_addr[ETH_ALEN] __aligned(2);' "$wifi_h" || {
	echo "rtl_efuse.dev_addr is not guaranteed u16-aligned" >&2
	exit 8
}

warm_fw="$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/fw.c"
for needle in \
	'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' \
	'if (err && mitrastar_retry && checksum_timeout)' \
	'rtl_write_dword(rtlpriv, REG_MCUFWDL, 0);' \
	'OMRTL92 stage=fw-warm-retry reason=checksum-timeout attempt=1'; do
	grep -Fq "$needle" "$warm_fw" || {
		echo "warm firmware retry source gate missing: $needle" >&2
		exit 8
	}
done
strings "$module_rtl8192ee" | grep -Fq \
	'OMRTL92 stage=fw-warm-retry reason=checksum-timeout attempt=1'

core="$src/drivers/net/wireless/realtek/rtlwifi/core.c"
for needle in \
	'hgw500_tx_ampdu_disable' \
	'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' \
	'rtlpriv->rtlhal.hw_type == HARDWARE_TYPE_RTL8192EE' \
	'vif->type == NL80211_IFTYPE_AP' \
	'OMRTLAMPDU stage=tx-start-rejected'; do
	grep -Fq "$needle" "$core" || {
		echo "TX A-MPDU lab source gate missing: $needle" >&2
		exit 8
	}
done
strings "$module_rtlwifi" | grep -Fq \
	'OMRTLAMPDU stage=tx-start-rejected tid=%u aid=%u param=1'
/usr/sbin/modinfo -p "$module_rtlwifi" | \
	grep -Fq 'hgw500_tx_ampdu_disable:Disable TX A-MPDU only on MitraStar HGW-500BNA-QCv2 lab runs'

for source_gate in \
	"$src/drivers/net/wireless/realtek/rtlwifi/core.c:rtl_hgw500_honest_tx_ack" \
	"$src/drivers/net/wireless/realtek/rtlwifi/base.c:OMRTLACK stage=policy-active" \
	"$src/drivers/net/wireless/realtek/rtlwifi/pci.c:OMRTLACK stage=completion-no-fabricated-ack"; do
	file=${source_gate%%:*}
	needle=${source_gate#*:}
	grep -Fq "$needle" "$file" || {
		echo "honest TX ACK source gate missing: $needle" >&2
		exit 8
	}
done
/usr/sbin/modinfo -p "$module_rtlwifi" | \
	grep -Fq 'hgw500_honest_tx_ack:Do not advertise or fabricate TX ACK status on HGW-500BNA-QCv2 lab runs'
strings "$module_rtlwifi" | grep -Fq \
	'OMRTLACK stage=policy-active reports_tx_ack=0 inject_ack=0 ampdu=unchanged'
strings "$module_rtl_pci" | grep -Fq \
	'OMRTLACK stage=completion-no-fabricated-ack id=%u queue=%d ampdu=%u'

tx_close="$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
for needle in \
	'hgw500_tx_close_diag' \
	'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' \
	'close_diag_max_queued' \
	'high_water_edge' \
	'OMRTLTXCLOSE id=%u q=%u index=%u sw_rp=%u sw_wp=%u hw_rp=%u hw_wp=%u entries=%u queued=%u desc_own=%u bd_own=%u qidx=%08x closed=0'; do
	grep -Fq "$needle" "$tx_close" || {
		echo "TX close diagnostic source gate missing: $needle" >&2
		exit 8
	}
done
/usr/sbin/modinfo -p "$module_rtl8192ee" | \
	grep -Fq 'hgw500_tx_close_diag:Trace RTL8192EE TX ring closure on HGW-500BNA-QCv2 lab runs'
strings "$module_rtl8192ee" | grep -Fq 'OMRTLTXCLOSE id=%u q=%u index=%u'

for needle in \
	'hgw500_tx_dma_wmb' \
	'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")' \
	'rtlpriv->rtlhal.hw_type == HARDWARE_TYPE_RTL8192EE' \
	'dma_wmb();' \
	'OMRTLTX1 stage=publish-barrier-active target=hgw500 rtl8192ee=1 dma64=%u'; do
	grep -Fq "$needle" "$tx_close" || {
		echo "W2-TX1 publish barrier source gate missing: $needle" >&2
		exit 8
	}
done
/usr/sbin/modinfo -p "$module_rtl8192ee" | \
	grep -Fq 'hgw500_tx_dma_wmb:Publish RTL8192EE TXBDs with dma_wmb on HGW-500BNA-QCv2 lab runs'
strings "$module_rtl8192ee" | \
	grep -Fq 'OMRTLTX1 stage=publish-barrier-active target=hgw500 rtl8192ee=1 dma64=%u'

tx_complete="$src/drivers/net/wireless/realtek/rtlwifi/pci.c"
tx_hw="$src/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/hw.c"
for needle in \
	'no_progress_count[RTL_PCI_MAX_TX_QUEUE_COUNT]' \
	'is_power_of_2(no_progress_id)' \
	'UART at 115200 baud is part of the timing budget on Topaz'; do
	grep -Fq "$needle" "$tx_complete" || {
		echo "W2-TX1 bounded TX completion trace gate missing: $needle" >&2
		exit 8
	}
done

tx_header="$src/drivers/net/wireless/realtek/rtlwifi/pci.h"
for needle in \
	'hgw500_txbd_compact32' \
	'hgw500_eapol_trace' \
	'hgw500_eapol_mgnt_queue' \
	'rtl_pci_txbd_entry(ring, idx)' \
	'buffer_desc_stride * entries' \
	'rtl_pci_txbd_queue_compact(rtlpriv, rtlpci, prio) ?' \
	'_rtl_pci_tx_buffer_addr(hw, ring, entry)' \
	'OMRTLTX9 stage=txbd-ring q=%u stride=%u compact=%u' \
	'OMRTLEAPOL stage=tx-enter' \
	'OMRTLEAPOL stage=rx' \
	'OMRTLEAPOL stage=tx_done' \
	'OMRTLEAPOL stage=queue-policy target=hgw500 action=mgnt_queue' \
	'OMRTL stage=pci-tx-queued id=%u q=%u queue_len=%u'; do
	grep -Fq "$needle" "$tx_complete" || {
		echo "W2-TX9 global TXBD source gate missing: $needle" >&2
		exit 8
	}
done
if grep -Fq 'prio <= VO_QUEUE ?' "$tx_complete"; then
	echo 'W2-TX9 refuses hybrid per-queue TXBD widths under the global hardware width bit' >&2
	exit 8
fi
for needle in 'u16 buffer_desc_stride;' 'bool txbd_compact32;' 'rtl_pci_txbd_entry'; do
	grep -Fq "$needle" "$tx_header" || {
		echo "W2-TX2 PCI header gate missing: $needle" >&2
		exit 8
	}
done
for needle in \
	'OEM DMA32 layout: four 8-byte segments in one 0x20-byte TXBD' \
	'memset(tx_bd_desc, 0, 32);' \
	'clear_pci_tx_desc_content(desc, TX_DESC_SIZE);' \
	'tx_bd_desc[3] = cpu_to_le32((u32)addr);' \
	'buffer_desc_stride == 32' \
	'index == HW RP is not'; do
	grep -Fq "$needle" "$tx_close" || {
		echo "W2-TX2 RTL8192EE layout/reclaim gate missing: $needle" >&2
		exit 8
	}
done
for needle in \
	'rtl92ee_is_robust_mgmt_frame_unaligned' \
	'rtl92ee_hgw500_is_eapol_data' \
	'get_unaligned_le16((const u8 *)hdr)' \
	'OMRTLRXALIGN stage=query-safe target=hgw500' \
	'OMRTLRXALIGN stage=signal-safe target=hgw500' \
	'memcpy(&local_hdr, tmp_buf, copy_len);' \
	'ieee80211_is_data_qos(fc)' \
	'hw_queue == MGNT_QUEUE && rtl92ee_hgw500_is_eapol_data(skb, fc)' \
	'(struct ieee80211_qos_hdr *)hdr' \
	'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")'; do
	grep -Fq "$needle" "$tx_close" || {
		echo "W2-TX8 unaligned RX query gate missing: $needle" >&2
		exit 8
	}
done
for needle in \
	'((unsigned long)skb->data & 1)' \
	'skb_push(skb, 1);' \
	'memmove(skb->data, skb->data + 1, frame_len);' \
	'OMRTLRXALIGN stage=frame-realigned target=hgw500 alignment=2'; do
	grep -Fq "$needle" "$tx_complete" || {
		echo "W2-TX8 RX frame alignment gate missing: $needle" >&2
		exit 8
	}
done
for needle in \
	'if (!rtlpci->txbd_compact32 ||' \
	'hgw500_force_txbd64_width))' \
	'wordtmp |= BIT(15);' \
	'rtl_write_word(rtlpriv, REG_RX_RXBD_NUM, wordtmp);' \
	'OMRTLTX6 stage=txbd-system-width compact32=%u force64=%u bit15=%u reg=%04x'; do
	grep -Fq "$needle" "$tx_hw" || {
		echo "W2-TX6 global hardware width gate missing: $needle" >&2
		exit 8
	}
done
/usr/sbin/modinfo -p "$module_rtl_pci" | \
	grep -Fq 'hgw500_txbd_compact32:Use the OEM global 32-byte RTL8192EE TXBD width on HGW-500BNA-QCv2'
/usr/sbin/modinfo -p "$module_rtl_pci" | \
	grep -Fq 'hgw500_eapol_trace:Trace HGW500 RTL8192EE EAPOL TX/RX frames without dumping key material'
/usr/sbin/modinfo -p "$module_rtl_pci" | \
	grep -Fq 'hgw500_eapol_mgnt_queue:Route HGW500 RTL8192EE EAPOL data frames through the management TX queue'
grep -Fq 'static bool hgw500_eapol_mgnt_queue = true;' "$tx_complete" || {
	echo "HGW500 EAPOL management queue default is not enabled" >&2
	exit 8
}
strings "$module_rtl_pci" | grep -Fq 'OMRTLTX9 stage=txbd-layout global_compact32=%u requested=%u dma64=%u'
strings "$module_rtl_pci" | grep -Fq 'OMRTLTX9 stage=txbd-ring q=%u stride=%u compact=%u'
strings "$module_rtl_pci" | grep -Fq 'OMRTL stage=pci-tx-queued id=%u q=%u queue_len=%u'
strings "$module_rtl_pci" | grep -Fq 'OMRTLEAPOL stage=tx-enter'
strings "$module_rtl_pci" | grep -Fq 'OMRTLEAPOL stage=rx'
strings "$module_rtl_pci" | grep -Fq 'OMRTLEAPOL stage=tx_done'
strings "$module_rtl_pci" | grep -Fq 'OMRTLEAPOL stage=queue-policy target=hgw500 action=mgnt_queue'
strings "$module_rtl8192ee" | grep -Fq 'OMRTLTX6 stage=txbd-system-width compact32=%u force64=%u bit15=%u reg=%04x'
strings "$module_rtl8192ee" | grep -Fq 'OMRTLRXALIGN stage=query-safe target=hgw500 rx_shift=%u drvinfo=%u'
strings "$module_rtl8192ee" | grep -Fq 'OMRTLRXALIGN stage=signal-safe target=hgw500 rx_shift=%u drvinfo=%u'
strings "$module_rtl_pci" | grep -Fq 'OMRTLRXALIGN stage=frame-realigned target=hgw500 alignment=2'
grep -Fq 'hgw500_mgmt_reply_rate' "$tx_close" || {
	echo "management reply rate source gate missing parameter" >&2
	exit 8
}
/usr/sbin/modinfo -p "$module_rtl8192ee" | \
	grep -Fq 'hgw500_mgmt_reply_rate:Force HGW500 AUTH/ASSOC reply TX rate: 0=off, 1=1M, 2=2M, 6=6M, 11=11M'
strings "$module_rtl8192ee" | \
	grep -Fq 'OMRTLMGMT stage=force-reply-rate type=%s rate=%u desc_rate=%u fallback=1'
python3 "$root/tools/test_realtek_tx2_ring_accounting.py" >/dev/null
python3 "$root/tools/test_realtek_tx2_source.py" >/dev/null
python3 "$root/tools/test_realtek_beacon_poll.py" >/dev/null
python3 "$root/tools/test_rtl8192ee_rx_unaligned_header.py" >/dev/null
python3 "$root/tools/test_w2_tx17_beacon_aperture.py" >/dev/null
python3 "$root/tools/test_rtl8192ee_mgmt_reply_rate.py" >/dev/null
grep -Fq 'OMRTLTX4 stage=beacon-tasklet-poll' "$tx_complete" || {
	echo "W2-TX4 beacon tasklet poll source gate missing" >&2
	exit 8
}
strings "$module_rtl_pci" | grep -Fq 'OMRTLTX4 stage=beacon-tasklet-poll'
strings "$module_rtl_pci" | grep -Fq 'OMRTLTX17 stage=beacon-aperture stride=%u entries=%u bytes=%zu oem_offset=%u'

tmp="$bundle.tmp.$$"
trap 'rm -rf -- "$tmp"' EXIT HUP INT TERM
rm -rf -- "$tmp"
mkdir -p "$tmp/modules" "$tmp/firmware/rtlwifi" "$tmp/evidence"

cp "$module_ctr" "$tmp/modules/ctr.ko"
cp "$module_ccm" "$tmp/modules/ccm.ko"
cp "$module_cmac" "$tmp/modules/cmac.ko"
cp "$module_cfg80211" "$tmp/modules/cfg80211.ko"
cp "$module_libarc4" "$tmp/modules/libarc4.ko"
cp "$module_mac80211" "$tmp/modules/mac80211.ko"
cp "$module_rtlwifi" "$tmp/modules/rtlwifi.ko"
cp "$module_btcoexist" "$tmp/modules/btcoexist.ko"
cp "$module_rtl_pci" "$tmp/modules/rtl_pci.ko"
cp "$module_rtl8192ee" "$tmp/modules/rtl8192ee.ko"
cp "$firmware" "$tmp/firmware/rtlwifi/rtl8192eefw.bin"
cp "$regdb" "$tmp/firmware/regulatory.db"

test "$(wc -c <"$ramtools")" -eq 816
echo "$ramtools_sha  $ramtools" | sha256sum -c - >/dev/null
cp "$ramtools" "$tmp/ram_insmod"
chmod 0755 "$tmp/ram_insmod"
"${tc}readelf" -h "$tmp/ram_insmod" | \
	grep -Eq 'Machine:.*ARC|Machine:.*ARCompact'
if "${tc}objdump" -d "$tmp/ram_insmod" | grep -Eq '\b(llock|scond)\b'; then
	echo "RAM BusyBox unexpectedly uses ARC atomic instructions" >&2
	exit 8
fi

"${tc}objdump" -dr "$module_rtlwifi" | \
	sed -n '/<rtl_get_hwinfo>:/,/^$/p' > \
	"$tmp/evidence/rtl_get_hwinfo.disasm.txt"
test -s "$tmp/evidence/rtl_get_hwinfo.disasm.txt"
"${tc}objdump" -dr "$module_rtlwifi" | \
	sed -n '/<rtl_init_core>:/,/^$/p' > \
	"$tmp/evidence/rtl_init_core.disasm.txt"
test -s "$tmp/evidence/rtl_init_core.disasm.txt"
if grep -Eq 'ldh.*0xa9cb' "$tmp/evidence/rtl_init_core.disasm.txt"; then
	echo "rtl_init_core still reads the odd historical dev_addr offset" >&2
	exit 8
fi
"${tc}objdump" -dr "$module_rtl8192ee" | \
	sed -n '/<rtl92ee_set_desc>:/,/^$/p' > \
	"$tmp/evidence/rtl92ee_set_desc.disasm.txt"
test -s "$tmp/evidence/rtl92ee_set_desc.disasm.txt"
grep -Eq '[[:space:]]sync([[:space:]]|$)' \
	"$tmp/evidence/rtl92ee_set_desc.disasm.txt" || {
	echo "W2-TX1 dma_wmb did not emit an ARC sync instruction" >&2
	exit 8
}
"${tc}objdump" -dr "$module_rtl_pci" | \
	sed -n '/<_rtl_pci_topaz_tx_complete>:/,/^$/p' > \
	"$tmp/evidence/rtl_pci_topaz_tx_complete.disasm.txt"
test -s "$tmp/evidence/rtl_pci_topaz_tx_complete.disasm.txt"
cp "$out/.config" "$tmp/evidence/kernel.config"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-arc-unaligned-efuse-topaz.patch" \
	"$tmp/evidence/rtlwifi-arc-unaligned-efuse-topaz.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-arc-align-efuse-dev-addr-topaz.patch" \
	"$tmp/evidence/rtlwifi-arc-align-efuse-dev-addr-topaz.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-rtl8192ee-topaz-beacon-irq-window.patch" \
	"$tmp/evidence/rtlwifi-rtl8192ee-topaz-beacon-irq-window.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-pci-managed-deferred-ack-topaz.patch" \
	"$tmp/evidence/rtlwifi-pci-managed-deferred-ack-topaz.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-rtl8192ee-topaz-beacon-poll.patch" \
	"$tmp/evidence/rtlwifi-rtl8192ee-topaz-beacon-poll.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-ap-swcrypto.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-ap-swcrypto.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx-ampdu-lab.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-tx-ampdu-lab.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-honest-tx-ack-lab.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-honest-tx-ack-lab.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx-close-diag.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-tx-close-diag.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx1-publish-barrier.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-tx1-publish-barrier.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx2-pci-header.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-tx2-pci-header.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx2-pci-mode.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-tx2-pci-mode.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx6-global-txbd-width.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-tx6-global-txbd-width.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-rx-unaligned-header-topaz.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-rx-unaligned-header-topaz.patch"
cp "$root/work/kernel-port/linux-5.10/rtlwifi-mitrastar-tx17-beacon-aperture.patch" \
	"$tmp/evidence/rtlwifi-mitrastar-tx17-beacon-aperture.patch"
cp "$root/tools/test_realtek_tx2_ring_accounting.py" \
	"$tmp/evidence/test_realtek_tx2_ring_accounting.py"
cp "$root/tools/test_realtek_tx2_source.py" \
	"$tmp/evidence/test_realtek_tx2_source.py"
cp "$root/tools/test_realtek_beacon_poll.py" \
	"$tmp/evidence/test_realtek_beacon_poll.py"
cp "$root/tools/test_rtl8192ee_rx_unaligned_header.py" \
	"$tmp/evidence/test_rtl8192ee_rx_unaligned_header.py"
cp "$root/tools/test_w2_tx17_beacon_aperture.py" \
	"$tmp/evidence/test_w2_tx17_beacon_aperture.py"
cp "$root/tools/test_rtl8192ee_mgmt_reply_rate.py" \
	"$tmp/evidence/test_rtl8192ee_mgmt_reply_rate.py"

printf '%s\n' \
	'ctr.ko' \
	'ccm.ko' \
	'cmac.ko' \
	'cfg80211.ko' \
	'libarc4.ko' \
	'mac80211.ko' \
	'rtlwifi.ko' \
	'btcoexist.ko' \
	'rtl_pci.ko' \
	'rtl8192ee.ko' > "$tmp/LOAD_ORDER.txt"

(
	cd "$tmp"
	sha256sum ram_insmod modules/*.ko firmware/regulatory.db \
		firmware/rtlwifi/rtl8192eefw.bin > \
		UPLOAD_SHA256SUMS
	cat UPLOAD_SHA256SUMS > SHA256SUMS
	sha256sum evidence/rtl_get_hwinfo.disasm.txt \
		evidence/rtl_init_core.disasm.txt \
		evidence/rtl92ee_set_desc.disasm.txt \
		evidence/rtl_pci_topaz_tx_complete.disasm.txt \
		evidence/rtlwifi-arc-unaligned-efuse-topaz.patch \
		evidence/rtlwifi-arc-align-efuse-dev-addr-topaz.patch \
		evidence/rtlwifi-rtl8192ee-topaz-beacon-irq-window.patch \
		evidence/rtlwifi-pci-managed-deferred-ack-topaz.patch \
		evidence/rtlwifi-rtl8192ee-topaz-beacon-poll.patch \
		evidence/rtlwifi-mitrastar-ap-swcrypto.patch \
		evidence/rtlwifi-mitrastar-tx-ampdu-lab.patch \
		evidence/rtlwifi-mitrastar-honest-tx-ack-lab.patch \
		evidence/rtlwifi-mitrastar-tx-close-diag.patch \
		evidence/rtlwifi-mitrastar-tx1-publish-barrier.patch \
		evidence/rtlwifi-mitrastar-tx2-pci-header.patch \
		evidence/rtlwifi-mitrastar-tx2-pci-mode.patch \
		evidence/rtlwifi-mitrastar-tx6-global-txbd-width.patch \
		evidence/rtlwifi-mitrastar-rx-unaligned-header-topaz.patch \
		evidence/rtlwifi-mitrastar-tx17-beacon-aperture.patch \
		evidence/test_realtek_tx2_ring_accounting.py \
		evidence/test_realtek_tx2_source.py \
		evidence/test_realtek_beacon_poll.py \
		evidence/test_rtl8192ee_rx_unaligned_header.py >> SHA256SUMS
	sha256sum evidence/test_w2_tx17_beacon_aperture.py \
		evidence/test_rtl8192ee_mgmt_reply_rate.py >> SHA256SUMS
)

export OM_ROOT="$root" OM_TMP="$tmp" OM_RELEASE="$release" \
	OM_BASE_IMAGE="$base_image" OM_BASE_VMLINUX="$base_vmlinux" \
	OM_SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1785024000}
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["OM_ROOT"])
bundle = Path(os.environ["OM_TMP"])
image = Path(os.environ["OM_BASE_IMAGE"])
vmlinux = Path(os.environ["OM_BASE_VMLINUX"])

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

items = []
for path in sorted(
    [bundle / "ram_insmod"]
    + list((bundle / "modules").glob("*.ko"))
    + [bundle / "firmware/regulatory.db",
       bundle / "firmware/rtlwifi/rtl8192eefw.bin"]
):
    items.append(
        {
            "path": path.relative_to(bundle).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    )

manifest = {
    "schema": "openmitrastar.realtek-ram-bundle/v1",
    "classification": "RAM-ONLY-NO-FLASH",
    "candidate_eligible": False,
    "kernel_release": os.environ["OM_RELEASE"],
    "source_date_epoch": int(os.environ["OM_SOURCE_DATE_EPOCH"]),
    "load_order": (bundle / "LOAD_ORDER.txt").read_text().splitlines(),
    "artifacts": items,
    "base_ram_image": {
        "path": image.relative_to(root).as_posix(),
        "bytes": image.stat().st_size,
        "sha256": sha256(image),
        "classification": "RAM-ONLY",
    },
    "base_vmlinux": {
        "path": vmlinux.relative_to(root).as_posix(),
        "bytes": vmlinux.stat().st_size,
        "sha256": sha256(vmlinux),
    },
    "safety": {
        "offline_build_only": True,
        "network_used": False,
        "uart_used": False,
        "router_accessed": False,
        "flash_supported": False,
        "persistent_writes_supported": False,
    },
    "static_gates": {
        "arc_elf": "PASS",
        "vermagic": "PASS",
        "pci_10ec_818b_alias": "PASS",
        "firmware_contract": "PASS",
        "regulatory_db_contract": "PASS",
        "unaligned_efuse_source": "PASS",
        "aligned_efuse_dev_addr": "PASS",
        "mitrastar_warm_fw_retry": "PASS",
        "hgw500_tx_ampdu_lab_param": "PASS",
        "hgw500_honest_tx_ack_lab_param": "PASS",
        "hgw500_tx_close_diag_param": "PASS",
        "hgw500_tx_dma_wmb_param": "PASS",
        "tx_complete_trace_bounded": "PASS",
        "hgw500_txbd_compact32_param": "PASS",
        "oem_txbd32_layout": "PASS",
        "hgw500_txbd_global_width_bit": "PASS",
        "hgw500_txbd_oem_parity": "PASS",
        "hgw500_compact32_desc_clear": "PASS",
        "ring_reclaim_model": "PASS",
        "hgw500_beacon_tasklet_poll": "PASS",
        "hgw500_rx_unaligned_header": "PASS",
        "hgw500_rx_unaligned_signal": "PASS",
        "hgw500_beacon_txbd_aperture": "PASS",
        "hgw500_mgmt_reply_rate_param": "PASS",
        "hgw500_eapol_trace_param": "PASS",
        "hgw500_eapol_mgnt_queue_param": "PASS",
    },
    "experiments": {
        "hgw500_tx_ampdu_disable": {
            "module": "rtlwifi.ko",
            "parameter": "hgw500_tx_ampdu_disable",
            "default": False,
            "activation": "explicit-module-parameter-only",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+AP+TX_START",
            "rx_ampdu_unchanged": True,
            "ack_policy_unchanged": True,
        },
        "hgw500_honest_tx_ack": {
            "modules": ["rtlwifi.ko", "rtl_pci.ko"],
            "parameter": "hgw500_honest_tx_ack",
            "default": False,
            "activation": "explicit-module-parameter-only",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE",
            "reports_tx_ack_status": False,
            "fabricated_tx_ack": False,
            "ampdu_unchanged": True,
        },
        "hgw500_tx_close_diag": {
            "module": "rtl8192ee.ko",
            "parameter": "hgw500_tx_close_diag",
            "default": False,
            "activation": "explicit-module-parameter-only",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+BE_QUEUE",
            "observes": ["software-consumer", "software-producer", "hardware-rp", "hardware-wp", "ring-size", "queue-depth", "descriptor-own", "buffer-descriptor-own"],
            "reclaim_behavior_changed": False,
        },
        "hgw500_tx_dma_wmb": {
            "module": "rtl8192ee.ko",
            "parameter": "hgw500_tx_dma_wmb",
            "default": False,
            "activation": "explicit-module-parameter-only",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+non-beacon-TX",
            "ampdu_unchanged": True,
            "ack_policy_unchanged": True,
            "txbd_layout_unchanged": True,
            "txbd_count_unchanged": True,
            "tx_reclaim_unchanged": True,
        },
        "hgw500_txbd_compact32": {
            "module": "rtl_pci.ko",
            "parameter": "hgw500_txbd_compact32",
            "default": False,
            "activation": "explicit-module-parameter-only",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+DMA32+all-TX-queues",
            "txbd_entry_bytes": 32,
            "txbd_segment_bytes": 8,
            "txbd_segments": 4,
            "hardware_width_register": "REG_RX_RXBD_NUM",
            "hardware_width_bit": 15,
            "hardware_width_bit_value": 0,
            "compact_queues": ["BK", "BE", "VI", "VO", "BEACON", "TXCMD", "MGNT", "HIGH", "HCCA"],
            "preserved_64_byte_queues": [],
            "hybrid_layout": False,
            "oem_parity_claim": True,
            "experiment_reason": "TX7 proved management queue RP remains zero when q6 uses a 64-byte stride under global hardware 32-bit TXBD mode",
            "tx_reclaim_unchanged": True,
            "recycled_tx_descriptor_cleared": True,
            "forced_reclaim": False,
            "double_free_uaf_guard": "index-equal-hardware-rp-remains-not-closed",
        },
        "hgw500_mgmt_reply_rate": {
            "module": "rtl8192ee.ko",
            "parameter": "hgw500_mgmt_reply_rate",
            "default": 0,
            "activation": "explicit-module-parameter-only",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+AUTH/ASSOC-reply-management-TX",
            "accepted_values": [0, 1, 2, 6, 11],
            "forced_rates": {
                "1": "DESC_RATE1M",
                "2": "DESC_RATE2M",
                "6": "DESC_RATE6M",
                "11": "DESC_RATE11M"
            },
            "probe_response_unchanged": True,
            "data_path_unchanged": True,
            "txbd_layout_unchanged": True,
            "fallback_allowed": True,
        },
        "hgw500_eapol_trace": {
            "module": "rtl_pci.ko",
            "parameter": "hgw500_eapol_trace",
            "default": False,
            "activation": "explicit-module-parameter-only",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+WPA2-4-way-EAPOL",
            "observes": ["tx-enter", "tx-desc", "tx-doorbell", "rx"],
            "key_material_dumped": False,
            "data_path_unchanged": True,
            "flash_supported": False,
        },
        "hgw500_eapol_mgnt_queue": {
            "modules": ["rtl_pci.ko", "rtl8192ee.ko"],
            "parameter": "hgw500_eapol_mgnt_queue",
            "default": True,
            "activation": "default-on-for-product, module-parameter-can-disable",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+WPA2-4-way-EAPOL",
            "action": "route EAPOL data frames through MGNT_QUEUE with MGNT firmware qsel",
            "normal_data_path_unchanged": True,
            "management_path_unchanged": True,
            "flash_supported": False,
        },
        "hgw500_beacon_tasklet_poll": {
            "module": "rtl_pci.ko",
            "parameter": "none",
            "default": True,
            "activation": "target-gated-runtime-path",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+IRQ28+BEACON_QUEUE",
            "action": "dma_wmb-then-tx_polling-BEACON_QUEUE-after-beacon-tasklet-set-own",
            "data_queue_txbd32_unchanged": True,
            "flash_supported": False
        },
        "hgw500_beacon_txbd_aperture": {
            "module": "rtl_pci.ko",
            "default": True,
            "activation": "target-gated-runtime-path",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+global-32-bit-TXBD+BEACON_QUEUE",
            "descriptor_stride_bytes": 32,
            "allocated_entries": 4,
            "allocated_bytes": 128,
            "oem_beacon_offset_bytes": 128,
            "data_path_unchanged": True,
            "own_reclaim_rate_ampdu_irq_unchanged": True,
            "flash_supported": False
        },
        "hgw500_rx_unaligned_header": {
            "modules": ["rtl8192ee.ko", "rtl_pci.ko"],
            "activation": "target-gated-runtime-path",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+ARC700+odd-RX-shift",
            "fault_signature": {
                "work": "_rtl_pci_rx_work",
                "caller": "_rtl_pci_rx_interrupt+0x188",
                "callee": "rtl92ee_rx_query_desc+0x204",
                "instruction": "ldw_s r1,[r1,0x18]",
                "efa": "0x86f900a9"
            },
            "query_frame_control": "get_unaligned_le16",
            "post_reserve_frame_alignment": 2,
            "non_target_behavior_unchanged": True,
            "flash_supported": False
        },
        "hgw500_rx_unaligned_signal": {
            "module": "rtl8192ee.ko",
            "activation": "target-gated-runtime-path",
            "scope": "mitrastar,hgw-500bna-qcv2+RTL8192EE+ARC700+odd-RX-shift+signal-parse",
            "fault_signature": {
                "callee": "rtl92ee_rx_query_desc+0x346",
                "instruction": "ldh.aw r1,[r21,r1]",
                "efa": "0x85a9c05b",
                "eret": "0x701fcf7e"
            },
            "aligned_header_copy": True,
            "raw_rx_frame_unchanged": True,
            "flash_supported": False
        }
    },
    "regulatory_database": {
        "path": "firmware/regulatory.db",
        "sha256": "e9051546c38849b54e6b6a90ca32151c9e29f23edb7698f2c4a437fc353b3393",
        "install_before_module": "cfg80211.ko",
        "force_reg_after_load": False,
    },
}
(bundle / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

rm -rf -- "$bundle"
mkdir -p "$(dirname -- "$bundle")"
mv -- "$tmp" "$bundle"
trap - EXIT HUP INT TERM

printf 'REALTEK_INCREMENTAL_BUNDLE_PASS release=%s bundle=%s\n' \
	"$release" "$bundle"
