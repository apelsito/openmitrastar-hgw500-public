"""Apply the reviewed F344 host-only CSA admission and process drain."""
from pathlib import Path
from prepare_f344_csa_policy import closing
ROOT=Path(__file__).resolve().parents[1]
Q=ROOT/'work/linux510-radio-port/quantenna-f344-modes/qdrv'
W=ROOT/'work/linux510-radio-port/quantenna-f344-peers/wlan'
H=ROOT/'work/kernel-port/f344/headers/net80211/ieee80211_var.h'
def read(p):return p.read_text()
def write(p,s):p.write_bytes(s.encode())
def main():
 s=read(H)
 if 'ic_f344_csa_enter' in s:raise SystemExit('already extended')
 s=s.replace('int (*ic_f344_channel_allowed)(struct ieee80211com *, struct ieee80211_channel *);','''int (*ic_f344_channel_allowed)(struct ieee80211com *, struct ieee80211_channel *);
 unsigned (*ic_f344_csa_enter)(struct ieee80211com *, struct ieee80211_channel *, unsigned);
 void (*ic_f344_csa_leave)(struct ieee80211com *);
 unsigned ic_f344_timer_generation;
 unsigned ic_f344_hardware_generation;''');write(H,s)
 write(Q/'f344_csa_state.h',read(ROOT/'work/kernel-port/f344/f344_csa_state.h'))
 p=Q/'qdrv_control.c';s=read(p)
 s=s.replace('#include "f344_mode_gate.h"','#include "f344_mode_gate.h"\n#include "f344_csa_state.h"')
 s=s.replace('module_param(openmitrastar_mode_channel_hold, bool, 0600);','''static DEFINE_SPINLOCK(f344_policy_lock);
static struct f344_csa_state f344_policy = { .generation = 1 };
static int f344_hold_set(const char *value, const struct kernel_param *kp)
{
 bool hold; unsigned long flags; int rc;
 if (!openmitrastar_mode_workflow || kstrtobool(value, &hold)) return -EINVAL;
 spin_lock_irqsave(&f344_policy_lock, flags);
 rc = f344_csa_hold(&f344_policy, hold);
 if (!rc) WRITE_ONCE(openmitrastar_mode_channel_hold, hold);
 spin_unlock_irqrestore(&f344_policy_lock, flags);
 return rc ? -EBUSY : 0;
}
static const struct kernel_param_ops f344_hold_ops = {
 .set = f344_hold_set, .get = param_get_bool,
};
module_param_cb(openmitrastar_mode_channel_hold, &f344_hold_ops,
                &openmitrastar_mode_channel_hold, 0600);''')
 s=s.replace('static int qdrv_command_bridge(struct device *dev, int argc, char *argv[]);','static int qdrv_command_bridge(struct device *dev, int argc, char *argv[]);\nstatic int qdrv_command_mode(struct device *dev, int argc, char *argv[]);')
 s=s.replace('{ "bridge",\tqdrv_command_bridge },','{ "bridge",\tqdrv_command_bridge },\n\t{ "mode", qdrv_command_mode },')
 needle='if(argc==3&&!strcmp(argv[0],"stop")'
 i=s.index(needle)
 s=s[:i]+'''if(argc==3&&!strcmp(argv[0],"mode")&&!strcmp(argv[1],"0")&&!strcmp(argv[2],"drain-csa")){
  rc=f344_copy_topology(dev,&view,0,0);if(rc)return rc;
  return view.channel_hold&&!view.primary_up&&!view.secondary_up&&!view.open_gate&&view.csa_known&&!view.extender&&!view.other_vaps?0:-EPERM;
 }
 '''+s[i:]
 s+='''
unsigned qdrv_f344_csa_enter(struct ieee80211com *ic,
                           struct ieee80211_channel *channel, unsigned expected)
{
 unsigned long flags; unsigned token = 0;
 if (!READ_ONCE(openmitrastar_mode_workflow)) return 1;
 spin_lock_irqsave(&f344_policy_lock, flags);
 if (qdrv_f344_deferred_channel_allowed(ic, channel))
  token = f344_csa_enter(&f344_policy, expected);
 spin_unlock_irqrestore(&f344_policy_lock, flags);
 return token;
}
void qdrv_f344_csa_leave(struct ieee80211com *ic)
{
 unsigned long flags;
 if (!READ_ONCE(openmitrastar_mode_workflow)) return;
 spin_lock_irqsave(&f344_policy_lock, flags);
 f344_csa_leave(&f344_policy);
 spin_unlock_irqrestore(&f344_policy_lock, flags);
}
static int qdrv_command_mode(struct device *dev, int argc, char *argv[])
{
 struct qdrv_mac *mac; struct qdrv_wlan *qw; struct shared_params *sp;
 struct ieee80211com *ic; unsigned long flags; unsigned generation;
 bool active;
 if (!openmitrastar_mode_workflow || argc != 3 || strcmp(argv[1],"0") ||
     strcmp(argv[2],"drain-csa") || f344_control_vap_admit(dev,argc,argv)) return -EPERM;
 mac=qdrv_control_mac_get(dev,"0");if(!mac||!mac->data)return -ENODEV;
 qw=qdrv_mac_get_wlan(mac);ic=&qw->ic;sp=qtn_mproc_sync_shared_params_get();
 if(!sp||!sp->csa_lhost)return -ENODEV;
 spin_lock_irqsave(&f344_policy_lock,flags);
 generation=f344_policy.generation;
 active=!f344_policy.hold||f344_policy.readers;
 spin_unlock_irqrestore(&f344_policy_lock,flags);
 if(active)return -EAGAIN;
 /* HOLD admits no new producers. No state/RTNL/spin lock spans joins. */
 del_timer_sync(&ic->ic_timer_csa);
 spin_lock_irqsave(&qw->csa_lock,flags);
 active=!!(sp->csa_lhost->lhost_status&QTN_CSA_STATUS_LHOST_ACTIVE);
 spin_unlock_irqrestore(&qw->csa_lock,flags);
 if(active)return -EAGAIN; /* Never manufacture a firmware cancellation. */
 flush_work(&qw->csa_wq);
 flush_work(&qw->channel_work_wq);
 spin_lock_irqsave(&qw->csa_lock,flags);
 active=!!(sp->csa_lhost->lhost_status&QTN_CSA_STATUS_LHOST_ACTIVE);
 if(!active){ic->ic_csa_count=0;ic->ic_flags&=~IEEE80211_F_CHANSWITCH;ic->ic_finish_csa=NULL;}
 spin_unlock_irqrestore(&qw->csa_lock,flags);
 spin_lock_irqsave(&f344_policy_lock,flags);
 if(generation!=f344_policy.generation)active=true;
 active=!f344_csa_mark_drained(&f344_policy,active,true);
 spin_unlock_irqrestore(&f344_policy_lock,flags);
 return active?-EAGAIN:0;
}
'''
 write(p,s)
 p=Q/'qdrv_control.h';s=read(p);s+='''
unsigned qdrv_f344_csa_enter(struct ieee80211com *, struct ieee80211_channel *, unsigned);
void qdrv_f344_csa_leave(struct ieee80211com *);
''';write(p,s)
 p=Q/'qdrv_wlan.c';s=read(p)
 s=s.replace('ic->ic_f344_channel_allowed = qdrv_f344_deferred_channel_allowed;','''ic->ic_f344_channel_allowed = qdrv_f344_deferred_channel_allowed;
 ic->ic_f344_csa_enter = qdrv_f344_csa_enter;
 ic->ic_f344_csa_leave = qdrv_f344_csa_leave;''')
 start=s.index('static void qdrv_set_channel_deferred(');end=closing(s,start)+1;b=s[start:end]
 b=b.replace('unsigned long irqflags;','unsigned long irqflags;\n unsigned f344_token;',1)
 old='''	if (!qdrv_f344_deferred_channel_allowed(ic, ic->ic_csa_chan)) {
		if (!(csa->lhost_status & QTN_CSA_STATUS_LHOST_ACTIVE))
			ic->ic_csa_count = 0;'''
 assert old in b
 b=b.replace(old,''' f344_token=qdrv_f344_csa_enter(ic,ic->ic_csa_chan,0);
	if (!f344_token) {''')
 b=b.replace('DBGPRINTF_E("CSA already active\\n");','DBGPRINTF_E("CSA already active\\n");\n  qdrv_f344_csa_leave(ic);')
 b=b.replace('csa->lhost_status = QTN_CSA_STATUS_LHOST_ACTIVE;','WRITE_ONCE(ic->ic_f344_hardware_generation,f344_token);\n\tcsa->lhost_status = QTN_CSA_STATUS_LHOST_ACTIVE;')
 b=b[:-1]+' qdrv_f344_csa_leave(ic);\n}'
 s=s[:start]+b+s[end:]
 start=s.index('static void csa_work(');end=closing(s,start)+1;b=s[start:end]
 b=b.replace('unsigned long irqflags;','unsigned long irqflags;\n unsigned f344_generation=READ_ONCE(ic->ic_f344_hardware_generation);')
 b=b.replace('if (qw->csa_callback) {','''if (!qdrv_f344_csa_enter(ic,chan,f344_generation)) return;
 if (qw->csa_callback) {''')
 b=b[:-1]+' qdrv_f344_csa_leave(ic);\n}';s=s[:start]+b+s[end:]
 start=s.index('static void channel_work(');end=closing(s,start)+1;b=s[start:end]
 b=b.replace('ieee80211_channel_switch_post(ic);','''if (!qdrv_f344_csa_enter(ic,ic->ic_curchan,
                             READ_ONCE(ic->ic_f344_hardware_generation))) return;
 ieee80211_channel_switch_post(ic);''')
 b=b[:-1]+' qdrv_f344_csa_leave(ic);\n}';s=s[:start]+b+s[end:];write(p,s)
 p=W/'ieee80211_wireless.c';s=read(p)
 # The timer fence dominates both the default and OEM custom completion.
 needle='\t(finish_csa ? finish_csa : ieee80211_finish_csa)((unsigned long)ic);'
 s=s.replace(needle,''' unsigned token=ic->ic_f344_csa_enter?
  ic->ic_f344_csa_enter(ic,ic->ic_csa_chan,READ_ONCE(ic->ic_f344_timer_generation)):1;
 if(!token)return;
'''+needle+'''
 if(ic->ic_f344_csa_leave)ic->ic_f344_csa_leave(ic);''')
 start=s.index('int ieee80211_enter_csa(');end=closing(s,start)+1;b=s[start:end]
 b=b.replace('uint32_t csa_flag;','uint32_t csa_flag;\n unsigned f344_token;')
 marker='\tic->ic_csa_chan = chan;'
 b=b.replace(marker,''' f344_token=ic->ic_f344_csa_enter?ic->ic_f344_csa_enter(ic,chan,0):1;
 if(!f344_token)return -EPERM;
 WRITE_ONCE(ic->ic_f344_timer_generation,f344_token);
'''+marker)
 b=b.replace('\treturn 0;',' if(ic->ic_f344_csa_leave)ic->ic_f344_csa_leave(ic);\n\treturn 0;')
 s=s[:start]+b+s[end:];write(p,s)
 p=W/'ieee80211_input.c';s=read(p);start=s.index('ieee80211_parse_csaie(');end=closing(s,start)+1;b=s[start:end]
 # Keep original parser in a scoped admission. Missing/malformed elements
 # retain its native validation and never acquire a CSA token.
 b=b.replace('ieee80211_parse_csaie(','ieee80211_parse_csaie_body(',1)
 wrapper='''
static int ieee80211_parse_csaie(struct ieee80211_node *ni,u_int8_t *csa_frm,
 u_int8_t *csa_tsf_frm,const struct ieee80211_frame *wh)
{
 struct ieee80211com *ic=ni->ni_vap->iv_ic;
 struct ieee80211_ie_csa *ie=(struct ieee80211_ie_csa *)csa_frm;
 struct ieee80211_channel *chan;unsigned token;int rc;
 if(!ic->ic_f344_csa_enter||!ie||ie->csa_len!=3)
  return ieee80211_parse_csaie_body(ni,csa_frm,csa_tsf_frm,wh);
 chan=ieee80211_doth_findchan(ni->ni_vap,ie->csa_chan);
 token=ic->ic_f344_csa_enter(ic,chan,0);if(!token)return -1;
 rc=ieee80211_parse_csaie_body(ni,csa_frm,csa_tsf_frm,wh);
 ic->ic_f344_csa_leave(ic);return rc;
}
'''
 s=s[:start]+b+wrapper+s[end:];write(p,s)
 (W.parent/'CSA_INPUT_PENDING.txt').unlink()
if __name__=='__main__':main()
