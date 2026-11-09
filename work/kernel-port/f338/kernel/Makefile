QTN_GPL ?= $(src)/../../../../sources/Quantenna-GPL
QDRV_COMPAT ?= $(src)/../../../../linux510-radio-port/quantenna/qdrv/compat/include
ccflags-y += -Wall -Wno-unused-parameter -mlong-calls
ccflags-y += -DOPENMITRASTAR_QDRV_V89_PAIR=1 -DOPENMITRASTAR_SWITCH_EMAC_PORT=1 -DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1
ccflags-y += -DCONFIG_ARCH_ARC=1 -DCONFIG_RUBY=1 -DCONFIG_TOPAZ=1
ccflags-y += -I$(QTN_GPL) -I$(QTN_GPL)/drivers -I$(QTN_GPL)/include -I$(QTN_GPL)/drivers/include/shared -I$(QTN_GPL)/drivers/include/kernel -I$(QTN_GPL)/common -I$(QDRV_COMPAT)
ccflags-y += -I$(src)/../uapi
obj-m += qtn_radar_f338.o
qtn_radar_f338-y := f332_provider.o f332_hardware.o f338_pipeline.o f338_protocol.o f338_ipc.o f331_postfilter.o f332_events.o f332_ocac.o f333_acquisition.o
