"""Create the F355 software-only lifetime derivative; never edit F344."""
from pathlib import Path
import hashlib,json,shutil
from prepare_f344_csa_policy import closing
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/linux510-radio-port/quantenna-f344-modes'
DEST=ROOT/'work/linux510-radio-port/quantenna-f355-lifetime'
NEW=ROOT/'work/kernel-port/f355'
def write(p,s):p.write_bytes(s.encode())
def transform(p,name,fn):
 s=p.read_text();import re
 m=re.search(r'^(?:static\s+)?[^;{}\n]*\b'+name+r'\([^;{}]*\)\s*\{',s,re.M)
 if not m:raise ValueError('missing '+name)
 end=closing(s,m.start())+1;write(p,s[:m.start()]+fn(s[m.start():end])+s[end:])
def main():
 if shutil.disk_usage(ROOT).free<=500*1024*1024:raise RuntimeError('C space guard')
 if DEST.exists():raise ValueError('F355 source already exists')
 shutil.copytree(BASE,DEST);q=DEST/'qdrv'
 for name in ('f355_lifetime.h','qdrv_f355_lifetime.h','qdrv_f355_lifetime.c'):(q/name).write_bytes((NEW/name).read_bytes())
 p=q/'Makefile';write(p,p.read_text().replace('qdrv-objs :=','qdrv-objs := qdrv_f355_lifetime.o',1))
 for name in ('qdrv_module.c','qdrv_control.c','qdrv_soc.c','qdrv_wlan.c','qdrv_hostlink.c'):
  p=q/name;s=p.read_text();anchor='#include "qdrv_features.h"'
  if anchor not in s:anchor='#include "qdrv_debug.h"'
  if anchor not in s:raise ValueError('include anchor '+name)
  write(p,s.replace(anchor,anchor+'\n#include "qdrv_f355_lifetime.h"',1))
 p=q/'qdrv_control.c';s=p.read_text()
 s=s.replace(' int rc;\n if(in_atomic()||irqs_disabled())return -EWOULDBLOCK;',' int rc;\n if(!qdrv_f355_ready())return -EAGAIN;\n if(qdrv_f355_failed())return -EIO;\n if(in_atomic()||irqs_disabled())return -EWOULDBLOCK;',1)
 anchor='\tif (found >= 0) {\n\t\tif ((*s_command_table[found].fn)(dev, argc, argv) < 0) {'
 assert anchor in s
 s=s.replace(anchor,'''\tif (found >= 0) {
  /* Pin before the first admitted side-effect-capable command. Even set
   * may prepare ownership for later hardware operations. Invalid/unmatched
   * commands have already been rejected. Pure get and stop do not pin. */
  if (strcmp(argv[0],"get") && strcmp(argv[0],"stop")) {
   int lifetime_rc=qdrv_f355_claim(argv[0]);
   if(lifetime_rc){qcb->rc=lifetime_rc;return -1;}
  }
\t\tif ((*s_command_table[found].fn)(dev, argc, argv) < 0) {
   if(!strcmp(argv[0],"clearsram") || (!strcmp(argv[0],"start") && argc<=2))
    qdrv_f355_boot_failure();''',1)
 # Initialize the proc reader's state before publishing the first proc node.
 s=s.replace('\tentry = proc_create("qdrvdata", 0666, NULL, &s_qdrv_proc_ops);','\tsema_init(&s_output_sem, 1);\n\ts_output_qcb = qcb;\n\tentry = proc_create("qdrvdata", 0666, NULL, &s_qdrv_proc_ops);',1)
 second='\n\tsema_init(&s_output_sem, 1);\n\ts_output_qcb = qcb;\n\n\tversion_entry'
 assert second in s;s=s.replace(second,'\n\tversion_entry',1)
 s=s.replace('\tif (down_interruptible(&s_output_sem)) {\n\t\treturn(-ERESTARTSYS);\n\t}\n\n\ts_output_qcb = NULL;','\t/* Teardown must complete its proc lifetime drain despite signals. */\n\tdown(&s_output_sem);\n\n\ts_output_qcb = NULL;',1)
 write(p,s)
 p=q/'qdrv_module.c';s=p.read_text()
 anchor='static DEVICE_ATTR(mode_state,0444,qdrv_attr_mode_state_show,NULL);'
 assert anchor in s;s=s.replace(anchor,anchor+'''
static ssize_t qdrv_attr_lifetime_state_show(struct device *dev,struct device_attribute *attr,char *buf)
{return qdrv_f355_status(buf);}
static DEVICE_ATTR(lifetime_state,0444,qdrv_attr_lifetime_state_show,NULL);
''',1)
 s=s.replace('\tint size;\n','\tint size;\n\tbool control_initialized=false;\n',1)
 anchor='\t/* Initialize control interface */'
 s=s.replace(anchor,'\tif(device_create_file(&qdrv_device,&dev_attr_lifetime_state))goto lifetime_sysfs_fail;\n\n'+anchor,1)
 s=s.replace('\tpr_info("OMQDRV stage=control-init-pass\\n");','\tcontrol_initialized=true;\n\tpr_info("OMQDRV stage=control-init-pass\\n");',1)
 anchor='\tpr_info("OMQDRV stage=control-ready rf=blocked\\n");'
 s=s.replace(anchor,anchor+'\n\t/* Last successful init step: no subsequent failure can unload a pin. */\n\tqdrv_f355_ready_commit();',1)
 s=s.replace('control_init_fail:\n\tdevice_remove_file(&qdrv_device, &dev_attr_panic_on_muc_halt);','control_init_fail:\n\tif(control_initialized)qdrv_control_exit(&qdrv_device);\n\tdevice_remove_file(&qdrv_device,&dev_attr_lifetime_state);\nlifetime_sysfs_fail:\n\tdevice_remove_file(&qdrv_device, &dev_attr_panic_on_muc_halt);',1)
 write(p,s)
 def module_exit(b):
  b=b.replace('\tdevice_remove_file(&qdrv_device,&dev_attr_mode_state);',''' /* Normal delete_module cannot reach this after a retained reference.
  * This guard also avoids destructive object cleanup if invoked wrongly;
  * it does not claim a return from module_exit can cancel forced removal. */
 if(qdrv_f355_exit_begin())return;
 device_remove_file(&qdrv_device,&dev_attr_lifetime_state);
\tdevice_remove_file(&qdrv_device,&dev_attr_mode_state);''',1)
  start=b.index('\t/*\n\t * A control-only instance')
  end=b.index('\n\t/* Exit the control interface */',start)
  b=b[:start]+''' /* No hardware resources exist in the only unloadable state. Never route
  * this callback through a command gate which may reject stop and then free. */
 if(qcb&&qcb->resources){
  pr_err("OMF355_LIFETIME unexpected-resources-retained resources=%#x\\n",qcb->resources);
  return;
 }
'''+b[end:]
  return b
 transform(p,'qdrv_module_exit',module_exit)
 p=q/'qdrv_soc.c'
 def revoke(b):return b.replace('{','{\n if(qdrv_f355_retained()&&soc_shared_params){\n  pr_err("OMF355_LIFETIME shared-retained reboot-required\\n");return;\n }',1)
 transform(p,'qdrv_soc_revoke_params',revoke)
 def publish(b):return b.replace('\t/* Guard againt second call to function */','\t/* A retained publication must never be overwritten by a retry. */\n\tif(soc_shared_params)return -EBUSY;\n\t/* Guard againt second call to function */',1)
 transform(p,'qdrv_soc_publish_params',publish)
 def core(b):
  b=b.replace('\thal_reset();','\tretval=qdrv_f355_core_begin();\n\tif(retval)return retval;\n\thal_reset();',1)
  b=b.replace('\t/* Clean up as much as we can */\n\t(void) qdrv_soc_exit(dev);','\t/* Unknown partial hardware ownership: retain allocations and callbacks. */\n\tqdrv_f355_boot_failure();',1)
  return b
 transform(p,'qdrv_soc_init',core)
 def soc_exit(b):return b.replace('\tqcb = dev_get_drvdata(dev);','\tqcb = dev_get_drvdata(dev);\n\tif(qdrv_f355_retained())return -EBUSY;\n\tif(!qcb||!qcb->resources)return 0;',1)
 transform(p,'qdrv_soc_exit',soc_exit)
 def dsp(b):return b.replace('\t/* Bring up the DSP */','\tretval=qdrv_f355_core_begin();\n\tif(retval)return retval;\n\t/* Bring up the DSP */',1).replace('\tif(retval == 0)\n\t\tqcb->resources |= QDRV_RESOURCE_DSP;','\tif(retval == 0)\n\t\tqcb->resources |= QDRV_RESOURCE_DSP;\n\telse qdrv_f355_boot_failure();',1)
 transform(p,'qdrv_start_dsp_only',dsp)
 for filename,fn in (('qdrv_wlan.c','qdrv_wlan_exit'),('qdrv_hostlink.c','qdrv_hostlink_exit')):
  p=q/filename
  transform(p,fn,lambda b:b.replace('\tDBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "-->Enter\\n");','\tif(qdrv_f355_retained())return -EBUSY;\n\tDBGPRINTF(DBG_LL_ALL, QDRV_LF_TRACE, "-->Enter\\n");',1))
 proof={'schema':'openmitrastar.f355-source/v1','baseline':str(BASE),'source':str(DEST),'scope':'permanent module ownership after admitted mutation; no hot restart','hardware':False,'files':{str(p.relative_to(DEST)):hashlib.sha256(p.read_bytes()).hexdigest() for p in DEST.rglob('*') if p.is_file()}}
 write(NEW/'source-manifest.json',json.dumps(proof,indent=2)+'\n')
 print(json.dumps({'source':str(DEST),'files':len(proof['files']),'free_c':shutil.disk_usage(ROOT).free}))
if __name__=='__main__':main()
