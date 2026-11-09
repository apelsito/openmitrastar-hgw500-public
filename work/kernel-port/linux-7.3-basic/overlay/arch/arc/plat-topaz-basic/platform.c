// SPDX-License-Identifier: GPL-2.0-only
/* No reset, watchdog, network, storage or radio platform callbacks. */
#include <linux/init.h>
#include <asm/mach_desc.h>

static const char *topaz_basic_compat[] __initconst = {
    "openmitrastar,hgw500-topaz-basic",
    NULL,
};

MACHINE_START(TOPAZ_BASIC, "OpenMitraStar Topaz BASIC UART")
    .dt_compat = topaz_basic_compat,
MACHINE_END
