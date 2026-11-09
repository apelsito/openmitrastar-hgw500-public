"""Pure, versioned R9 observation patches; never write a firmware source tree."""
import re

INCLUDES='''/* OMF367R9_INCLUDES_BEGIN */
#include <linux/ktime.h>
#include <linux/atomic.h>
#include <linux/preempt.h>
/* OMF367R9_INCLUDES_END */
'''

HOST_HELPERS=r'''/* OMF367R9_HOSTLINK_HELPERS_BEGIN */
static atomic_t qdrv_f367r9_trace_state = ATOMIC_INIT(0);
static atomic_t qdrv_f367r9_trace_lines = ATOMIC_INIT(0);
static u64 qdrv_f367r9_trace_start_ns;

void qdrv_f367r9_hostlink_trace_arm(unsigned int channel)
{
 if(channel!=52 || atomic_cmpxchg(&qdrv_f367r9_trace_state,0,1)!=0)return;
 WRITE_ONCE(qdrv_f367r9_trace_start_ns,ktime_get_ns());
 smp_wmb();
 atomic_set(&qdrv_f367r9_trace_state,2);
}

bool qdrv_f367r9_hostlink_trace_active(void)
{
 u64 now;
 if(atomic_read(&qdrv_f367r9_trace_state)!=2)return false;
 smp_rmb();
 now=ktime_get_ns();
 return now-READ_ONCE(qdrv_f367r9_trace_start_ns)<8000000000ULL;
}

struct qdrv_f367r9_wait_trace {
 bool active;
 u32 command,start_jiffies,budget_ticks,progress;
 u64 start_ns,next_ns;
 const char *phase;
};

static void qdrv_f367r9_wait_emit(struct qdrv_f367r9_wait_trace *trace,
 const char *event,u64 now,int timeout)
{
 int line=atomic_inc_return(&qdrv_f367r9_trace_lines);
 int shared_cal=-1;
 if(line>48){
  if(line==49)pr_info("OMF367R9_HLINK_TRACE_BUDGET exhausted=1 lines=48\n");
  return;
 }
 if(soc_shared_params)shared_cal=READ_ONCE(soc_shared_params->calstate);
 pr_info("OMF367R9_HLINK phase=%s event=%s cmd=%u budget_ticks=%u timeout=%d jiffies=%u delta_ticks=%u monotonic_ns=%llu elapsed_ns=%llu cal_global=%u cal_shared=%d cal_default=%u hardirq=%u softirq=%u irq_off=%u preempt=%u\n",
  trace->phase,event,trace->command,trace->budget_ticks,timeout,(u32)jiffies,
  (u32)((u32)jiffies-trace->start_jiffies),(unsigned long long)now,
  (unsigned long long)(now-trace->start_ns),(unsigned)READ_ONCE(g_qtn_params.g_calstate),
  shared_cal,(unsigned)QTN_CALSTATE_DEFAULT,!!in_irq(),!!in_serving_softirq(),
  !!irqs_disabled(),(unsigned)preempt_count());
}

static struct qdrv_f367r9_wait_trace qdrv_f367r9_wait_begin(
 u32 command,const char *message,u32 budget_ticks,u32 start_jiffies)
{
 struct qdrv_f367r9_wait_trace trace={0};
 if(command!=38 && command!=17 && command!=35 && command!=26)return trace;
 if(!qdrv_f367r9_hostlink_trace_active())return trace;
 trace.active=true;trace.command=command;trace.start_jiffies=start_jiffies;
 trace.budget_ticks=budget_ticks;trace.start_ns=ktime_get_ns();
 trace.next_ns=trace.start_ns+1000000000ULL;
 trace.phase=!strcmp(message,"waiting for empty mbox")?"empty":
  !strcmp(message,"waiting for MuC dequeue")?"dequeue":"completion";
 qdrv_f367r9_wait_emit(&trace,"before",trace.start_ns,-1);
 return trace;
}

static void qdrv_f367r9_wait_progress(struct qdrv_f367r9_wait_trace *trace)
{
 u64 now;
 if(!trace->active || trace->progress>=6)return;
 now=ktime_get_ns();
 if(now<trace->next_ns || now-READ_ONCE(qdrv_f367r9_trace_start_ns)>=8000000000ULL)return;
 trace->next_ns=now+1000000000ULL;trace->progress++;
 qdrv_f367r9_wait_emit(trace,"progress",now,-1);
}

static void qdrv_f367r9_wait_end(struct qdrv_f367r9_wait_trace *trace,int timeout)
{
 if(trace->active)qdrv_f367r9_wait_emit(trace,"after",ktime_get_ns(),timeout);
}
/* OMF367R9_HOSTLINK_HELPERS_END */
'''

PEER_HELPERS=r'''/* OMF367R9_PEER_HELPERS_BEGIN */
static atomic_t f367r9_csa_timer_seen = ATOMIC_INIT(0);
static void f367r9_csa_timer_trace(const char *event,u64 start_ns)
{
 u64 now=ktime_get_ns();
 pr_info("OMF367R9_CSA event=%s target=52 jiffies=%u monotonic_ns=%llu elapsed_ns=%llu hardirq=%u softirq=%u irq_off=%u preempt=%u\n",
  event,(u32)jiffies,(unsigned long long)now,
  (unsigned long long)(now-start_ns),!!in_irq(),!!in_serving_softirq(),
  !!irqs_disabled(),(unsigned)preempt_count());
}
/* OMF367R9_PEER_HELPERS_END */
'''

def once(text,needle,replacement):
    if text.count(needle)!=1:raise ValueError('nonunique anchor: '+needle[:80])
    return text.replace(needle,replacement,1)

def patch_hostlink(text):
    if 'OMF367R9_' in text:raise ValueError('R9 hostlink already patched')
    marker='#define QDRV_IOCTL_EVNT_TIMEOUT'
    text=once(text,marker,HOST_HELPERS+'\n'+marker)
    text=INCLUDES+text
    lines=text.splitlines(keepends=True);out=[]
    for line in lines:
        out.append(line)
        if re.match(r'\s*u32 irq_to = wait_time\*100000/HZ;',line):
            out.append('\tstruct qdrv_f367r9_wait_trace omr9_trace = qdrv_f367r9_wait_begin(ioctl->ioctl_command,msg,wait_time,(u32)start_time); /* OMF367R9_MACRO */ \\\n')
        if re.match(r'\s*timeout = time_after\(jiffies, start_time \+ wait_time\);',line):
            # This point is only the non-hard-IRQ path. The hook reads clocks
            # but does not participate in either original timeout expression.
            out.append('\t\t\tqdrv_f367r9_wait_progress(&omr9_trace); /* OMF367R9_MACRO */ \\\n')
        if re.match(r'\s*status = timeout && cond;',line):
            out.append('\tqdrv_f367r9_wait_end(&omr9_trace,status); /* OMF367R9_MACRO */ \\\n')
    result=''.join(out)
    if result.count('/* OMF367R9_MACRO */')!=3:raise ValueError('timeout macro anchors')
    return result

def patch_peer_csa(text):
    if 'OMF367R9_' in text:raise ValueError('R9 CSA already patched')
    anchor='void ieee80211_finish_csa_timer(struct timer_list *timer)'
    text=once(text,anchor,PEER_HELPERS+'\n'+anchor)
    target='\t(finish_csa ? finish_csa : ieee80211_finish_csa)((unsigned long)ic);'
    before=r'''/* OMF367R9_PEER_LOCAL_BEGIN */
 struct ieee80211_channel *r9_target=READ_ONCE(ic->ic_csa_chan);
 bool r9_trace=false;
 u64 r9_start=0;
 if(r9_target && r9_target!=IEEE80211_CHAN_ANYC &&
    READ_ONCE(r9_target->ic_ieee)==52 && atomic_cmpxchg(&f367r9_csa_timer_seen,0,1)==0){
  r9_trace=true;r9_start=ktime_get_ns();f367r9_csa_timer_trace("before",r9_start);
 }
/* OMF367R9_PEER_LOCAL_END */
'''
    after=r'''
/* OMF367R9_PEER_AFTER_BEGIN */
 if(r9_trace)f367r9_csa_timer_trace("after",r9_start);
/* OMF367R9_PEER_AFTER_END */'''
    return INCLUDES+once(text,target,before+target+after)

def strip_observation(text):
    """Test helper: removing the observer must recover the input exactly."""
    text=''.join(line for line in text.splitlines(keepends=True) if '/* OMF367R9_MACRO */' not in line)
    text=text.replace(INCLUDES,'').replace(HOST_HELPERS+'\n','').replace(PEER_HELPERS+'\n','')
    for name in ('PEER_LOCAL',):
        text=re.sub(r'/\* OMF367R9_'+name+r'_BEGIN \*/.*?/\* OMF367R9_'+name+r'_END \*/\n', '',text,flags=re.S)
    text=re.sub(r'\n/\* OMF367R9_PEER_AFTER_BEGIN \*/.*?/\* OMF367R9_PEER_AFTER_END \*/','',text,flags=re.S)
    return text
