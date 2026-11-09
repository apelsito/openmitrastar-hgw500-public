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
static unsigned raw_off, raw_on, stop_cacs, channel_required;
static int raw_on_rc, raw_off_rc;
static bool hardware_tx, fake_radar, inject_loss, inject_stop;
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
#define pr_err_ratelimited(...) do { warnings++; } while(0)
#define IEEE80211_CHAN_DFS_CAC_DONE 2U
#define IEEE80211_CHAN_DFS_CAC_IN_PROGRESS 4U
#define IEEE80211_CHAN_DFS_OCAC_DONE 8U
#define IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_CAC_REQUIRED 8
#define IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_RADAR_DETECTED 4
struct ieee80211_channel { uint8_t ic_ieee; bool dfs; unsigned ic_flags; int availability; bool radar; };
struct ieee80211_ocac_tsflog { uint32_t tsf_log[QTN_OCAC_TSF_LOG_DEPTH][2];unsigned log_index; };
struct ieee80211com {
 unsigned ic_radar_bw,ic_flags,ic_pm_state[1];
 struct {bool sta_dfs_strict_mode;} sta_dfs_info;
 void (*ic_mark_channel_dfs_cac_status)(struct ieee80211com*,struct ieee80211_channel*,unsigned,bool);
 void (*ic_mark_channel_availability_status)(struct ieee80211com*,struct ieee80211_channel*,int);
 int (*ic_get_chan_availability_status_by_chan_num)(struct ieee80211com*,struct ieee80211_channel*);
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
static struct { bool enabled,xmit_stopped;struct ieee80211com *ic;struct ieee80211_channel*cac_chan; } qdrv_radar_cb;
static bool qdrv_radar_sta_dfs;
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
static void qdrv_f338_availability(u32 generation,u32 reason);
static int qdrv_is_dfs_master(void){return 1;}
/* Preserve the OEM macro's implicit local ic and availability callback. */
#define ieee80211_is_chan_radar_detected(channel_to_check) \
 (IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_RADAR_DETECTED == ic->ic_get_chan_availability_status_by_chan_num(ic, (channel_to_check)))
static int get_availability(struct ieee80211com*c,struct ieee80211_channel*ch){(void)c;return ch->availability;}
static void stop_cac(void){assert(!lock_depth);stop_cacs++;qdrv_radar_cb.cac_chan=NULL;}
static int sys_raw_disable_xmit(void){assert(!lock_depth);raw_off++;if(!raw_off_rc)hardware_tx=false;return raw_off_rc;}
static int sys_raw_enable_xmit(void);
#include "../qdrv/qdrv_f332_ready.inc"
static bool qdrv_f367_tx_allowed(void){return true;}
#include "../qdrv/qdrv_f338_availability.inc"
static int sys_raw_enable_xmit(void){assert(!lock_depth);raw_on++;if(inject_loss){inject_loss=false;detector_ready=false;qdrv_f338_availability(detector_generation,1);}if(inject_stop){inject_stop=false;qdrv_f332.stopping=true;}hardware_tx=true;return raw_on_rc;}
static void qdrv_radar_on_newchan(void){newchans++;if(qdrv_f332_begin_cac(qdrv_radar_cb.ic->ic_curchan)){cac_starts++;qdrv_radar_cb.cac_chan=qdrv_radar_cb.ic->ic_curchan;}}
static struct ieee80211_channel ch52={.ic_ieee=52,.dfs=true},ch56={.ic_ieee=56,.dfs=true},ch36={.ic_ieee=36,.dfs=false};
static struct ieee80211com ic;
static unsigned groups;
static void reset(void)
{
 assert(!lock_depth);memset(&ic,0,sizeof(ic));
 ic.ic_radar_bw=80;ic.ic_curchan=&ch52;ic.ic_bsschan=&ch52;ic.ic_ocac.ocac_chan=&ch52;
 qdrv_radar_cb.ic=&ic;qdrv_radar_cb.enabled=true;qdrv_radar_configured=true;
 ic.ic_get_chan_availability_status_by_chan_num=get_availability;
 scheduled=cancelled=joined=enables=tx_stops=cac_starts=warnings=newchans=0;
 jiffies=0;detector_ready=false;synchronous_enable=false;detector_generation=7;detector_channel=52;scan_channel=0;
 qdrv_f332_ready_init();qdrv_f338_health_init();
 qdrv_radar_cb.xmit_stopped=false;qdrv_radar_cb.cac_chan=NULL;raw_on=raw_off=stop_cacs=channel_required=0;raw_on_rc=raw_off_rc=0;hardware_tx=true;fake_radar=false;inject_loss=inject_stop=false;
 ch52.ic_flags=ch56.ic_flags=ch36.ic_flags=0;ch52.radar=ch56.radar=ch36.radar=false;
 ch52.availability=ch56.availability=ch36.availability=0;
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
 qdrv_f332_ready_init();qdrv_f338_health_init();
 qdrv_radar_cb.xmit_stopped=false;qdrv_radar_cb.cac_chan=NULL;raw_on=raw_off=stop_cacs=channel_required=0;raw_on_rc=raw_off_rc=0;hardware_tx=true;fake_radar=false;inject_loss=inject_stop=false;
 ch52.ic_flags=ch56.ic_flags=ch36.ic_flags=0;ch52.radar=ch56.radar=ch36.radar=false;assert(qdrv_f332_begin_cac(&ch52));groups++;
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
static void mark_cac(struct ieee80211com*c,struct ieee80211_channel*ch,unsigned flag,bool yes)
{(void)c;assert(!lock_depth);if(yes)ch->ic_flags|=flag;else ch->ic_flags&=~flag;}
static void mark_availability(struct ieee80211com*c,struct ieee80211_channel*ch,int status)
{(void)c;assert(!lock_depth);channel_required++;ch->availability=status;}
static void service(void)
{
 reset();ic.ic_mark_channel_dfs_cac_status=mark_cac;ic.ic_mark_channel_availability_status=mark_availability;
 ch52.ic_flags=IEEE80211_CHAN_DFS_CAC_DONE|IEEE80211_CHAN_DFS_OCAC_DONE;
 detector_ready=true;
}
static void test_service_loss_and_duplicate(void)
{
 unsigned long deadline;service();ic.ic_ocac.ocac_accum_cac_time_ms=500;
 qdrv_f332.cac_generation=7;qdrv_f332.begin_valid=true;
 detector_ready=false;qdrv_f338_availability(7,QDRV_F338_SERVICE_CLOSED);
 assert(raw_off==1&&!hardware_tx&&qdrv_radar_cb.xmit_stopped);
 assert(qdrv_f338_needs_cac()&&!qdrv_f332.cac_generation&&!qdrv_f332.begin_valid);
 assert(!ic.ic_ocac.ocac_accum_cac_time_ms&&!ch52.ic_flags);
 assert(ch52.availability==IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_CAC_REQUIRED);
 assert(!fake_radar&&qdrv_f332.pending);deadline=qdrv_f332.deadline;
 jiffies=100;qdrv_f338_availability(7,QDRV_F338_SERVICE_TIMEOUT);
 assert(raw_off==1&&qdrv_f332.deadline==deadline);groups++;
}
static void test_loss_preserves_real_nop(void)
{
 service();ch52.radar=true;ch52.availability=IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_RADAR_DETECTED;
 detector_ready=false;qdrv_f338_availability(7,QDRV_F338_HARDWARE_FAULT);
 assert(ch52.radar&&ch52.availability==IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_RADAR_DETECTED);
 assert(!channel_required&&!fake_radar&&!newchans);
 detector_ready=true;detector_generation=8;qdrv_f338_availability(8,QDRV_F338_SERVICE_READY);
 assert(!cac_starts&&!qdrv_f338_enable_tx());
 qdrv_f332.cac_generation=8;qdrv_f332.cac_channel=52;
 assert(!qdrv_f338_accept_cac(&ch52)&&ch52.radar);groups++;
}
static void test_loss_overtakes_tx_enable(void)
{
 service();qdrv_radar_cb.xmit_stopped=true;hardware_tx=false;inject_loss=true;
 assert(!qdrv_f338_enable_tx());
 assert(raw_on==1&&raw_off==2&&!hardware_tx&&qdrv_radar_cb.xmit_stopped);
 assert(qdrv_f338_needs_cac());groups++;
}
static void test_stop_overtakes_tx_enable(void)
{
 service();qdrv_radar_cb.xmit_stopped=true;inject_stop=true;
 assert(!qdrv_f338_enable_tx());assert(raw_on==1&&raw_off==1&&!hardware_tx);groups++;
}
static void test_late_service_ready_requires_full_cac(void)
{
 unsigned starts,stops;service();detector_ready=false;qdrv_f338_availability(7,QDRV_F338_SERVICE_PROTOCOL);
 tick(5000);assert(qdrv_f332.timed_out&&!qdrv_f332.pending);
 detector_generation=8;detector_ready=true;jiffies=10000;
 qdrv_f338_availability(7,QDRV_F338_SERVICE_READY);assert(!cac_starts);
 qdrv_f338_availability(8,QDRV_F338_SERVICE_READY);
 assert(cac_starts==1&&qdrv_f332.cac_generation==8&&qdrv_f338_needs_cac());
 assert(!qdrv_f338_enable_tx()&&!hardware_tx);
 starts=cac_starts;stops=stop_cacs;
 qdrv_f338_availability(8,QDRV_F338_SERVICE_READY);assert(cac_starts==starts&&stop_cacs==stops);
 assert(qdrv_f338_accept_cac(&ch52));assert(!qdrv_f338_needs_cac());
 assert(qdrv_f338_enable_tx()&&hardware_tx);
 qdrv_f338_availability(7,QDRV_F338_SERVICE_CLOSED);assert(hardware_tx&&!qdrv_f338_needs_cac());
 qdrv_f338_availability(6,QDRV_F338_SERVICE_TIMEOUT);assert(hardware_tx&&!qdrv_f338_needs_cac());groups++;
}
static void test_initial_ready_after_timeout(void)
{
 reset();assert(!qdrv_f332_begin_cac(&ch52));tick(5000);assert(qdrv_f332.timed_out);
 detector_ready=true;qdrv_f338_availability(7,QDRV_F338_SERVICE_READY);
 assert(cac_starts==1&&!qdrv_f332.timed_out);groups++;
}
static void test_loss_invalidates_old_cac_and_ocac(void)
{
 struct radar_ocac_info_s radar={0};struct qtn_ocac_info info={QTN_OCAC_ON_OFF_CHAN,100,{0,0}};bool overflow;
 service();qdrv_radar_cb.cac_chan=&ch52;assert(qdrv_f332_begin_cac(&ch52));
 detector_ready=false;qdrv_f338_availability(7,QDRV_F338_SERVICE_TIMEOUT);
 assert(!qdrv_radar_cb.cac_chan&&!qdrv_f338_accept_cac(&ch52));
 service();ic.ic_curchan=ic.ic_bsschan=&ch36;scan_channel=52;radar.ocac_scan_chan=52;
 assert(qdrv_f332_ocac_record(&ic,&info,&radar,52,7,1,&overflow));
 detector_ready=false;qdrv_f338_availability(7,QDRV_F338_SERVICE_CLOSED);
 assert(!raw_off&&hardware_tx);info.chan_status=QTN_OCAC_ON_DATA_CHAN;
 assert(!qdrv_f332_ocac_record(&ic,&info,&radar,52,8,2,&overflow));assert(!ic.ic_ocac.ocac_accum_cac_time_ms);groups++;
}
static void test_unconfirmed_tx_stop_never_reopens(void)
{
 service();raw_off_rc=-5;detector_ready=false;qdrv_f338_availability(7,QDRV_F338_HARDWARE_FAULT);
 assert(qdrv_f338_health.tx_fault&&hardware_tx&&!qdrv_radar_cb.xmit_stopped);
 detector_ready=true;detector_generation=8;qdrv_f338_availability(8,QDRV_F338_SERVICE_READY);
 assert(!qdrv_f338_enable_tx()&&!raw_on&&qdrv_f338_needs_cac());groups++;
}
static void test_availability_after_teardown_is_inert(void)
{
 service();qdrv_f332_ready_join();detector_ready=false;
 qdrv_f338_availability(7,QDRV_F338_SERVICE_CLOSED);detector_ready=true;
 qdrv_f338_availability(8,QDRV_F338_SERVICE_READY);assert(!raw_off&&!raw_on&&!newchans);groups++;
}
int main(void)
{
 test_cac_wait_and_start();test_ready_sync_and_cac_generation();test_retry_is_bounded();test_context_cancel_and_teardown();
 test_ocac_start_and_end_must_be_ready();test_ocac_epoch_scan_and_overflow();test_ocac_retry_never_replays_period();
 test_service_loss_and_duplicate();test_loss_preserves_real_nop();test_loss_overtakes_tx_enable();test_stop_overtakes_tx_enable();
 test_late_service_ready_requires_full_cac();test_initial_ready_after_timeout();test_loss_invalidates_old_cac_and_ocac();
 test_unconfirmed_tx_stop_never_reopens();test_availability_after_teardown_is_inert();
 printf("F338_QDRV_READY_PASS groups=%u hardware=0\n",groups);return 0;
}
