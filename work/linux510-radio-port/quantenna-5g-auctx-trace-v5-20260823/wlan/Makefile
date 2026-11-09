# Linux 5.10 compile gate for Quantenna's net80211 compatibility layer.

QTN_GPL := $(src)/../../../sources/Quantenna-GPL
QDRV_COMPAT := $(src)/../qdrv/compat/include

ccflags-y += -Wall -Wno-error -Wno-unused-function -Wno-unused-variable
ccflags-y += -Wno-error=implicit-function-declaration
ccflags-y += -include $(QDRV_COMPAT)/openmitrastar_qdrv_compat.h
ccflags-y += -DQDRV -DQSCS_ENABLED -DQTN_BG_SCAN -DQBMPS_ENABLE
ccflags-y += -DCONFIG_ARCH_ARC=1 -DCONFIG_RUBY=1
ccflags-y += -DCONFIG_QTN_80211K_SUPPORT -DQTN_DYN_CCA=1
ccflags-y += -mlong-calls
ccflags-y += -I$(QDRV_COMPAT)
ccflags-y += -I$(QTN_GPL)
ccflags-y += -I$(QTN_GPL)/drivers
ccflags-y += -I$(QTN_GPL)/drivers/ruby
ccflags-y += -I$(QTN_GPL)/include
ccflags-y += -I$(QTN_GPL)/drivers/include/shared
ccflags-y += -I$(QTN_GPL)/drivers/include/kernel
ccflags-y += -I$(QTN_GPL)/common

wlan-objs := wlan_fwt_compat.o if_media.o ieee80211_beacon.o ieee80211_beacon_desc.o \
	ieee80211_crypto.o ieee80211_crypto_none.o ieee80211_proto.o \
	ieee80211_output.o ieee80211_power.o ieee80211_scan.o \
	ieee80211_wireless.o ieee80211_linux.o ieee80211_rate.o \
	ieee80211_input.o ieee80211_node.o ieee80211_tdls.o ieee80211_tpc.o \
	ieee80211_mlme_statistics.o ieee80211.o

wlan_scan_sta-objs := ieee80211_scan_sta.o
wlan_scan_ap-objs := ieee80211_scan_ap.o
wlan_ccmp-objs := ieee80211_crypto_ccmp.o
wlan_tkip-objs := ieee80211_crypto_tkip.o
wlan_xauth-objs := ieee80211_xauth.o

obj-m += wlan.o wlan_scan_ap.o wlan_scan_sta.o
obj-m += wlan_ccmp.o wlan_tkip.o wlan_xauth.o
