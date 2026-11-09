#ifndef OPENMITRASTAR_COMPAT_TROUBLESHOOT_H
#define OPENMITRASTAR_COMPAT_TROUBLESHOOT_H

#define HEADER_CORE_DUMP 0xDEAD

typedef int (*arc_troubleshoot_start_hook_cbk)(void *context);

void arc_set_sram_safe_area(unsigned long start, unsigned long end);
void arc_save_to_sram_safe_area(int compress_ratio);
void arc_set_troubleshoot_start_hook(
	arc_troubleshoot_start_hook_cbk callback, void *context);
void *get_log_buf(int *length, int *first, char **buffer);

#endif
