#ifndef OPENMITRASTAR_COMPAT_BOARD_GPIO_H
#define OPENMITRASTAR_COMPAT_BOARD_GPIO_H

#include <linux/types.h>

#define ARCH_NR_GPIOS 22

void gpio_config(u32 pin, u32 config);
void gpio_uart0_config(void);
void gpio_uart1_config(void);
void gpio_spi_flash_config(void);
int gpio_enable_pwm(u32 pin, u32 high_count, u32 low_count);
u32 gpio_disable_pwm(u32 pin);
void gpio_wowlan_output(u32 pin, u32 config);

#endif
