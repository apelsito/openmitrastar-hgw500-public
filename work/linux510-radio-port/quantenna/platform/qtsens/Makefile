QTN_GPL := $(src)/../../../../sources/Quantenna-GPL
QDRV_COMPAT := $(src)/../../qdrv/compat/include

ccflags-y += -Wall -Wno-error -Wno-unused-function -Wno-unused-variable
ccflags-y += -Wno-error=implicit-function-declaration -mlong-calls
ccflags-y += -include $(QDRV_COMPAT)/openmitrastar_qdrv_compat.h
ccflags-y += -DCONFIG_ARCH_ARC=1 -DCONFIG_RUBY=1 -DCONFIG_TOPAZ=1
ccflags-y += -I$(QDRV_COMPAT) -I$(QTN_GPL) -I$(QTN_GPL)/common
ccflags-y += -I$(QTN_GPL)/drivers -I$(QTN_GPL)/include
ccflags-y += -I$(QTN_GPL)/drivers/include/shared
ccflags-y += -I$(QTN_GPL)/drivers/include/kernel

obj-m += temp_sensor.o
