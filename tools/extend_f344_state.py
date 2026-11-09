"""Add sanitized live readback and native three-address bridge controls."""
from pathlib import Path
from test_f329_watchdog import function
ROOT=Path(__file__).resolve().parents[1]
QDRV=ROOT/'work/linux510-radio-port/quantenna-f344-modes/qdrv'
def main():
 p=QDRV/'qdrv_control.c';s=p.read_text()
 if 'qdrv_f344_mode_state(' in s:raise SystemExit('F344 state extension already present')
 for name in ('f344_mode_gate.c','f344_mode_gate.h'):(QDRV/name).write_bytes((ROOT/'work/kernel-port/f344'/name).read_bytes())
 old=function(s,'f344_control_vap_admit');new=old
 new=new.replace('struct qdrv_mac *mac;struct qdrv_wlan *qw;struct f344_topology view={0};','struct f344_topology view={0};')
 new=new.replace('enum f344_vap_operation operation;unsigned i;u8 requested','enum f344_vap_operation operation;u8 requested')
 new=new.replace('else if(argc==5', 'else if(argc==4&&!strcmp(argv[0],"bridge")&&!strcmp(argv[1],"0")&&(!strcmp(argv[2],"enable")||!strcmp(argv[2],"disable")||!strcmp(argv[2],"clear")))return -EPERM;\n else if(argc==3&&!strcmp(argv[0],"bridge")&&!strcmp(argv[1],"0")&&(!strcmp(argv[2],"enable")||!strcmp(argv[2],"disable")||!strcmp(argv[2],"clear")))operation=F344_BRIDGE_CONFIG;\n else if(argc==5',1)
 begin=new.index(' mac=qdrv_control_mac_get(');end=new.index(' if(rc)pr_info',begin)
 new=new[:begin]+' rc=f344_copy_topology(dev,&view,0,0);if(rc)return rc;\n rc=f344_vap_admit(&view,operation);\n'+new[end:]
 copy='''static int f344_copy_topology(struct device *dev,struct f344_topology *view,unsigned *three_address,unsigned *channel_offset)
{
 struct qdrv_mac *mac=qdrv_control_mac_get(dev,"0");struct qdrv_wlan *qw;unsigned i;
 if(!mac||!mac->data)return -ENODEV;
 qw=qdrv_mac_get_wlan(mac);view->core_started=!!openmitrastar_sequential_started;
 view->open_gate=!!qdrv_openmitrastar_rf_gate_enabled();
 rtnl_lock();view->repeater=!!ieee80211_is_repeater(&qw->ic);
 if(three_address)*three_address=!!QDRV_FLAG_3ADDR_BRIDGE_ENABLED();
 if(channel_offset)*channel_offset=(qw->ic.ic_phytype==IEEE80211_T_OFDM||qw->ic.ic_phytype==IEEE80211_T_DS)?1:0;
 for(i=0;i<QDRV_MAX_VAPS;i++){
  struct net_device*vdev=mac->vnet[i];struct qdrv_vap*qv;enum f344_mode mode;
  if(!vdev)continue;
  qv=netdev_priv(vdev);mode=qv->iv.iv_opmode==IEEE80211_M_HOSTAP?F344_MODE_AP:qv->iv.iv_opmode==IEEE80211_M_STA?F344_MODE_STA:F344_MODE_NONE;
  if(IEEE80211_VAP_WDS_IS_MBS(&qv->iv)||IEEE80211_VAP_WDS_IS_RBS(&qv->iv)||qv->iv.iv_opmode==IEEE80211_M_WDS)view->extender=true;
  if(!strcmp(vdev->name,"wifi0")){view->primary_present=true;view->primary_mode=mode;view->primary_up=!!(vdev->flags&IFF_UP);}
  else if(!strcmp(vdev->name,"wifi1")){view->secondary_present=true;view->secondary_mode=mode;view->secondary_up=!!(vdev->flags&IFF_UP);}
  else view->other_vaps++;
 }
 view->valid=true;rtnl_unlock();return 0;
}

'''
 s=s.replace(old,copy+new)
 s+='''
int qdrv_f344_mode_state(struct device *dev,char *buf)
{
 struct f344_topology v={0};unsigned three_address=0,offset=0;int rc;
 mutex_lock(&f344_control_mutex);
 rc=f344_copy_topology(dev,&v,&three_address,&offset);
 if(!rc)rc=scnprintf(buf,512,"schema=openmitrastar.f344-mode/v1\\nworkflow_enabled=%u\\ncore_started=%u\\nprimary_present=%u\\nprimary_mode=%u\\nprimary_up=%u\\nsecondary_present=%u\\nsecondary_mode=%u\\nsecondary_up=%u\\nrepeater=%u\\nextender=%u\\nother_vaps=%u\\nopen_gate=%u\\nthree_address_bridge=%u\\nchannel_input_offset=%u\\n",openmitrastar_mode_workflow,v.core_started,v.primary_present,v.primary_mode,v.primary_up,v.secondary_present,v.secondary_mode,v.secondary_up,v.repeater,v.extender,v.other_vaps,v.open_gate,three_address,offset);
 mutex_unlock(&f344_control_mutex);return rc;
}
'''
 p.write_bytes(s.encode())
 p=QDRV/'qdrv_control.h';s=p.read_text();pos=s.rfind('#endif');s=s[:pos]+'int qdrv_f344_mode_state(struct device *dev,char *buf);\n'+s[pos:];p.write_bytes(s.encode())
 p=QDRV/'qdrv_module.c';s=p.read_text()
 anchor='static DEVICE_ATTR(control, 0644,\n\tqdrv_attr_control_show, qdrv_attr_control_store);'
 assert s.count(anchor)==1
 s=s.replace(anchor,anchor+'''
static ssize_t qdrv_attr_mode_state_show(struct device *dev,struct device_attribute *attr,char *buf)
{return qdrv_f344_mode_state(dev,buf);}
static DEVICE_ATTR(mode_state,0444,qdrv_attr_mode_state_show,NULL);
''')
 anchor='\tif (device_create_file(&qdrv_device, &dev_attr_panic_on_muc_halt) != 0)'
 s=s.replace(anchor,'\tif(device_create_file(&qdrv_device,&dev_attr_mode_state)!=0)goto mode_state_sysfs_fail;\n'+anchor,1)
 s=s.replace('muc_halt_sysfs_fail:\n\tdevice_remove_file(&qdrv_device, &dev_attr_control);','muc_halt_sysfs_fail:\n\tdevice_remove_file(&qdrv_device,&dev_attr_mode_state);\nmode_state_sysfs_fail:\n\tdevice_remove_file(&qdrv_device, &dev_attr_control);',1)
 # Remove/drain this new getter before any existing exit frees qdrv state.
 anchor='static void __exit qdrv_module_exit(void)\n{';assert s.count(anchor)==1
 s=s.replace(anchor,anchor+'\n\tdevice_remove_file(&qdrv_device,&dev_attr_mode_state);',1)
 p.write_bytes(s.encode())
if __name__=='__main__':main()
