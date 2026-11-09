// SPDX-License-Identifier: GPL-2.0-only
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/io.h>
#include <linux/string.h>
#include <linux/ktime.h>
#include <linux/timekeeping.h>
#include <linux/printk.h>
#include <qtn/qtn_bb_mutex.h>
#include <common/ruby_pm_mproc.h>
#include <radar/radar.h>
#include "f332_hardware.h"
#include "f338_pipeline.h"
static bool shadow_enable,f315_configured,dirty,verified,iir_programmed;
static unsigned shadow_bandwidth=80,target_gain=RADAR_GAIN_NORM_TARGET_GAIN_DEFAULT;
static uint32_t epoch_base,zc_cursor;
static bool zc_accurate;
static bool first_capture_trace=true,pm_begin_logged,pm_acquired_logged,pm_release_logged;
static unsigned phase_lines;
static void phase(const char*name)
{
 if(phase_lines<96){pr_info("OMF366 phase=%s\n",name);phase_lines++;}
}
static struct f332_hw_profile f315_profile;
static atomic64_t f315_map_failures=ATOMIC64_INIT(0),f315_mmio_writes=ATOMIC64_INIT(0),f315_mmio_write_refusals=ATOMIC64_INIT(0);
#include "f332_setup.inc"
extern u_int8_t get_bootcfg_scancnt(void);
static int clock_now(int32_t*seconds,int32_t*microseconds)
{
 struct timespec64 now;ktime_get_real_ts64(&now);
 if(now.tv_sec<0||now.tv_sec>0x7fffffff)return -ERANGE;
 *seconds=(int32_t)now.tv_sec;*microseconds=(int32_t)(now.tv_nsec/1000);return 0;
}
static int clear_point(bool trace)
{
 int rc=0;
 /* OEM 3920..39c4. No CNT_L write, no SRAM clear in iterative consume. */
 if(trace)phase("clear_pt.bb.before");
 qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);
 if(trace)phase("clear_pt.bb.acquired");
 rc|=f315_write_reg(F315_REG_CLEAR_INT,2);
 rc|=f315_write_reg(F315_REG_CUR_CHMEM,0);
 rc|=f315_write_reg(F315_REG_PTR_H,0);
 rc|=f315_write_reg(F315_REG_PTR_L,0);
 rc|=f315_write_reg(F315_REG_NEW_START,0);
 zc_accurate=true;
 rc|=f315_write_reg(F315_REG_NEW_CURRENT,0);
 zc_cursor=0;wmb();qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);if(trace)phase("clear_pt.bb.released");
 return rc?-EIO:0;
}
static int verify_setup(bool check_iir)
{
 int ok;
 qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);
 ok=f315_read_reg(F315_REG_TH1)==TH1_DEFAULT&&f315_read_reg(F315_REG_TH2)==TH2_DEFAULT&&
  f315_read_reg(F315_REG_DOWNSAMPLE)==DSAMPLE_DEFAULT&&f315_read_reg(F315_REG_NUMDELAY)==NDELAY_DEFAULT&&
  f315_read_reg(F315_REG_TAGMODE)==(unsigned)f315_profile.tag_enabled&&
  f315_read_reg(F315_REG_ZWIN)==f315_profile.win_size&&f315_read_reg(F315_REG_MAXWR)==f315_profile.win_per_pulse&&
  f315_read_reg(F315_REG_MINWIDTH)==f315_profile.hw_width_min&&f315_read_reg(F315_REG_MAXWIDTH)==f315_profile.hw_width_max&&
  f315_read_reg(F315_REG_NEW_MODE)==QT_RADAR_NEW_MODE_DEFAULT&&
  f315_read_reg(F315_REG_GAIN_TARGET)==target_gain;
 if(ok&&check_iir)ok=f315_read_reg(F315_REG_IIR_A1)==(shadow_bandwidth==80?RADAR_IIR_A1_80:RADAR_IIR_A1_40)&&
  f315_read_reg(F315_REG_IIR_B3)==(shadow_bandwidth==80?RADAR_IIR_B3_80:RADAR_IIR_B3_40);
 qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);return ok?0:-EIO;
}
static unsigned native_gain(uint32_t revision,unsigned scancnt)
{return !scancnt||(revision&0xf0U)==0x40U?0x23U:0x19U;}
static int reset_counter_sequence(int32_t*sec,int32_t*usec)
{
 int rc;phase("counter.bb.before");qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);phase("counter.bb.acquired");
 phase("counter.write1.before");rc=f315_write_reg(F315_REG_CNT_L,0);wmb();phase("counter.write1.after");
 if(!rc){phase("counter.write2.before");rc=f315_write_reg(F315_REG_CNT_L,0);phase("counter.write2.after");}wmb();
 qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);phase("counter.bb.released");if(rc)return rc;
 return clock_now(sec,usec);
}
static int native_memory_clear(void)
{
 unsigned i;int rc=0;
 /* OEM4d42..4d92: high/low interleaved FIFO FIRST, then valid ZC only. */
 phase("memory.bb.before");qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);phase("memory.bb.acquired");phase("clear_fifo.before");
 for(i=0;i<256&&!rc;i++){
  rc=f315_clear_capture_word(0x1400U+4*i);
  if(!rc)rc=f315_clear_capture_word(0x1000U+4*i);
 }
 phase("clear_fifo.after");phase("clear_zc.before");
 for(i=0;i<0xe00U&&!rc;i+=4)rc=f315_clear_capture_word(i);
 phase("clear_zc.after");wmb();qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);phase("memory.bb.released");return rc;
}
static int native_configuration(void __iomem*chip)
{
 uint32_t timer;int rc=0;
 phase("configuration.bb.before");qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);phase("configuration.bb.acquired");
#define WRITE_NATIVE(reg,val) do{if(!rc)rc=f315_write_reg((reg),(val));}while(0)
 WRITE_NATIVE(F315_REG_TH1,TH1_DEFAULT);WRITE_NATIVE(F315_REG_TH2,TH2_DEFAULT);
 WRITE_NATIVE(F315_REG_DOWNSAMPLE,5);WRITE_NATIVE(F315_REG_NUMDELAY,5);WRITE_NATIVE(F315_REG_TAGMODE,f315_profile.tag_enabled);
 WRITE_NATIVE(F315_REG_GAIN_NORM,0x82);
 if(!rc)target_gain=native_gain(readl(chip),get_bootcfg_scancnt());
 WRITE_NATIVE(F315_REG_GAIN_TARGET,target_gain);WRITE_NATIVE(F315_REG_IIR_HPF_ORDER,10);
 WRITE_NATIVE(F315_REG_IIR_LPF_SHIFT,0);WRITE_NATIVE(F315_REG_INTR_EN,0);WRITE_NATIVE(F315_REG_NUM_PULSES,255);WRITE_NATIVE(F315_REG_CLEAR_INT,2);
 timer=f315_read_reg(F315_REG_TIMER_REC_EN)|TIMER_REC_EN_ADDR_MASK;WRITE_NATIVE(F315_REG_TIMER_REC_EN,timer);
 WRITE_NATIVE(F315_REG_AGC_IN_PROG,0);WRITE_NATIVE(F315_REG_RX_IN_PROG,1);WRITE_NATIVE(F315_REG_SPRAM_IN_PROG,0);WRITE_NATIVE(F315_REG_NEW_MODE,1);WRITE_NATIVE(F315_REG_DC_LUT,0);
 WRITE_NATIVE(F315_REG_RX_EXT_AFTER,255);WRITE_NATIVE(F315_REG_RX_EXT_BEFORE,255);
 WRITE_NATIVE(F315_REG_ZWIN,f315_profile.win_size);WRITE_NATIVE(F315_REG_MAXWR,f315_profile.win_per_pulse);WRITE_NATIVE(F315_REG_TX_EXT,0x140);
#undef WRITE_NATIVE
 wmb();qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);phase("configuration.bb.released");return rc;
}
static int native_bootstrap(void)
{
 void __iomem*chip;int32_t sec,usec;int rc;
 first_capture_trace=true;pm_begin_logged=pm_acquired_logged=pm_release_logged=false;phase("bootstrap.begin");
 phase("chip.map.before");chip=ioremap(0xe0000014U,4);if(!chip)return -ENOMEM;phase("chip.map.after");
 rc=native_configuration(chip);iounmap(chip);if(rc)return rc;
 rc=clear_point(true);if(rc)return rc;
 rc=native_memory_clear();if(rc)return rc;
 /* Full reset helper4cf8 and outer radar_start each emit one pair. */
 phase("bootstrap.clear_helper_reset");rc=reset_counter_sequence(&sec,&usec);if(rc)return rc;
 phase("bootstrap.outer_reset");rc=reset_counter_sequence(&sec,&usec);if(rc)return rc;
 epoch_base=(uint32_t)sec*10000000U+(uint32_t)usec*10U;
 qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);
 rc=f315_write_reg(F315_REG_RX_IN_PROG,1);
 if(!rc)rc=f315_write_reg(F315_REG_MINWIDTH,f315_profile.hw_width_min);
 if(!rc)rc=f315_write_reg(F315_REG_MAXWIDTH,f315_profile.hw_width_max);
 wmb();qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);
 if(!rc){f315_configured=true;iir_programmed=false;zc_cursor=0;zc_accurate=true;}
 phase("bootstrap.end");return rc;
}
int f332_hw_open(uint32_t gen,bool allowed,uint32_t bandwidth,const struct f332_hw_profile*p,bool bootstrap,uint32_t*base)
{
 int32_t sec,usec;int rc;
 if(!allowed||!p||!base||!f332_provider_current(gen)||!f315_bb_ready())return -EPERM;
 if(bandwidth!=20&&bandwidth!=40&&bandwidth!=80)return -EINVAL;
 if(p->win_size!=120||p->win_per_pulse!=28||p->hw_width_min!=4||p->hw_width_max!=360)return -EINVAL;
 shadow_enable=true;
 if(!f315_maps_ready()){
  rc=f315_map_windows();if(rc){f315_unmap_windows();return rc;}
 }
 if(bootstrap||!f315_configured){
  shadow_bandwidth=bandwidth;f315_profile=*p;dirty=true;verified=false;
  rc=native_bootstrap();if(rc)return rc;
  rc=verify_setup(false);if(rc)return rc;
  verified=true;
 }else{
  shadow_bandwidth=bandwidth;
  phase("iir.bb.before");qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);phase("iir.before");rc=f315_apply_iir();wmb();phase("iir.after");qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);phase("iir.bb.released");if(rc)return rc;
  iir_programmed=true;
  rc=clear_point(true);if(rc)return rc;
  rc=reset_counter_sequence(&sec,&usec);if(rc){verified=false;return rc;}
  epoch_base=(uint32_t)sec*10000000U+(uint32_t)usec*10U;
  rc=verify_setup(true);if(rc){verified=false;return rc;}
 }
 if(!f332_provider_current(gen))return -ESTALE;
 *base=epoch_base;return 0;
}
static int read_word(void*unused,enum f333_space space,unsigned index,f333_u32*value)
{
 unsigned offset;(void)unused;
 if(!value)return 0;
 if(space==F333_BANK_HIGH&&index<256)offset=0x1400+index*4;
 else if(space==F333_BANK_LOW&&index<256)offset=0x1000+index*4;
 else if(space==F333_ZC_RAM&&index<896)offset=index*4;
 else return 0;
 return f315_capture_word(offset,value);
}
int f332_hw_capture(uint32_t gen,struct f332_capture*c,const struct f332_ocac_state*ocac_state)
{
 struct f333_snapshot raw_snapshot,zc_snapshot;int rr,zr,rc;bool tracing=first_capture_trace;
 if(!c||!ocac_state||!verified||!shadow_enable||!f315_bb_ready()||!f332_provider_current(gen))return -EAGAIN;
 memset(&raw_snapshot,0,sizeof(raw_snapshot));memset(&zc_snapshot,0,sizeof(zc_snapshot));
 c->raw_valid=false;c->zc_valid=false;
 raw_snapshot.tag_enabled=f315_profile.tag_enabled;raw_snapshot.win_per_pulse=f315_profile.win_per_pulse;
 raw_snapshot.software_zc_accurate=zc_accurate;raw_snapshot.zc_start_bytes=zc_cursor;
 raw_snapshot.ocac_filter=ocac_state->filter;raw_snapshot.ocac_mask=ocac_state->mask;
 if(tracing)phase("capture.raw.bb.before");
 qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);
 if(tracing)phase("capture.raw.bb.acquired");
 raw_snapshot.start=f315_read_reg(F315_REG_NEW_START);raw_snapshot.current_ptr=f315_read_reg(F315_REG_NEW_CURRENT);
 rr=f333_capture_raw(&raw_snapshot,read_word,0,c->raw,256,&c->raw_meta);
 qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);if(tracing)phase("capture.raw.bb.released");
 if(rr!=F333_OK||!c->raw_meta.complete)return -EIO;
 zc_snapshot=raw_snapshot;
 if(tracing)phase("capture.zc.bb.before");
 qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);
 if(tracing)phase("capture.zc.bb.acquired");
 zc_snapshot.start=f315_read_reg(F315_REG_NEW_START);zc_snapshot.current_ptr=f315_read_reg(F315_REG_NEW_CURRENT);
 zr=f333_capture_zc(&zc_snapshot,read_word,0,c->zc.samples,49,&c->zc_meta);
 qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);if(tracing)phase("capture.zc.bb.released");
 if(zr!=F333_OK&&zr!=F333_ZC_NOT_ACCURATE)return -EIO;
 c->zc.accurate=c->zc_meta.source_accurate;
 c->raw_valid=true;c->zc_valid=(zr==F333_OK&&c->zc_meta.complete)||zr==F333_ZC_NOT_ACCURATE;
 zc_cursor=c->zc_meta.next_cursor;
 if(!f332_provider_current(gen))return -ESTALE;
 rc=clear_point(tracing);if(rc){c->raw_valid=c->zc_valid=false;return rc;}
 first_capture_trace=false;
 return 0;
}
int f332_hw_reset(void*unused,uint32_t gen,uint32_t request,int32_t*sec,int32_t*usec)
{
 int rc=0;(void)unused;
 if(!f332_provider_current(gen))return F332_BACKEND_CANCELLED;
 if(!request||!sec||!usec||!verified||!shadow_enable||!f315_bb_ready())return -EPERM;
 qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);
 rc=f315_write_reg(F315_REG_CNT_L,0);wmb();
 if(!rc)rc=f315_write_reg(F315_REG_CNT_L,0);
 /* OEM makes no zero readback assertion: the counter/producer may advance.
  * Completion here proves two writes emitted, not hardware acknowledgement. */
 wmb();
 qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);
 if(rc){verified=false;return rc;}
 rc=clock_now(sec,usec);if(rc){verified=false;return rc;}
 epoch_base=(uint32_t)*sec*10000000U+(uint32_t)*usec*10U;return 0;
}
int f332_hw_point(uint32_t*point)
{
 if(!point||!verified||!shadow_enable||!f315_bb_ready())return -EAGAIN;
 qtn_bb_mutex_enter(QTN_LHOST_SOC_CPU);*point=f315_read_reg(F315_REG_NEW_CURRENT);qtn_bb_mutex_leave(QTN_LHOST_SOC_CPU);return 0;
}
bool f332_hw_ready(void){return verified&&iir_programmed&&shadow_enable&&f315_maps_ready()&&f315_bb_ready();}
bool f332_hw_dirty(void){return dirty;}
bool f332_hw_duty_acquire(uint32_t gen)
{
 bool acquired;
 if(!shadow_enable||!f315_bb_ready()||!f332_provider_current(gen))return false;
 if(!pm_begin_logged){phase("pm.before");pm_begin_logged=true;}
 acquired=qtn_pm_duty_try_lock(QTN_LHOST_SOC_CPU)!=0;
 if(acquired&&!pm_acquired_logged){phase("pm.acquired");pm_acquired_logged=true;}
 return acquired;
}
void f332_hw_duty_release(void){qtn_pm_duty_unlock(QTN_LHOST_SOC_CPU);if(!pm_release_logged){phase("pm.released");pm_release_logged=true;}}
void f332_hw_cleanup_unarmed(void){if(!dirty)f315_unmap_windows();}
void f332_hw_retire(void){shadow_enable=false;verified=false;}
