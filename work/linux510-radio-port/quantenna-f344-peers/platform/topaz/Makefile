QTN_GPL := $(src)/../../../../sources/Quantenna-GPL
QDRV_COMPAT := $(src)/../../qdrv/compat/include

ifeq ($(OPENMITRASTAR_QDRV_V89_PAIR),1)
ccflags-y += -DOPENMITRASTAR_QDRV_V89_PAIR=1
endif

ifeq ($(OPENMITRASTAR_SWITCH_EMAC_PORT),1)
ccflags-y += -DOPENMITRASTAR_SWITCH_EMAC_PORT=1
ccflags-y += -DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1
endif

ccflags-y += -Wall -Wno-error -Wno-unused-function -Wno-unused-variable
ccflags-y += -Wno-error=implicit-function-declaration -mlong-calls
ccflags-y += -include $(QDRV_COMPAT)/openmitrastar_qdrv_compat.h
ccflags-y += -DCONFIG_ARCH_ARC=1 -DCONFIG_RUBY=1 -DCONFIG_TOPAZ=1
ccflags-y += -DQTN_DEBUG -DQDRV
ccflags-y += -DOPENMITRASTAR_NO_LEGACY_PROC
ccflags-y += -I$(QDRV_COMPAT) -I$(QTN_GPL) -I$(QTN_GPL)/common
ccflags-y += -I$(QTN_GPL)/drivers -I$(QTN_GPL)/include
ccflags-y += -I$(QTN_GPL)/drivers/include/shared
ccflags-y += -I$(QTN_GPL)/drivers/include/kernel
ccflags-y += -I$(src)/../ruby

obj-m += hbm.o temp_sens.o topaz_congest_queue.o
obj-m += switch_tqe.o switch_vlan.o fwt_if.o
ifeq ($(OPENMITRASTAR_SWITCH_EMAC_PORT),1)
obj-m += dpi.o switch_emac.o
endif
