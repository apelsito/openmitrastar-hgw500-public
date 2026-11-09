# F344 continuation notes — 2026-09-21

Parent assigned full AP/STA/repeater workflows, offline only. Wi-Fi/RF/client
execution is USER_DEFERRED; no router, AELITA, UART, network or flash action.
F341 has been delivered and must not be changed/repacked. F343 CPU-halt work
was rejected by automatic control and is canceled: do not recreate or disguise it.

F341 delivered image:
`/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f341-f340-native-diagnostic-device-bound/`
5,406,720B SHA f6c6184a4e08265a741f42df0a92a91a1cb2bf9aa513fabb0d861cff06494595;
manifest SHA011ac6b08b85449ca21eb46363861fd702556033781ff3a5b97beb5174369a09.
Result `outputs/preflight/f341-fullimage-20260921T135223Z/result.json` PASS offline.
Doc `docs/OPENMITRASTAR_F341_NATIVE_DIAGNOSTIC_IMAGE.md`.

## Parallel work

- `/root/dfs_core_audit` is building vendor wpa_supplicant1.1 + wpa_cli with
  MADWIFI and literal -r support. Preserve vendor OpenSSL/EAP profile; it found
  openssl-1.0.2d tarball in GPL download_backup. ARC/noatomic sysroot as below.
- `/root/hardware_parity_inventory` F342 is only the portable config journal:
  `work/kernel-port/modules/f342_config_journal`, blob1..4096B, caller-owned
  f318_store_ops, save alternating DC/DD. No runtime transport or SPI backend.
  F344 can own `/run/openmitrastar/f344`; persistence remains separate/unarmed.
- Root is doing F345 SPI research. Root alone operates hardware.

## Proven OEM contracts

Sources `work/hgw500-rootfs-live/squashfs-root/scripts/`:

- `start-prod:8..76`: explicit mode ap/sta/repeater. Three-way selector0 AP,
  1 STA, 2 AUTO; AUTO uses static-IP setting and DHCP lease presence to choose
  AP/STA, not repeater. Do not copy the original br0-address changes or DHCP
  side effects into a management-preserving transition.
- `start-vap:129..150,858..869`: repeater means primary wifi0 STA, both scan
  modules, `iwpriv wifi0 repeater 1`, then `start 0 ap wifi1`, hostapd on wifi1.
  Not the same as QHOP/WDS extender role.
- `start-helpers.sh:128..172`: STA supplicant command
  `wpa_supplicant -B -q -iwifi0 -bbr0 -Dmadwifi -c PRIVATE_CONFIG`; repeater adds
  `-r`. -r is parsed/stored in vendor source but core agent found no behavioral
  consumer; real repeater effect comes from driver ioctl and secondary AP.
- `qtn_wds_ext.sh`: extender MBS/RBS rejects coexistence with repeater. Its
  original reload script powers down Ethernet ports; do not copy that action.
- QCSAPI qcsapi.h6990..7015 documents generic selector GPIO12/13, but its CLI
  description inconsistently says1/2/3; start-prod and API contract use0/1/2.
  This does NOT prove the HGW A2 physical selector mapping. GPIO12 appears as
  OEM monitor_rfenable separately. No GPIO configuration/claim invented.

## Existing port gaps / reusable primitives

- F321/F341 full inventory contains hostapd, hostapd-qtn, hostapd-cli-qtn,
  hostapd_cli. No wpa_supplicant, wpa_cli, call_qcsapi or qbr was found.
- Current driver source for new clone:
  `work/linux510-radio-port/quantenna-f338-availability` (qdrv subtree).
  Its wlan files are in `work/linux510-radio-port/quantenna/wlan` / coherent
  F332 peer snapshot, not that qdrv-only source clone.
- qdrv_control.c227..360 added HGW sequential gate permits only one
  `start 0 ap wifi0 FACTORY_MAC` after core start. It rejects STA, APwifi1,
  and post-start stop. Need a separately enabled F344 typed extension using
  actual current VAP topology, preserving the existing default AP behavior.
- Native qdrv_command_start897..1020 already supports ap/sta/wds and argc4/5.
  wifi1 argc4 uses the driver's own MAC derivation; don't invent a BSSID.
- Native qdrv_command_stop1075..1136 supports `stop 0 IFNAME` and `stop 0 all`.
  The all form calls qdrv_radar_unload and qdrv_wlan_cleanup_before_reload.
  qdrv_radar_unload2169 only calls radar_disable. Inspect cleanup behavior
  before choosing a warm-transition policy; preserve real NOP restrictions.
- qdrv_vap.c59..90 `openmitrastar_rf_enable` is a gate on ndo_open only.
  Setting0 does NOT mute an already-UP interface. Use administrative DOWN
  with readback before delete/recreate, never claim hardware quiescence.
- ieee80211_wireless.c11743 REPEATER ioctl requires first VAP STA and rejects
  extender MBS/RBS. It sets ic_flags_ext REPEATER and resets first VAP to INIT.
- Native channel mask API exists: SETCHANLIST at15929, GETCHANLIST16016;
  ioctls SIOCIWFIRSTPRIV+6/+7 and struct ieee80211req_chanlist in shared
  drivers/include/shared/net80211/ieee80211_ioctl.h.
  Use actual set/get mask36/40/44/48 with primary VAP DOWN before station
  security starts. Do not rely on supplicant scan_freq: MADWIFI1913..1949
  ignores params.freqs and sends an empty SIOCSIWSCAN request.
- Vendor supplicant STATUS includes mode/state/BSSID/SSID/id/keymgmt/ciphers,
  no frequency. Use actual SIOCGIWFREQ for current frequency; BSS query freq
  is not the same as live association frequency.
- hostapd-QTN GET_CONFIG emits passphrase/psk only with CONFIG_WPS and
  wps_state!=0 (zhostapd/hostapd-git/hostapd/ctrl_iface.c608..658).
  Never assume rollback secrets are recoverable from every running AP.
  Require a complete private managed snapshot/config source, not unknown0.

## Implementation direction (not yet qualified)

New `work/kernel-port/f344` and version/components only. Need actual qdrv
mode admission extension, portable transaction core, native userspace backend
and deterministic fake-transport tests. Snapshot and read back management,
VAP topology/modes, channel mask/frequency, security and private configs.
Use per-interface daemon control sockets, not global pidof/killall (2.4 GHz
management AP must survive). Applied state requires full readback; on failure
restore exact prior snapshot and verify restoration, otherwise report unknown.
Do not present station/client CGI as a station uplink implementation.

Build context: F340 kernel config
f374913b8d2adc7c4138af32263b650eeb967b4defc0139cfd00e6bff7ba1118;
`analysis/f340-watchdog-kernel-20260921T132951Z/result.json` and a/Module.symvers.
Clone context in F341 closure also exists; never edit F340/F341 sealed outputs.
ARC tc `work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-` or
`arc-snps-linux-uclibc-`; sysroot
`/home/user/openmitrastar-uclibc-noatomic-sysroot`. Use -mno-atomic.
Wsl distro podman-mem9-tidb; script files + `wsl -u root -e sh FILE` avoid quoting.

## Initial implementation now present

`f344_mode_gate.[ch]` and `test_mode_gate.c` implement the portable VAP admission
and selector policy. New clone `work/linux510-radio-port/quantenna-f344-modes`
has an opt-in module parameter, live-topology precheck for AP0/STA0/AP1 and
stop0all, and serialization of the existing qdrv control buffer. Created by
`tools/prepare_f344_qdrv.py`. Default gate off preserves the old AP-only
behavior. No new hardware action was taken.

First gate build/test passed (not the final workflow delivery):
`outputs/preflight/f344-mode-gate-20260921T141605Z/result.json`:20 portable
cases +11 actual topology helper cases.
`outputs/kernel-port/f344-qdrv-modes-20260921T141633Z/manifest.json`:two
identical qdrv builds,689340B SHA592815e75de02fa99e607ae0e96bc68134f2a95a30ea3dd888dee4aa5b0396bb.
New parameter openmitrastar_mode_workflow0400; all14 existing parameters and
beacon getter preserved; target F340 config, provider qtn_radar_f338.
Build tool `tools/build_f344_qdrv.py`; test `tools/test_f344_gate.py`.
No transaction/backend implementation yet. Next needs a sanitized kernel
mode/topology readback (including 3-address bridge flag and channel bit-offset)
and real native userspace snapshot/transition/rollback transport.

Additional exact findings: RF-enable is only ndo_open admission, so every
transition must administratively DOWN both known VAPs before closing it.
SETCHANLIST shifts input bits for OFDM: input bit(channel-1) maps to actual
channel; GETCHANLIST returns bit(channel). ieee80211.c998 fixes this port's
ic_phytype=IEEE80211_T_OFDM. Never SET an unadjusted GET mask. Need native
encode/readback helpers and tests. qdrv_wlan_cleanup_before_reload only resets
ic_chan_is_set; qdrv_radar_unload calls radar_disable and does not itself
erase the NOP array. Full transaction/backend/snapshot code is still pending.
