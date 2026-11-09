/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef F352_CONTRACT_H
#define F352_CONTRACT_H
/* Units/bit definitions follow Linux 5.10 include/uapi/linux/mii.h. */
static inline int f352_link_decode(unsigned bmcr, unsigned bmsr,
 unsigned advertise, unsigned partner, unsigned advertise1000,
 unsigned partner1000, unsigned *speed, unsigned *full)
{
 unsigned common;
 if (!(bmsr & 0x0004)) return -67; /* ENOLINK, BMSR_LSTATUS */
 if (!(bmcr & 0x1000)) {
  *speed=(bmcr & 0x0040)?1000:((bmcr & 0x2000)?100:10);
  *full=!!(bmcr & 0x0100);return 0;
 }
 if (!(bmsr & 0x0020)) return -11; /* EAGAIN, BMSR_ANEGCOMPLETE */
 common=partner1000 & (advertise1000 << 2);
 if(common & 0x0800){*speed=1000;*full=1;return 0;}
 if(common & 0x0400){*speed=1000;*full=0;return 0;}
 common=advertise & partner;
 if(common & 0x0100){*speed=100;*full=1;return 0;}
 if(common & 0x0080){*speed=100;*full=0;return 0;}
 if(common & 0x0040){*speed=10;*full=1;return 0;}
 if(common & 0x0020){*speed=10;*full=0;return 0;}
 return -5; /* EIO: no supported common mode, leave outputs unchanged. */
}
/* OEM S40network + scripts/mac_setlocal add TWO to the first octet.
 * This is not an OR operation. Reject its textual overflow instead of wrapping.
 */
static inline int f352_secondary_mac(const unsigned char *primary,
 unsigned char *secondary)
{
 unsigned i,nonzero=0;
 for(i=0;i<6;i++)nonzero|=primary[i];
 if(!nonzero || (primary[0]&1) || primary[0]>253)return -22;
 for(i=0;i<6;i++)secondary[i]=primary[i];
 secondary[0]=(unsigned char)(primary[0]+2);return 0;
}
/* Same all-or-nothing loop used by the driver and host fault tests. */
struct f352_lifecycle {
 void *ctx;
 int (*create)(void *,unsigned);
 void (*destroy)(void *,unsigned);
};
static inline int f352_register_pair(const struct f352_lifecycle *ops)
{
 unsigned i;int error;
 for(i=0;i<2;i++){
  error=ops->create(ops->ctx,i);
  if(error){while(i)ops->destroy(ops->ctx,--i);return error;}
 }
 return 0;
}
static inline void f352_unregister_pair(const struct f352_lifecycle *ops)
{ops->destroy(ops->ctx,1);ops->destroy(ops->ctx,0);}
#endif
