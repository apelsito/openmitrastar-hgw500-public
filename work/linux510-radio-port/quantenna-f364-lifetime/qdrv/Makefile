# Linux 5.10 compile gate for the native Quantenna Topaz/QMAC driver.
# This tree is laboratory-only and is never packaged into a flash image.

QTN_GPL := $(src)/../../../sources/Quantenna-GPL

ccflags-y += -Wall -Wno-error -Wno-unused-function -Wno-unused-variable
ccflags-y += -Wno-error=implicit-function-declaration
ccflags-y += -include $(src)/compat/include/openmitrastar_qdrv_compat.h
ccflags-y += -DQDRV -DQSCS_ENABLED -DQTN_BG_SCAN -DQBMPS_ENABLE
ccflags-y += -DCONFIG_ARCH_ARC=1 -DCONFIG_RUBY=1
ccflags-y += -DCONFIG_QTN_80211K_SUPPORT -DQTN_ENABLE_TRACE_BUFFER=0
ccflags-y += -DQTN_DEBUG -mlong-calls
ccflags-y += -DOPENMITRASTAR_QDRV_NO_IPV6_OFFLOAD
ccflags-y += -DOPENMITRASTAR_NO_LEGACY_PROC
ccflags-y += -I$(src)/compat/include
ccflags-y += -I$(QTN_GPL)
ccflags-y += -I$(QTN_GPL)/drivers
ccflags-y += -I$(QTN_GPL)/include
ccflags-y += -I$(QTN_GPL)/drivers/include/shared
ccflags-y += -I$(QTN_GPL)/drivers/include/kernel
ccflags-y += -I$(QTN_GPL)/common

qdrv-objs := qdrv_f355_lifetime.o qdrv_kernel_compat.o qdrv_radar_compat.o qdrv_fwt_compat.o qdrv_module.o qdrv_control.o qdrv_soc.o qdrv_hal.o \
	qdrv_muc.o qdrv_mac.o qdrv_mac_reserve.o qdrv_comm.o qdrv_wlan.o \
	qdrv_tx.o qdrv_rx.o qdrv_scan.o qdrv_hostlink.o qdrv_vap.o \
	qdrv_dsp.o qdrv_txbf.o qdrv_muc_stats.o qdrv_radar.o qdrv_math.o \
	qdrv_bridge.o qdrv_uc_print.o qdrv_sch.o qdrv_sch_pm.o \
	qdrv_pktlogger.o qdrv_auc.o qdrv_pcap.o qdrv_vlan.o qdrv_show.o \
	qdrv_mu.o qdrv_fw.o

obj-m += qdrv.o
