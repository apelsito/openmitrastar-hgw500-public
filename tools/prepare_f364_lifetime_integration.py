"""Transplant only qualified F355 lifetime protection onto the F363 profile."""
from pathlib import Path
import difflib,hashlib,json,shutil
from prepare_f355_lifetime import transform
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/linux510-radio-port/quantenna-f363-temperature'
DEST=ROOT/'work/linux510-radio-port/quantenna-f364-lifetime'
DONOR=ROOT/'work/linux510-radio-port/quantenna-f355-lifetime/qdrv'
QUAL=Path('/workspace/OpenMitraStar-build/f355/f355-qualified-20260921T170051Z/result.json')
OUT=ROOT/'work/kernel-port/versions/f364-lifetime-integration'
NEW=('f355_lifetime.h','qdrv_f355_lifetime.h','qdrv_f355_lifetime.c')
CHANGED={'qdrv/Makefile','qdrv/qdrv_control.c','qdrv/qdrv_module.c','qdrv/qdrv_soc.c',
         'qdrv/qdrv_wlan.c','qdrv/qdrv_hostlink.c',*('qdrv/'+n for n in NEW)}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def replace(p,old,new):
 s=p.read_text();require(s.count(old)==1,'unique anchor '+p.name+' '+old[:55]);p.write_bytes(s.replace(old,new,1).encode())
def main():
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 require(not DEST.exists() and not OUT.exists(),'immutable F364 source exists')
 proof=json.loads(QUAL.read_text());require(proof['status']=='PASS_OFFLINE_PINNED_LIFETIME_COHERENT_CLOSURE','F355 qualification')
 for name in NEW:require(sha(DONOR/name)==proof['source_hashes']['qdrv/'+name],'F355 adapter drift')
 base_pins={p.relative_to(BASE).as_posix():sha(p) for p in BASE.rglob('*') if p.is_file()}
 shutil.copytree(BASE,DEST);OUT.mkdir(parents=True)
 for name in NEW:shutil.copyfile(DONOR/name,DEST/'qdrv'/name)
 q=DEST/'qdrv'
 replace(q/'Makefile','qdrv-objs :=','qdrv-objs := qdrv_f355_lifetime.o')
 for name in ('qdrv_module.c','qdrv_control.c','qdrv_soc.c','qdrv_wlan.c','qdrv_hostlink.c'):
  replace(q/name,'#include "qdrv_features.h"','#include "qdrv_features.h"\n#include "qdrv_f355_lifetime.h"')
 p=q/'qdrv_control.c'
 replace(p,'#include "qdrv_f355_lifetime.h"','#include "qdrv_f355_lifetime.h"\n#include <linux/mutex.h>')
 replace(p,'int qdrv_control_input(struct device *dev, char *buf, unsigned int count)',
         'static DEFINE_MUTEX(f364_control_mutex);\nstatic int qdrv_control_input_serialized(struct device *dev, char *buf, unsigned int count)')
 replace(p,'\tif (found >= 0) {\n\t\tif ((*s_command_table[found].fn)(dev, argc, argv) < 0) {',
 '''\tif (found >= 0) {
  /* Qualified F355 lifetime: pin after policy, before a possible mutation. */
  if (strcmp(argv[0],"get") && strcmp(argv[0],"stop")) {
   int lifetime_rc=qdrv_f355_claim(argv[0]);
   if(lifetime_rc){qcb->rc=lifetime_rc;return -1;}
  }
\t\tif ((*s_command_table[found].fn)(dev, argc, argv) < 0) {
   if(!strcmp(argv[0],"clearsram") || (!strcmp(argv[0],"start") && argc<=2))
    qdrv_f355_boot_failure();''')
 replace(p,'\tentry = proc_create("qdrvdata", 0666, NULL, &s_qdrv_proc_ops);',
         '\tsema_init(&s_output_sem, 1);\n\ts_output_qcb = qcb;\n\tentry = proc_create("qdrvdata", 0666, NULL, &s_qdrv_proc_ops);')
 replace(p,'\n\tsema_init(&s_output_sem, 1);\n\ts_output_qcb = qcb;\n\n\tversion_entry','\n\tversion_entry')
 replace(p,'\tif (down_interruptible(&s_output_sem)) {\n\t\treturn(-ERESTARTSYS);\n\t}\n\n\ts_output_qcb = NULL;',
         '\t/* Teardown must complete its proc lifetime drain despite signals. */\n\tdown(&s_output_sem);\n\n\ts_output_qcb = NULL;')
 wrapper=extract((DONOR/'qdrv_control.c').read_text(),'qdrv_control_input').replace('f344_control_mutex','f364_control_mutex')
 with p.open('ab') as f:f.write(('\n'+wrapper+'\n').encode())
 p=q/'qdrv_module.c'
 anchor='static DEVICE_ATTR(control, 0644,\n\tqdrv_attr_control_show, qdrv_attr_control_store);'
 lifetime_show=extract((DONOR/'qdrv_module.c').read_text(),'qdrv_attr_lifetime_state_show')
 replace(p,anchor,anchor+'\n'+lifetime_show+'\nstatic DEVICE_ATTR(lifetime_state,0444,qdrv_attr_lifetime_state_show,NULL);')
 replace(p,'\tint size;\n','\tint size;\n\tbool control_initialized=false;\n')
 replace(p,'\t\tDBGPRINTF_E("Failed to register \\"%s\\"\\n", QDRV_DEV_NAME);'.replace('\\"','\\"'),
         '\t\tDBGPRINTF_E("Failed to register \\"%s\\"\\n", QDRV_DEV_NAME);'.replace('\\"','\\"')+'\n\t\t/* device_register initialized the kobject even when add failed. */\n\t\tput_device(&qdrv_device);')
 replace(p,'\t/* Initialize control interface */','\tif(device_create_file(&qdrv_device,&dev_attr_lifetime_state))goto lifetime_sysfs_fail;\n\n\t/* Initialize control interface */')
 replace(p,'\tpr_info("OMQDRV stage=control-init-pass\\n");','\tcontrol_initialized=true;\n\tpr_info("OMQDRV stage=control-init-pass\\n");')
 replace(p,'\tpr_info("OMQDRV stage=control-ready rf=blocked\\n");','\tpr_info("OMQDRV stage=control-ready rf=blocked\\n");\n\t/* Last successful init step: no subsequent failure can unload a pin. */\n\tqdrv_f355_ready_commit();')
 replace(p,'control_init_fail:\n\tdevice_remove_file(&qdrv_device, &dev_attr_panic_on_muc_halt);',
         'control_init_fail:\n\tif(control_initialized)qdrv_control_exit(&qdrv_device);\n\tdevice_remove_file(&qdrv_device,&dev_attr_lifetime_state);\nlifetime_sysfs_fail:\n\tdevice_remove_file(&qdrv_device, &dev_attr_panic_on_muc_halt);')
 def module_exit(body):
  body=body.replace('\tstruct qdrv_cb *qcb;','''\tstruct qdrv_cb *qcb;
 /* The retained kernel reference protects module text; this is a second guard. */
 if(qdrv_f355_exit_begin())return;
 device_remove_file(&qdrv_device,&dev_attr_control);
 device_remove_bin_file(&qdrv_device,&qdrv_show_rssi_phy_stats);
 device_remove_file(&qdrv_device,&dev_attr_lifetime_state);''',1)
  start=body.index('\t/*\n\t * A control-only instance');end=body.index('\n\t/* Exit the control interface */',start)
  body=body[:start]+''' /* Only an unmutated instance can reach normal module exit. */
 if(qcb&&qcb->resources){
  pr_err("OMF355_LIFETIME unexpected-resources-retained resources=%#x\\n",qcb->resources);
  return;
 }
'''+body[end:]
  body=body.replace('\tdevice_remove_bin_file(&qdrv_device, &qdrv_show_rssi_phy_stats);\n','').replace('\tdevice_remove_file(&qdrv_device, &dev_attr_control);\n','')
  return body
 transform(p,'qdrv_module_exit',module_exit)
 p=q/'qdrv_soc.c'
 transform(p,'qdrv_soc_revoke_params',lambda b:b.replace('{','{\n if(qdrv_f355_retained()&&soc_shared_params){\n  pr_err("OMF355_LIFETIME shared-retained reboot-required\\n");return;\n }',1))
 transform(p,'qdrv_soc_publish_params',lambda b:b.replace('\t/* Guard againt second call to function */','\t/* A retained publication must never be overwritten by a retry. */\n\tif(soc_shared_params)return -EBUSY;\n\t/* Guard againt second call to function */',1))
 transform(p,'qdrv_soc_init',lambda b:b.replace('\thal_reset();','\tretval=qdrv_f355_core_begin();\n\tif(retval)return retval;\n\thal_reset();',1).replace('\t/* Clean up as much as we can */\n\t(void) qdrv_soc_exit(dev);','\t/* Unknown partial hardware ownership: retain allocations and callbacks. */\n\tqdrv_f355_boot_failure();',1))
 transform(p,'qdrv_soc_exit',lambda b:b.replace('\tqcb = dev_get_drvdata(dev);','\tqcb = dev_get_drvdata(dev);\n\tif(qdrv_f355_retained())return -EBUSY;\n\tif(!qcb||!qcb->resources)return 0;',1))
 transform(p,'qdrv_start_dsp_only',lambda b:b.replace('\t/* Bring up the DSP */','\tretval=qdrv_f355_core_begin();\n\tif(retval)return retval;\n\t/* Bring up the DSP */',1).replace('\tif(retval == 0)\n\t\tqcb->resources |= QDRV_RESOURCE_DSP;','\tif(retval == 0)\n\t\tqcb->resources |= QDRV_RESOURCE_DSP;\n\telse qdrv_f355_boot_failure();',1))
 for filename,fn in (('qdrv_wlan.c','qdrv_wlan_exit'),('qdrv_hostlink.c','qdrv_hostlink_exit')):
  transform(q/filename,fn,lambda b:b.replace('\tDBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "-->Enter\\n");','\tif(qdrv_f355_retained())return -EBUSY;\n\tDBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "-->Enter\\n");',1))
 finalize(base_pins)

def finalize(base_pins=None):
 q=DEST/'qdrv'
 if base_pins is None:base_pins={p.relative_to(BASE).as_posix():sha(p) for p in BASE.rglob('*') if p.is_file()}
 require(not (OUT/'source-manifest.json').exists(),'source already sealed')
 pins={p.relative_to(DEST).as_posix():sha(p) for p in DEST.rglob('*') if p.is_file()}
 changed={n for n in set(pins)|set(base_pins) if pins.get(n)!=base_pins.get(n)}
 require(changed==CHANGED,'unexpected delta '+str(changed^CHANGED))
 require(all(sha(BASE/n)==digest for n,digest in base_pins.items()),'F363 changed during copy')
 require(extract((BASE/'qdrv/qdrv_wlan.c').read_text(),'qdrv_get_internal_temp')==extract((q/'qdrv_wlan.c').read_text(),'qdrv_get_internal_temp'),'F363 thermal guard changed')
 require(not (q/'f344_mode_gate.c').exists(),'F344 mode implementation leaked')
 for name in ('qdrv_control_init','qdrv_control_exit'):
  require(extract((q/'qdrv_control.c').read_text(),name)==extract((DONOR/'qdrv_control.c').read_text(),name),'qualified F355 proc body changed')
 diff=[]
 for name in sorted(changed):
  left=(BASE/name).read_text().splitlines(keepends=True) if (BASE/name).exists() else []
  diff.extend(difflib.unified_diff(left,(DEST/name).read_text().splitlines(keepends=True),fromfile='F363/'+name,tofile='F364/'+name))
 (OUT/'source.diff').write_text(''.join(diff))
 result={'schema':'openmitrastar.f364-lifetime-source/v1','status':'PASS_SOURCE_COMBINATION',
         'source':str(DEST),'baseline':str(BASE),'source_hashes':pins,'baseline_hashes':base_pins,
         'changed_files':sorted(changed),'f355_qualification':{'path':str(QUAL),'sha256':sha(QUAL)},
         'f355_adapter_exact':True,'f355_proc_bodies_exact':True,'f363_temperature_guard_exact':True,
         'f344_features_added':False,'hardware_actions':False,'f363_final_image_required':True}
 (OUT/'source-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'source':str(DEST),'manifest':str(OUT/'source-manifest.json')}))
if __name__=='__main__':main()
