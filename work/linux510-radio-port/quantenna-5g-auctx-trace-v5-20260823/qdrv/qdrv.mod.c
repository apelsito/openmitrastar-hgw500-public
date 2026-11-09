#include <linux/module.h>
#define INCLUDE_VERMAGIC
#include <linux/build-salt.h>
#include <linux/vermagic.h>
#include <linux/compiler.h>

BUILD_SALT;

MODULE_INFO(vermagic, VERMAGIC_STRING);
MODULE_INFO(name, KBUILD_MODNAME);

__visible struct module __this_module
__section(".gnu.linkonce.this_module") = {
	.name = KBUILD_MODNAME,
	.init = init_module,
#ifdef CONFIG_MODULE_UNLOAD
	.exit = cleanup_module,
#endif
	.arch = MODULE_ARCH_INIT,
};

#ifdef CONFIG_RETPOLINE
MODULE_INFO(retpoline, "Y");
#endif

MODULE_INFO(depends, "wlan,temp_sensor,qtn_platform_support,hbm,switch_vlan,switch_tqe,runtime_compat,qtn_pm_qos_compat,switch_emac,board_compat,gpio,topaz_congest_queue,emac_lib,iputil,temp_sens");


MODULE_INFO(srcversion, "72638F0E06DD4DD45DF66B4");
