#ifndef OPENMITRASTAR_COMPAT_BOARD_KDUMP_H
#define OPENMITRASTAR_COMPAT_BOARD_KDUMP_H

/* The OEM crash-dump dispatcher is not part of mainline Linux 5.10. */
static inline void kdump_add_troubleshooter(void (*fn)(void))
{
}

#endif
