QTN_GPL := $(src)/../../../../sources/Quantenna-GPL
QDRV_COMPAT := $(src)/../../qdrv/compat/include

ccflags-y += -Wall -Wno-error -Wno-unused-function -Wno-unused-variable
ccflags-y += -Wno-error=implicit-function-declaration -mlong-calls
ccflags-y += -include $(QDRV_COMPAT)/openmitrastar_qdrv_compat.h
ccflags-y += -DCONFIG_ARCH_ARC=1 -DCONFIG_RUBY=1 -DCONFIG_TOPAZ=1
ccflags-y += -DQTN_DEBUG
ccflags-y += -I$(QDRV_COMPAT) -I$(QTN_GPL) -I$(QTN_GPL)/common
ccflags-y += -I$(QTN_GPL)/drivers -I$(QTN_GPL)/include
ccflags-y += -I$(QTN_GPL)/drivers/include/shared
ccflags-y += -I$(QTN_GPL)/drivers/include/kernel

bootcfg-objs := bootcfg_drv.o bootcfg_mtd.o bootcfg_eeprom.o \
	bootcfg_store_init.o bootcfg_compress.o bootcfg_file.o
obj-m += bootcfg.o
