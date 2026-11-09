from pathlib import Path
import difflib
ROOT=Path(r"/workspace/user-home\Desktop\MitraStar")
tree=ROOT/"work/linux510-radio-port/quantenna-f332-ready-handshake"
p=tree/"qdrv/qdrv_radar.c";text=p.read_text()
def change(old,new):
 global text
 assert text.count(old)==1,old[:100]
 text=text.replace(old,new,1)
def function(name,new):
 global text
 import re
 m=re.search(r'(?m)^(?:static )?(?:void|int|bool) '+name+r'\([^;]*?\)\n\{',text);assert m,name
 start=m.end()-1;level=1;end=start+1
 while level:level+=(text[end]=='{')-(text[end]=='}');end+=1
 text=text[:m.start()]+new.strip()+"\n"+text[end:]
change('void qdrv_sta_set_xmit(int enable)','''#include "qdrv_f332_ready.inc"

void qdrv_sta_set_xmit(int enable)''')
function('qdrv_ocac_tasklet',r'''static void qdrv_ocac_tasklet(unsigned long data)
{
 struct qtn_ocac_info *info=(struct qtn_ocac_info *)data;
 struct radar_ocac_info_s *radar;
 struct ieee80211com *ic=qdrv_radar_cb.ic;
 u32 generation,point;
 u8 channel;
 bool overflow=false,accepted;
 if(!qdrv_radar_cb.enabled||qdrv_f332_ready_stopping()||!ic||
    !ic->ic_ocac.ocac_chan||ic->ic_ocac.ocac_chan==IEEE80211_CHAN_ANYC||
    !ic->ic_bsschan||ic->ic_bsschan==IEEE80211_CHAN_ANYC||
    qdrv_radar_is_rdetection_required(ic->ic_bsschan))
  return;
 radar=radar_ocac_info_addr_get();
 if(!radar)return;
 channel=ic->ic_ocac.ocac_chan->ic_ieee;
 /* This API takes the provider OCAC lock itself; never call it under that lock. */
 if(radar_set_scan_context(channel)){qdrv_f332_ocac_unready();return;}
 generation=qdrv_f332_wait_ready(QDRV_F332_OCAC,channel,ic->ic_radar_bw);
 if(!generation){qdrv_f332_ocac_unready();return;}
 radar_record_buffer_pt(&point);
 if(qdrv_f332_generation()!=generation){qdrv_f332_ocac_unready();return;}
 accepted=qdrv_f332_ocac_record(ic,info,radar,channel,generation,point,&overflow);
 if(overflow){
  /* No out-of-bounds write and no retained continuity after a lost endpoint. */
  qdrv_f332_cancel_wait();radar_disable();(void)radar_set_scan_context(0);
  return;
 }
 if(accepted&&info->chan_status==QTN_OCAC_ON_DATA_CHAN)
  ic->ic_chan_switch_reason_record(ic,IEEE80211_CSW_REASON_OCAC_RUN);
}''')
change('\t/* resume normal operation on channel */',r'''
 /* A readiness interruption invalidates the entire CAC interval. */
 if(!qdrv_f332_complete_cac(chan)){
  sys_disable_xmit();
  stop_cac();
  if(ic->ic_mark_channel_dfs_cac_status){
   ic->ic_mark_channel_dfs_cac_status(ic,chan,IEEE80211_CHAN_DFS_CAC_DONE,false);
   ic->ic_mark_channel_dfs_cac_status(ic,chan,IEEE80211_CHAN_DFS_CAC_IN_PROGRESS,false);
  }
  if(ic->ic_mark_channel_availability_status)
   ic->ic_mark_channel_availability_status(ic,chan,IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_CAC_REQUIRED);
  if(qdrv_radar_cb.enabled&&!qdrv_f332_ready_stopping()&&ic->ic_curchan==chan)
   qdrv_radar_on_newchan();
  return;
 }
	/* resume normal operation on channel */''')
change('''	/* CAC not required for DFS slave */
	if (qdrv_is_dfs_slave() && !(ic->sta_dfs_info.sta_dfs_strict_mode))
		return;
''','''	/* CAC not required for DFS slave */
	if (qdrv_is_dfs_slave() && !(ic->sta_dfs_info.sta_dfs_strict_mode))
		return;
	if (!qdrv_f332_begin_cac(cur_chan))
		return;
''')
change('''void qdrv_radar_before_newchan(void)
{''','''void qdrv_radar_before_newchan(void)
{''')
# Cancel pending contexts only after local declarations (kernel C style).
needle='''	bool rdetect;

	if (!qdrv_radar_cb.enabled)
		return;

	if (ic->ic_flags & IEEE80211_F_SCAN) {'''
change(needle,'''\tbool rdetect;

	qdrv_f332_cancel_wait();
	if (!qdrv_radar_cb.enabled)
		return;

	if (ic->ic_flags & IEEE80211_F_SCAN) {''')
change('''	/* report new channel to the radar module */
	radar_set_chan(new_chan->ic_ieee);''','''	/* Publish context before requesting asynchronous detector readiness. */
	if (radar_set_scan_context(0) || radar_set_chan(new_chan->ic_ieee)) {
		sys_disable_xmit();
		return;
	}''')
needle='''	if (rdetect) {
		if (new_chan->ic_flags & IEEE80211_CHAN_DFS_OCAC_DONE) {'''
change(needle,'''\tif (rdetect) {
		if (qdrv_is_dfs_master() || qdrv_radar_sta_dfs || ic->sta_dfs_info.sta_dfs_strict_mode) {
			sys_disable_xmit();
			if (!qdrv_f332_wait_ready(QDRV_F332_SERVICE, new_chan->ic_ieee, ic->ic_radar_bw))
				return;
		}
		if (new_chan->ic_flags & IEEE80211_CHAN_DFS_OCAC_DONE) {''')
change('''			INIT_DELAYED_WORK(&qdrv_radar_cb.muc_sampling.sample_work,
				qdrv_radar_sample_work);''','''			INIT_DELAYED_WORK(&qdrv_radar_cb.muc_sampling.sample_work,
				qdrv_radar_sample_work);
			qdrv_radar_cb.muc_sampling.initialized = true;''')
change('''	qdrv_radar_cb.mac = mac;
	qdrv_radar_cb.ic = ic;''','''	qdrv_radar_cb.mac = mac;
	qdrv_radar_cb.ic = ic;
	qdrv_f332_ready_init();''')
function('qdrv_radar_exit',r'''int qdrv_radar_exit(struct qdrv_mac *mac)
{
 unsigned channel;
 int rc;
 if(mac->unit!=0)return 0;
 qdrv_f332_ready_join();
 if(!qdrv_radar_configured)return 0;
 /* Called before SoC/MuC/shared teardown, from process context. */
 sys_disable_xmit();
 qdrv_mac_disable_irq(mac,RUBY_M2L_IRQ_LO_OCAC);
 synchronize_irq(mac->irq);
 tasklet_kill(&qdrv_radar_cb.ocac_tasklet);
 if(qdrv_radar_cb.muc_sampling.initialized)
  cancel_delayed_work_sync(&qdrv_radar_cb.muc_sampling.sample_work);
 del_timer_sync(&qdrv_radar_cb.cac_timer);
 del_timer_sync(&qdrv_radar_cb.dfs_cs_timer);
 del_timer_sync(&qdrv_radar_cb.ic->sta_dfs_info.sta_radar_timer);
 for(channel=0;channel<qdrv_radar_cb.ic->ic_nchans;channel++)
  del_timer_sync(&qdrv_radar_cb.nonoccupy_timer[channel]);
 qdrv_radar_disable();
 pm_qos_remove_notifier(PM_QOS_POWER_SAVE,&qdrv_radar_cb.pm_notifier);
 sys_stop_radarmod();
 rc=radar_wait_stopped();
 if(rc)return rc; /* No ic/shared free unless lifetime drain is proven. */
 memset(&qdrv_radar_cb,0,sizeof(qdrv_radar_cb));
 qdrv_radar_configured=false;
 qdrv_radar_first_call=true;
 qdrv_radar_sta_dfs=false;
 return 0;
}''')
p.write_text(text,encoding="utf-8",newline="\n")
p=tree/"qdrv/qdrv_soc.c";text=p.read_text()
needle='''	qtn_show_info_unregister();

	(void)qdrv_mu_stat_exit(qcb);'''
assert text.count(needle)==1
text=text.replace(needle,'''\t/* F332: drain detector/retry callbacks before stopping MuC or freeing ic. */
	if (qdrv_radar_exit(&qcb->macs[0]) != 0)
		return -EBUSY;

	qtn_show_info_unregister();

	(void)qdrv_mu_stat_exit(qcb);''')
p.write_text(text,encoding="utf-8",newline="\n")
patch=[]
for name in ("qdrv_radar.c","qdrv_soc.c"):
 a=ROOT/"work/linux510-radio-port/quantenna-f334-f321-profile/qdrv"/name;b=tree/"qdrv"/name
 patch.extend(difflib.unified_diff(a.read_text().splitlines(keepends=True),b.read_text().splitlines(keepends=True),fromfile="F334/"+name,tofile="F332-ready/"+name))
out=ROOT/"outputs/preflight/f332-ready-handshake"
out.mkdir(parents=True,exist_ok=True)
(out/"integration.diff").write_text("".join(patch),encoding="utf-8")
print("F332 qdrv handshake integrated in new tree only")

