# Joint Linux 5.10 build gate for the Quantenna host stack.

ifeq ($(OPENMITRASTAR_QDRV_V89_PAIR),1)
subdir-ccflags-y += -DOPENMITRASTAR_QDRV_V89_PAIR=1
endif

ifeq ($(OPENMITRASTAR_SWITCH_EMAC_PORT),1)
subdir-ccflags-y += -DOPENMITRASTAR_SWITCH_EMAC_PORT=1
subdir-ccflags-y += -DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1
endif

obj-m += wlan/
obj-m += qdrv/
obj-m += platform/
