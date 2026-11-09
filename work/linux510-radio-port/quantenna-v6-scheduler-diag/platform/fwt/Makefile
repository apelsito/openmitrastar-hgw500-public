QTN_GPL := $(src)/../../../../sources/Quantenna-GPL
QDRV_COMPAT := $(src)/../../qdrv/compat/include

ccflags-y += -Wall -Wno-error -Wno-unused-function -Wno-unused-variable
ccflags-y += -Wno-error=implicit-function-declaration -mlong-calls
ccflags-y += -include $(QDRV_COMPAT)/openmitrastar_qdrv_compat.h
ccflags-y += -DCONFIG_ARCH_ARC=1 -DCONFIG_RUBY=1 -DCONFIG_TOPAZ=1
ccflags-y += -DQTN_DEBUG -DQDRV
ccflags-y += -DOPENMITRASTAR_NO_LEGACY_PROC
ccflags-y += -DOPENMITRASTAR_NO_LEGACY_BRIDGE
ccflags-y += -I$(QDRV_COMPAT) -I$(QTN_GPL) -I$(QTN_GPL)/common
ccflags-y += -I$(QTN_GPL)/drivers -I$(QTN_GPL)/include
ccflags-y += -I$(QTN_GPL)/drivers/include/shared
ccflags-y += -I$(QTN_GPL)/drivers/include/kernel

fwt_ctrl-objs := fwt.o fwt_sw.o fwt_db.o
obj-m += fwt_ctrl.o
