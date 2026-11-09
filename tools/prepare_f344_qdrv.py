"""Versioned qdrv mode admission extension; never modify sealed F338/F341."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/linux510-radio-port/quantenna-f338-availability'
TARGET=ROOT/'work/linux510-radio-port/quantenna-f344-modes'
def main():
 if TARGET.exists():raise SystemExit('F344 qdrv source already exists')
 sources={}
 for sub in ('qdrv','wlan','mtest'):
  if not (SOURCE/sub).exists():continue
  for p in (SOURCE/sub).rglob('*'):
   if p.is_symlink():raise ValueError('source symlink')
   if p.is_file():q=TARGET/p.relative_to(SOURCE);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes());sources[str(p.relative_to(SOURCE))]=hashlib.sha256(p.read_bytes()).hexdigest()
 (TARGET/'Makefile').write_bytes((SOURCE/'Makefile').read_bytes())
 for name in ('f344_mode_gate.c','f344_mode_gate.h'):(TARGET/'qdrv'/name).write_bytes((ROOT/'work/kernel-port/f344'/name).read_bytes())
 p=TARGET/'qdrv/Makefile';s=p.read_text().replace('qdrv-objs :=','qdrv-objs := f344_mode_gate.o',1);p.write_bytes(s.encode())
 p=TARGET/'qdrv/qdrv_control.c';s=p.read_text();s=s.replace('#include <qtn/qtn_bb_mutex.h>','#include <qtn/qtn_bb_mutex.h>\n#include <linux/mutex.h>\n#include <linux/rtnetlink.h>\n#include "f344_mode_gate.h"',1)
 s=s.replace('static int openmitrastar_single_vap_create;','static bool openmitrastar_mode_workflow;\nmodule_param(openmitrastar_mode_workflow, bool, 0400);\nMODULE_PARM_DESC(openmitrastar_mode_workflow, "F344 explicit AP/STA/repeater VAP workflow; default disabled");\nstatic int openmitrastar_single_vap_create;',1)
 anchor='static int qdrv_sequential_precheck(int argc, char *argv[])'
 assert s.count(anchor)==1
 helper='''static struct qdrv_mac *qdrv_control_mac_get(struct device *, const char *);
static int f344_control_vap_admit(struct device *dev,int argc,char **argv)
{
 struct qdrv_mac *mac;struct qdrv_wlan *qw;struct f344_topology view={0};
 enum f344_vap_operation operation;unsigned i;u8 requested[IEEE80211_ADDR_LEN];int rc;
 if(argc==3&&!strcmp(argv[0],"stop")&&!strcmp(argv[1],"0")&&!strcmp(argv[2],"all"))operation=F344_DELETE_ALL;
 else if(argc==5&&!strcmp(argv[0],"start")&&!strcmp(argv[1],"0")&&!strcmp(argv[3],"wifi0")){
  if(!strcmp(argv[2],"ap"))operation=F344_CREATE_AP0;
  else if(!strcmp(argv[2],"sta"))operation=F344_CREATE_STA0;
  else return -EPERM;
  if(!openmitrastar_single_vap_create)return -EPERM;
  view.primary_mac_matches=openmitrastar_sequential_mac0_valid&&!qdrv_parse_mac(argv[4],requested)&&!memcmp(requested,openmitrastar_sequential_mac0,sizeof(requested));
 }else if(argc==4&&!strcmp(argv[0],"start")&&!strcmp(argv[1],"0")&&!strcmp(argv[2],"ap")&&!strcmp(argv[3],"wifi1")){
  if(!openmitrastar_single_vap_create)return -EPERM;
  operation=F344_CREATE_AP1;
 }else return -EPERM;
 mac=qdrv_control_mac_get(dev,"0");if(!mac||!mac->data)return -ENODEV;
 qw=qdrv_mac_get_wlan(mac);view.core_started=!!openmitrastar_sequential_started;
 view.open_gate=!!qdrv_openmitrastar_rf_gate_enabled();
 rtnl_lock();
 view.repeater=!!ieee80211_is_repeater(&qw->ic);
 for(i=0;i<QDRV_MAX_VAPS;i++){
  struct net_device *vdev=mac->vnet[i];struct qdrv_vap*qv;enum f344_mode mode;
  if(!vdev)continue;
  qv=netdev_priv(vdev);mode=qv->iv.iv_opmode==IEEE80211_M_HOSTAP?F344_MODE_AP:qv->iv.iv_opmode==IEEE80211_M_STA?F344_MODE_STA:F344_MODE_NONE;
  if(IEEE80211_VAP_WDS_IS_MBS(&qv->iv)||IEEE80211_VAP_WDS_IS_RBS(&qv->iv)||qv->iv.iv_opmode==IEEE80211_M_WDS)view.extender=true;
  if(!strcmp(vdev->name,"wifi0")){view.primary_present=true;view.primary_mode=mode;view.primary_up=!!(vdev->flags&IFF_UP);}
  else if(!strcmp(vdev->name,"wifi1")){view.secondary_present=true;view.secondary_mode=mode;view.secondary_up=!!(vdev->flags&IFF_UP);}
  else view.other_vaps++;
 }
 view.valid=true;rc=f344_vap_admit(&view,operation);rtnl_unlock();
 if(rc)pr_info("OMF344_MODE reject=%d operation=%u interfaces_down=%u open_gate=%u\\n",rc,operation,!view.primary_up&&!view.secondary_up,view.open_gate);
 return rc?-EPERM:0;
}

'''
 s=s.replace(anchor,helper+'static int qdrv_sequential_precheck(struct device *dev,int argc, char *argv[])',1)
 s=s.replace('if (openmitrastar_sequential_started) {','if (openmitrastar_sequential_started) {\n\t\tif (READ_ONCE(openmitrastar_mode_workflow))\n\t\t\treturn f344_control_vap_admit(dev,argc,argv);',1)
 s=s.replace('qdrv_sequential_precheck(argc, argv)','qdrv_sequential_precheck(dev, argc, argv)',1)
 s=s.replace('} else if (!strcmp(argv[0], "start") && argc == 5) {','} else if (openmitrastar_mode_workflow && !strcmp(argv[0], "stop") && argc==3) {\n\t\topenmitrastar_sequential_vap_created=0;\n\t\tpr_info("OMF344_MODE vaps_deleted=1 core_retained=1\\n");\n\t} else if (!strcmp(argv[0], "start") && (argc == 5 || (openmitrastar_mode_workflow && argc==4))) {',1)
 s=s.replace('pr_info("OMQDRVSEQ stage=vap-pass unit=0 mode=ap interface=wifi0 rf=blocked count=1\\n");','if(openmitrastar_mode_workflow)\n\t\t\tpr_info("OMF344_MODE vap_created=1 mode=%s interface=%s\\n",argv[2],argv[3]);\n\t\telse pr_info("OMQDRVSEQ stage=vap-pass unit=0 mode=ap interface=wifi0 rf=blocked count=1\\n");',1)
 # Both current callers are sysfs store and module exit, hence sleepable.
 # Serializing the command buffer also prevents a second control writer
 # from changing argv between the live topology precheck and native action.
 signature='int qdrv_control_input(struct device *dev, char *buf, unsigned int count)'
 assert s.count(signature)==1
 s=s.replace(signature,'static int qdrv_control_input_serialized(struct device *dev, char *buf, unsigned int count)',1)
 s+='''
static DEFINE_MUTEX(f344_control_mutex);
int qdrv_control_input(struct device *dev,char *buf,unsigned int count)
{
 int rc;
 if(in_atomic()||irqs_disabled())return -EWOULDBLOCK;
 mutex_lock(&f344_control_mutex);
 rc=qdrv_control_input_serialized(dev,buf,count);
 mutex_unlock(&f344_control_mutex);return rc;
}
'''
 p.write_bytes(s.encode());(TARGET/'F338-source-binding.json').write_text(json.dumps(sources,indent=2)+'\n')
if __name__=='__main__':main()
