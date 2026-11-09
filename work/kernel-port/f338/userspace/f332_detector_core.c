/* Exact OEM detector, new capacity/time/cadence adapter. No Linux objects
 * are passed into legacy bytes. Caller serializes this single engine.
 */
#include "f332_detector.h"
#include "f328_legacy_abi.h"
#include "eu-profile.h"
extern void f328_oem_detect_init(void*);
extern void f328_oem_detect_reset(void);
extern _Bool f328_oem_detect_radar(struct f332_pulse*,int,int,void*);
extern _Bool f328_oem_detect_radar_poll(void);
static uint32_t control[0x89c/4],generation,channel,bandwidth;
static struct f332_pulse pulses[256];
static struct f332_zc crossing;
static int active;
_Static_assert(sizeof(struct f332_pulse)==16,"OEM raw layout");
_Static_assert(sizeof(struct f332_zc)==21956,"OEM ZC layout");
static int snapshot(struct f332_detection *r,int found)
{
 if(!r)return -1;
 f328_abi_memset(r,0,sizeof(*r));r->generation=generation;r->channel=channel;r->bandwidth=bandwidth;r->fault=f328_fault;r->candidate=!!found;
 f328_abi_memcpy(r->configuration,control,300);f328_abi_memcpy(r->statistics,(unsigned char*)control+300,700);
 return f328_fault?-3:0;
}
int f332_detect_begin(uint32_t gen,uint32_t chan,uint32_t bw,uint32_t ticks)
{
 if(!gen||!chan||chan>196||(bw!=20&&bw!=40&&bw!=80))return -1;
 if(active)return -2;
 f328_abi_memset(f328_oem_bss,0,0x9458);f328_abi_memset(control,0,sizeof(control));
 f328_abi_memcpy(control,f328_eu_cfg,300);f328_fault=0;
 f328_abi_init_timer_key((void*)(f328_oem_bss+0x92f8),0,0);
 f328_abi_init_timer_key((void*)(f328_oem_bss+0x9314),0,0);
 if(f328_virtual_clock(200,ticks))return -3;
 f328_oem_detect_init(control);f328_oem_detect_reset();
 if(f328_fault)return -3;
 generation=gen;channel=chan;bandwidth=bw;active=1;return 0;
}
int f332_detect_step(uint32_t gen,const struct f332_pulse *p,unsigned total,unsigned current_count,
 const int32_t *indices,const struct f332_zc *zc,int poll_due,uint32_t ticks,struct f332_detection *result)
{
 unsigned i;int found=0;
 if(!result||total>256||current_count>128||current_count>total||(total&&!p)||!indices||!zc||(poll_due!=0&&poll_due!=1)||zc->accurate>1)return -1;
 if(!active||gen!=generation)return -2;
 for(i=0;i<total;i++)if(p[i].tagged>1)return -1;
 /* 32-bit epoch-adjusted timestamps are intentional: qualified in QEMU. */
 if(f328_advance(ticks)){active=0;return -3;}
 f328_abi_memset(pulses,0,sizeof(pulses));
 if(total)f328_abi_memcpy(pulses,p,total*sizeof(*p));
 f328_abi_memcpy(&crossing,zc,sizeof(crossing));
 f328_abi_memcpy((unsigned char*)control+300+120,indices,128*sizeof(*indices));
 ((unsigned char*)control)[215]=0; /* OEM worker 41e2..41ec. */
 if(poll_due)found=f328_oem_detect_radar_poll();
 if(!found&&total)found=f328_oem_detect_radar(pulses,(int)total,(int)current_count,&crossing);
 if(f328_fault){active=0;return snapshot(result,0);}
 return snapshot(result,found);
}
int f332_detect_snapshot(uint32_t gen,struct f332_detection *r)
{if(!active||gen!=generation)return -2;return snapshot(r,0);}
int f332_detect_environment(uint32_t gen,unsigned ocac,uint32_t scan,unsigned weather)
{
 if(!active||gen!=generation)return -2;
 if(ocac>1||weather>1||scan>196)return -1;
 /* OEM UP spinlock has size0. radar_ocac_info flags are offsets0,1,85;
  * detector reads at9794/9798 and999a/999c confirm the exact layout. */
 f328_oem_bss[0x9104]=(unsigned char)ocac;f328_oem_bss[0x9105]=(unsigned char)scan;
 f328_oem_bss[0x9159]=(unsigned char)weather;return 0;
}
int f332_detect_reset(uint32_t gen)
{if(!active||gen!=generation)return -2;f328_oem_detect_reset();return f328_fault?-3:0;}
int f332_detect_end(uint32_t gen)
{
 if(gen!=generation)return -2;
 if(active)f328_oem_detect_reset();
 f328_abi_del_timer((void*)(f328_oem_bss+0x92f8));f328_abi_del_timer((void*)(f328_oem_bss+0x9314));active=0;return 0;
}
