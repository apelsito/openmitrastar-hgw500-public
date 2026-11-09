"""Pure R9 boundary annotations; calls, return values and policy stay unchanged."""
from test_f355_lifetime import extract

HEADER='''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef QDRV_F367R9_TRACE_H
#define QDRV_F367R9_TRACE_H
#include <linux/types.h>
#define F367R9_NO_RESULT (-4096)
void qdrv_f367r9_hostlink_trace_arm(unsigned int channel);
bool qdrv_f367r9_hostlink_trace_active(void);
void qdrv_f367r9_boundary(const char *stage,int result);
#endif
'''
RADAR_HELPERS=r'''/* OMF367R9_RADAR_HELPERS_BEGIN */
static atomic_t f367r9_boundary_lines=ATOMIC_INIT(0);
void qdrv_f367r9_boundary(const char *stage,int result)
{
 struct ieee80211com*ic;
 struct ieee80211_channel*chan;
 unsigned channel;
 if(!qdrv_f367r9_hostlink_trace_active()||atomic_inc_return(&f367r9_boundary_lines)>32)return;
 ic=READ_ONCE(qdrv_radar_cb.ic);
 chan=ic?READ_ONCE(ic->ic_curchan):NULL;
 channel=chan&&chan!=IEEE80211_CHAN_ANYC?READ_ONCE(chan->ic_ieee):0;
 pr_info("OMF367R9_BOUNDARY stage=%s result_valid=%u result=%d channel=%u filter_bw=%u phymode=%u radar_enabled=%u hardirq=%u softirq=%u irq_off=%u preempt=%u jiffies=%u monotonic_ns=%llu\n",
  stage,result!=F367R9_NO_RESULT,result==F367R9_NO_RESULT?0:result,channel,
  ic?READ_ONCE(ic->ic_radar_bw):0,ic?READ_ONCE(ic->ic_phymode):0,
  READ_ONCE(qdrv_radar_cb.enabled),!!in_irq(),!!in_serving_softirq(),
  !!irqs_disabled(),(unsigned)preempt_count(),(u32)jiffies,(unsigned long long)ktime_get_ns());
}
static bool f367r9_context_admit(struct ieee80211_channel *chan)
{bool rc;qdrv_f367r9_boundary("context-admit.before",F367R9_NO_RESULT);rc=qdrv_f367_context_admit(chan);qdrv_f367r9_boundary("context-admit.after",rc);return rc;}
static int f367r9_scan_context(uint8_t channel)
{int rc;qdrv_f367r9_boundary("scan-context.before",F367R9_NO_RESULT);rc=radar_set_scan_context(channel);qdrv_f367r9_boundary("scan-context.after",rc);return rc;}
static int f367r9_native_context(uint8_t channel,uint32_t bandwidth)
{int rc;qdrv_f367r9_boundary("native-context.before",F367R9_NO_RESULT);rc=radar_set_context(channel,bandwidth);qdrv_f367r9_boundary("native-context.after",rc);return rc;}
static u32 f367r9_wait_ready(unsigned kind,unsigned channel,unsigned bandwidth)
{u32 rc;qdrv_f367r9_boundary("readiness.before",F367R9_NO_RESULT);rc=qdrv_f332_wait_ready(kind,channel,bandwidth);qdrv_f367r9_boundary("readiness.after",rc);return rc;}
/* OMF367R9_RADAR_HELPERS_END */
'''
def once(text,a,b):
 if text.count(a)!=1:raise ValueError('R9 boundary anchor '+a[:90])
 return text.replace(a,b,1)
def driver_operations(text):
 original=extract(text,'qdrv_set_channel');body=original
 body=once(body,'\tic->sta_dfs_info.allow_measurement_report = false;','''	qdrv_f367r9_hostlink_trace_arm(ic->ic_curchan&&ic->ic_curchan!=IEEE80211_CHAN_ANYC?ic->ic_curchan->ic_ieee:0);
	qdrv_f367r9_boundary("set-channel.entry",F367R9_NO_RESULT);
	ic->sta_dfs_info.allow_measurement_report = false;''')
 body=once(body,'\tqdrv_hostlink_store_txpow(qw, ic->ic_curchan->ic_maxpower_normal);','''	qdrv_f367r9_boundary("store38.before",F367R9_NO_RESULT);
	{int observed_rc=qdrv_hostlink_store_txpow(qw, ic->ic_curchan->ic_maxpower_normal);
	 qdrv_f367r9_boundary("store38.after",observed_rc);}''')
 body=once(body,'\t\tqdrv_radar_before_newchan();','''		qdrv_f367r9_boundary("before-newchan.before",F367R9_NO_RESULT);
		qdrv_radar_before_newchan();
		qdrv_f367r9_boundary("before-newchan.after",F367R9_NO_RESULT);''')
 body=once(body,'\t{int rc=qdrv_hostlink_setchan(qw,freq_band,qtn_chan);','''	qdrv_f367r9_boundary("change17.before",F367R9_NO_RESULT);
	{int rc=qdrv_hostlink_setchan(qw,freq_band,qtn_chan);
	 qdrv_f367r9_boundary("change17.after",rc);''')
 body=once(body,'\tqdrv_radar_on_newchan();','''	qdrv_f367r9_boundary("on-newchan.before",F367R9_NO_RESULT);
	qdrv_radar_on_newchan();
	qdrv_f367r9_boundary("on-newchan.after",F367R9_NO_RESULT);''')
 return [(original,body),('#include "qdrv_radar.h"','#include "qdrv_radar.h"\n#include "qdrv_f367r9_trace.h"')]
def radar_operations(text):
 original=extract(text,'qdrv_radar_on_newchan');body=original
 for a,b in [('qdrv_f367_context_admit(new_chan)','f367r9_context_admit(new_chan)'),('radar_set_scan_context(0)','f367r9_scan_context(0)'),('radar_set_context(new_chan->ic_ieee,ic->ic_radar_bw)','f367r9_native_context(new_chan->ic_ieee,ic->ic_radar_bw)'),('qdrv_f332_wait_ready(QDRV_F332_SERVICE, new_chan->ic_ieee, ic->ic_radar_bw)','f367r9_wait_ready(QDRV_F332_SERVICE, new_chan->ic_ieee, ic->ic_radar_bw)')]:body=once(body,a,b)
 return [(original,body),('#include "qdrv_control.h"','#include "qdrv_control.h"\n#include "qdrv_f367r9_trace.h"\n#include <linux/atomic.h>\n#include <linux/preempt.h>'),('#include "qdrv_f367_control.inc"','#include "qdrv_f367_control.inc"\n'+RADAR_HELPERS)]
def apply(text,operations):
 if 'OMF367R9' in text or 'qdrv_f367r9_trace.h' in text:raise ValueError('R9 observation already present')
 for a,b in operations:text=once(text,a,b)
 return text
def patch_driver(text):return apply(text,driver_operations(text))
def patch_radar(text):return apply(text,radar_operations(text))
def controller_operations(text):
 result=[]
 for key,command in [('region'," \"$iwpriv\" wifi0 get_region | grep -q 'get_region:21317' || fail region-readback"),('mode'," \"$iwpriv\" wifi0 get_mode | grep -qi '11ac20' || fail mode-readback")]:
  result.append((command," printf 'OMF367R9_READ step="+key+" phase=before\\n'\n"+command+"\n printf 'OMF367R9_READ step="+key+" phase=after rc=0\\n'"))
 result.append((' context_attempts=0\n while :; do\n  f367_load_snapshot || fail context-readback', ''' context_attempts=0
 OM_F367_R9_READ_TRACE=1;export OM_F367_R9_READ_TRACE
 while :; do
  printf 'OMF367R9_READ step=snapshot phase=before iteration=%s\\n' "$context_attempts"
  f367_load_snapshot || fail context-readback
  printf 'OMF367R9_READ step=snapshot phase=after rc=0 iteration=%s\\n' "$context_attempts"'''))
 return result
def patch_controller(text):return apply(text,controller_operations(text))
def status_operations(text):
 helper='''r9_trace()
{
 [ "${OM_F367_R9_READ_TRACE:-0}" != 1 ] || printf 'OMF367R9_SNAPSHOT step=%s phase=%s\\n' "$1" "$2" >&2 || true
}
'''
 return [('value=$(cat "$kernel")',helper+'r9_trace kernel before\nvalue=$(cat "$kernel")\nr9_trace kernel after'),("grep -qx 'schema=openmitrastar.f341-provider/v1' \"$provider/status\" || exit 2","r9_trace provider-schema before\ngrep -qx 'schema=openmitrastar.f341-provider/v1' \"$provider/status\" || exit 2\nr9_trace provider-schema after"),("awk -F= '\nBEGIN", "r9_trace provider-fields before\nawk -F= '\nBEGIN"),("' \"$provider/status\"\n","' \"$provider/status\"\nr9_trace provider-fields after\n")]
def patch_status(text):return apply(text,status_operations(text))
