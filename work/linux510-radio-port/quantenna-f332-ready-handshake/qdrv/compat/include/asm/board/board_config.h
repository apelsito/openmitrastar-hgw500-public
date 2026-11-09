#ifndef OPENMITRASTAR_COMPAT_BOARD_CONFIG_H
#define OPENMITRASTAR_COMPAT_BOARD_CONFIG_H

#include <linux/types.h>

#include <common/ruby_board_cfg.h>

int qtn_get_hw_config_id(void);
int qtn_get_spi_protect_config(void);
int get_board_config(int board_config_param, int *board_config_value);
int get_all_board_params(char *buffer);
int board_slow_ethernet(void);
int board_napi_budget(void);

#endif
