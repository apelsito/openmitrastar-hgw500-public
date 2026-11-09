/* Compile the exact qdrv readiness/OCAC helper with controlled kernel APIs. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef uint8_t u8;
typedef struct { unsigned held; } spinlock_t;
#define DEFINE_SPINLOCK(name) spinlock_t name
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define QTN_PM_CURRENT_LEVEL 0
#define BOARD_PM_LEVEL_DUTY 2
#define IEEE80211_F_SCAN 1
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel *)(uintptr_t)1)
#define QTN_OCAC_ON_DATA_CHAN 0
#define QTN_OCAC_ON_OFF_CHAN 1
#define QTN_OCAC_TSF_LOG_DEPTH 4
#define msecs_to_jiffies(x) (x)
#define time_after_eq(a,b) ((int32_t)((uint32_t)(a)-(uint32_t)(b))>=0)
static unsigned lock_depth;
#define spin_lock_irqsave(p, flags) do { assert(!(p)->held);(p)->held=1;lock_depth++;(flags)=0; } while(0)
#define spin_unlock_irqrestore(p, flags) do { (void)(flags);assert((p)->held);(p)->held=0;lock_depth--; } while(0)
#define spin_lock(p) do { assert(!(p)->held);(p)->held=1;lock_depth++; } while(0)
#define spin_unlock(p) do { assert((p)->held);(p)->held=0;lock_depth--; } while(0)
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; bool queued; unsigned long due; void (*fn)(struct work_struct *); };
static unsigned long jiffies;
static unsigned scheduled, cancelled, joined, enables, tx_stops, cac_starts, warnings, newchans;
#define INIT_DELAYED_WORK(w,f) do { (w)->queued=false;(w)->fn=(f); } while(0)
static bool schedule_delayed_work(struct delayed_work *work,unsigned long delay)
{
 scheduled++;
 if(work->queued)return false;
 work->queued=true;work->due=jiffies+delay;return true;
}
static void cancel_delayed_work(struct delayed_work *work){cancelled++;work->queued=false;}
static void cancel_delayed_work_sync(struct delayed_work *work){assert(!lock_depth);joined++;work->queued=false;}
#define pr_warn_ratelimited(...) do { warnings++; } while(0)
struct ieee80211_channel { uint8_t ic_ieee; bool dfs; };
struct ieee80211_ocac_tsflog { uint32_t tsf_log[QTN_OCAC_TSF_LOG_DEPTH][2];unsigned log_index; };
struct ieee80211com {
 unsigned ic_radar_bw,ic_flags,ic_pm_state[1];
 struct ieee80211_channel *ic_curchan,*ic_bsschan;
 struct {
  struct ieee80211_channel *ocac_chan;
  unsigned ocac_accum_cac_time_ms;
  struct {unsigned tasklet_data_chan,tasklet_off_chan;} ocac_counts;
  struct ieee80211_ocac_tsflog ocac_tsflog;
 } ic_ocac;
};
struct qtn_ocac_info { unsigned chan_status,actual_dwell_time;uint32_t tsf_log[2]; };
struct radar_ocac_info_s {spinlock_t lock;u8 ocac_scan_chan;struct {u8 ocac_status;u32 fifo_pt;} ocac_radar_pts[10];u8 array_ps;u32 canary;};
static struct { bool enabled;struct ieee80211com *ic; } qdrv_radar_cb;
static bool qdrv_radar_configured,detector_ready,synchronous_enable;
static u32 detector_generation;
static u8 detector_channel,scan_channel;
static u32 radar_ready_generation(void){assert(!lock_depth);return detector_ready?detector_generation:0;}
static bool radar_get_status(void){assert(!lock_depth);return detector_ready;}
static void sys_enable_rdetection(void){assert(!lock_depth);enables++;if(synchronous_enable)detector_ready=true;}
static void sys_disable_xmit(void){assert(!lock_depth);tx_stops++;}
static int radar_set_scan_context(uint8_t channel){assert(!lock_depth);if(channel!=scan_channel){scan_channel=channel;detector_ready=false;detector_generation++;}return 0;}
static int radar_set_chan(uint8_t channel){assert(!lock_depth);if(channel!=detector_channel){detector_channel=channel;detector_ready=false;detector_generation++;}return 0;}
static bool qdrv_radar_is_rdetection_required(const struct ieee80211_channel *channel){return channel&&channel!=IEEE80211_CHAN_ANYC&&channel->dfs;}
static void qdrv_radar_on_newchan(void);
#include "../qdrv/qdrv_f332_ready.inc"
static void qdrv_radar_on_newchan(void){newchans++;if(qdrv_f332_begin_cac(qdrv_radar_cb.ic->ic_curchan))cac_starts++;}
static struct ieee80211_channel ch52={52,true},ch56={56,true},ch36={36,false};
static struct ieee80211com ic;
static unsigned groups;
static void reset(void)
{
 assert(!lock_depth);memset(&ic,0,sizeof(ic));
 ic.ic_radar_bw=80;ic.ic_curchan=&ch52;ic.ic_bsschan=&ch52;ic.ic_ocac.ocac_chan=&ch52;
 qdrv_radar_cb.ic=&ic;qdrv_radar_cb.enabled=true;qdrv_radar_configured=true;
 scheduled=cancelled=joined=enables=tx_stops=cac_starts=warnings=newchans=0;
 jiffies=0;detector_ready=false;synchronous_enable=false;detector_generation=7;detector_channel=52;scan_channel=0;
 qdrv_f332_ready_init();
}
static void tick(unsigned long now)
{
 jiffies=now;
 if(qdrv_f332_ready_work.queued&&time_after_eq(now,qdrv_f332_ready_work.due)){
  qdrv_f332_ready_work.queued=false;qdrv_f332_ready_work.fn(&qdrv_f332_ready_work.work);
 }
}
static void test_cac_wait_and_start(void)
{
 unsigned long deadline,due;reset();
 assert(!qdrv_f332_begin_cac(&ch52));assert(!cac_starts&&tx_stops==1&&enables==1);
 deadline=qdrv_f332.deadline;due=qdrv_f332_ready_work.due;
 jiffies=10;assert(!qdrv_f332_begin_cac(&ch52));assert(qdrv_f332.deadline==deadline&&qdrv_f332_ready_work.due==due);
 tick(50);assert(newchans==1&&!cac_starts&&qdrv_f332_ready_work.queued);
 detector_ready=true;tick(100);assert(cac_starts==1&&!qdrv_f332_ready_work.queued);
 assert(qdrv_f332_complete_cac(&ch52));detector_generation++;
 assert(!qdrv_f332_complete_cac(&ch52));groups++;
}
static void test_ready_sync_and_cac_generation(void)
{
 reset();synchronous_enable=true;assert(qdrv_f332_begin_cac(&ch52));
 assert(qdrv_f332_complete_cac(&ch52));detector_ready=false;assert(!qdrv_f332_complete_cac(&ch52));
 detector_ready=true;ic.ic_curchan=&ch56;assert(!qdrv_f332_complete_cac(&ch52));groups++;
}
static void test_retry_is_bounded(void)
{
 unsigned count;reset();assert(!qdrv_f332_begin_cac(&ch52));
 tick(5000);assert(qdrv_f332.timed_out&&!qdrv_f332_ready_work.queued&&warnings==1);
 count=enables;
 for(unsigned i=0;i<50;i++){jiffies++;assert(!qdrv_f332_begin_cac(&ch52));}
 assert(enables==count&&warnings==1&&!qdrv_f332_ready_work.queued);
 detector_ready=true;assert(qdrv_f332_begin_cac(&ch52));
 detector_ready=false;jiffies=7000;assert(!qdrv_f332_begin_cac(&ch52));assert(qdrv_f332.deadline==12000);groups++;
}
static void test_context_cancel_and_teardown(void)
{
 reset();assert(!qdrv_f332_begin_cac(&ch52));ic.ic_curchan=&ch56;
 tick(50);assert(!cac_starts&&!qdrv_f332_ready_work.queued);
 qdrv_f332_cancel_wait();ic.ic_curchan=&ch52;assert(!qdrv_f332_begin_cac(&ch52));
 qdrv_f332_ready_join();assert(joined==1&&qdrv_f332_ready_stopping()&&!qdrv_f332_ready_work.queued);
 detector_ready=true;assert(!qdrv_f332_begin_cac(&ch52));assert(!qdrv_f332_complete_cac(&ch52));
 qdrv_f332_retry(&qdrv_f332_ready_work.work);assert(!cac_starts);
 qdrv_f332_ready_init();assert(qdrv_f332_begin_cac(&ch52));groups++;
}
static void test_ocac_start_and_end_must_be_ready(void)
{
 struct radar_ocac_info_s radar={0};struct qtn_ocac_info info={QTN_OCAC_ON_OFF_CHAN,100,{1,2}};bool overflow;
 reset();radar.ocac_scan_chan=52;radar.canary=0x12345678;
 qdrv_f332_ocac_unready();info.chan_status=QTN_OCAC_ON_DATA_CHAN;
 assert(!qdrv_f332_ocac_record(&ic,&info,&radar,52,7,1,&overflow));assert(!ic.ic_ocac.ocac_accum_cac_time_ms&&!radar.array_ps);
 info.chan_status=QTN_OCAC_ON_OFF_CHAN;assert(qdrv_f332_ocac_record(&ic,&info,&radar,52,7,2,&overflow));
 info.chan_status=QTN_OCAC_ON_DATA_CHAN;assert(qdrv_f332_ocac_record(&ic,&info,&radar,52,7,3,&overflow));
 assert(ic.ic_ocac.ocac_accum_cac_time_ms==100&&radar.array_ps==2&&ic.ic_ocac.ocac_counts.tasklet_data_chan==1);
 info.chan_status=QTN_OCAC_ON_OFF_CHAN;assert(qdrv_f332_ocac_record(&ic,&info,&radar,52,7,4,&overflow));
 qdrv_f332_ocac_unready();info.chan_status=QTN_OCAC_ON_DATA_CHAN;
 assert(!qdrv_f332_ocac_record(&ic,&info,&radar,52,7,5,&overflow));assert(ic.ic_ocac.ocac_accum_cac_time_ms==100);
 assert(radar.canary==0x12345678);groups++;
}
static void test_ocac_epoch_scan_and_overflow(void)
{
 struct radar_ocac_info_s radar={0};struct qtn_ocac_info info={QTN_OCAC_ON_OFF_CHAN,100,{1,2}};bool overflow;
 reset();radar.ocac_scan_chan=52;radar.canary=0x5a5a5a5a;
 assert(qdrv_f332_ocac_record(&ic,&info,&radar,52,7,1,&overflow));
 info.chan_status=QTN_OCAC_ON_DATA_CHAN;
 assert(!qdrv_f332_ocac_record(&ic,&info,&radar,52,8,2,&overflow));assert(!ic.ic_ocac.ocac_accum_cac_time_ms);
 radar.ocac_scan_chan=56;info.chan_status=QTN_OCAC_ON_OFF_CHAN;
 assert(qdrv_f332_ocac_record(&ic,&info,&radar,56,8,3,&overflow));
 info.chan_status=QTN_OCAC_ON_DATA_CHAN;
 assert(qdrv_f332_ocac_record(&ic,&info,&radar,56,8,4,&overflow));assert(ic.ic_ocac.ocac_accum_cac_time_ms==100);
 radar.array_ps=10;info.chan_status=QTN_OCAC_ON_OFF_CHAN;
 assert(!qdrv_f332_ocac_record(&ic,&info,&radar,56,8,5,&overflow));assert(overflow&&radar.array_ps==10);
 assert(radar.canary==0x5a5a5a5a&&!ic.ic_ocac.ocac_accum_cac_time_ms&&!qdrv_f332.begin_valid);groups++;
}
static void test_ocac_retry_never_replays_period(void)
{
 reset();ic.ic_bsschan=&ch36;ic.ic_curchan=&ch36;scan_channel=52;
 assert(!qdrv_f332_wait_ready(QDRV_F332_OCAC,52,80));tick(50);
 assert(!ic.ic_ocac.ocac_accum_cac_time_ms&&!ic.ic_ocac.ocac_counts.tasklet_data_chan);
 detector_ready=true;tick(100);assert(!qdrv_f332_ready_work.queued&&!ic.ic_ocac.ocac_accum_cac_time_ms);groups++;
}
int main(void)
{
 test_cac_wait_and_start();test_ready_sync_and_cac_generation();test_retry_is_bounded();test_context_cancel_and_teardown();
 test_ocac_start_and_end_must_be_ready();test_ocac_epoch_scan_and_overflow();test_ocac_retry_never_replays_period();
 printf("F332_QDRV_READY_PASS groups=%u hardware=0\n",groups);return 0;
}
