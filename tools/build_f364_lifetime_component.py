"""Build only lifetime qdrv against copied F363 headers/context; no hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shlex,shutil,subprocess
from elftools.elf.elffile import ELFFile
import f334_qdrv_contract as qc
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/linux510-radio-port/quantenna-f364-lifetime'
SOURCE_PROOF=ROOT/'work/kernel-port/versions/f364-lifetime-integration/source-manifest.json'
F355=Path('/workspace/OpenMitraStar-build/f355/f355-qualified-20260921T170051Z/result.json')
REVIEW=ROOT/'work/kernel-port/versions/f364-lifetime-integration/reviewed-nonfunctional-delta.json'
REVIEW_SHA='90298fb0a646751ebf138e505b9dcf024998c8328dde5ffb610ae74cab039792'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def require(v,m):
 if not v:raise ValueError(m)
def item(p):p=Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def elf_symbols(p):
 with Path(p).open('rb') as f:
  elf=ELFFile(f);symbols=list(elf.get_section_by_name('.symtab').iter_symbols())
  return {s.name for s in symbols if s.name and s['st_shndx']=='SHN_UNDEF'},{s.name[10:] for s in symbols if s.name.startswith('__ksymtab_')}

def combination_checks():
 q=SOURCE/'qdrv';control=(q/'qdrv_control.c').read_text();module=(q/'qdrv_module.c').read_text();soc=(q/'qdrv_soc.c').read_text()
 entry=extract(control,'qdrv_control_input');dispatch=extract(control,'qdrv_control_input_serialized')
 init=extract(module,'qdrv_module_init');exit_body=extract(module,'qdrv_module_exit');core=extract(soc,'qdrv_soc_init')
 checks={
  'no_f344_mode_wiring':'f344_' not in control and 'mode_state' not in module and not (q/'f344_mode_gate.c').exists(),
  'ready_rechecked_under_own_mutex':entry.count('qdrv_f355_ready()')==2 and entry.index('mutex_lock(&f364_control_mutex)')<entry.rindex('qdrv_f355_ready()')<entry.index('qdrv_control_input_serialized'),
  'existing_policy_before_pin_before_dispatch':dispatch.index('qdrv_sequential_precheck')<dispatch.index('qdrv_f355_claim')<dispatch.index('(*s_command_table[found].fn)'),
  'init_commit_after_last_failure':init.index('qdrv_f355_ready_commit')>init.index('qdrv_module_create_sysfs_phy_stats'),
  'partial_init_cleanup':all(s in init for s in ('if(control_initialized)qdrv_control_exit','put_device(&qdrv_device)','dev_attr_lifetime_state')),
  'unload_drains_sysfs_before_proc':exit_body.index('device_remove_file(&qdrv_device,&dev_attr_control)')<exit_body.index('qdrv_control_exit')<exit_body.index('kfree(data)'),
  'unload_never_calls_stop':'qdrv_control_input(' not in exit_body,
  'core_retains_before_reset':core.index('qdrv_f355_core_begin')<core.index('hal_reset();'),
  'no_partial_core_cleanup':'qdrv_soc_exit(' not in core and 'qdrv_f355_boot_failure()' in core,
 }
 for label,name,fn,release in [('soc','qdrv_soc.c','qdrv_soc_exit','qtn_show_info_unregister'),('shared','qdrv_soc.c','qdrv_soc_revoke_params','dma_free_coherent'),('wlan','qdrv_wlan.c','qdrv_wlan_exit','qdrv_wlan_80211_exit'),('hostlink','qdrv_hostlink.c','qdrv_hostlink_exit','flush_scheduled_work')]:
  body=extract((q/name).read_text(),fn);checks[label+'_release_guard']=body.index('qdrv_f355_retained()')<body.index(release)
 require(all(checks.values()),'combination contracts '+str([n for n,v in checks.items() if not v]))
 return checks

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--f363-components-result',required=True,type=Path);ap.add_argument('--qualify-existing',type=Path);args=ap.parse_args()
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 base=json.loads(args.f363_components_result.read_text());sp=json.loads(SOURCE_PROOF.read_text());old=json.loads(F355.read_text())
 require(base['status']=='PASS_OFFLINE_TEMPERATURE_INTEGRATION','F363 component result must really PASS')
 require(sp['status']=='PASS_SOURCE_COMBINATION' and old['status']=='PASS_OFFLINE_PINNED_LIFETIME_COHERENT_CLOSURE','source qualification')
 for row in base['artifacts'].values():require(sha(row['path'])==row['sha256'],'F363 component drift')
 normalized={n.replace('\\','/'):h for n,h in base['source_pins'].items()}
 for name,h in sp['baseline_hashes'].items():require(normalized.get('qdrv-source/'+name)==h,'F363 qdrv source changed '+name)
 for name,h in sp['source_hashes'].items():require(sha(SOURCE/name)==h,'F364 source changed '+name)
 kernel_source_linux=base.get('kernel_source_linux') or linux(base['kernel_source'])
 kernel_output_linux=base.get('kernel_build_directory_linux') or linux(base['kernel_build_directory'])
 base_dir=Path(base.get('completed_build',args.f363_components_result.resolve().parent))
 config=Path(base['artifacts']['f363.config']['path']);require('# CONFIG_MODULE_FORCE_UNLOAD is not set' in config.read_text(),'forced unload enabled')
 module_core=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cat',kernel_source_linux+'/kernel/module.c'],capture_output=True,check=True)
 require(hashlib.sha256(module_core.stdout).hexdigest()==old['kernel_module_c_sha256'],'kernel module lifecycle implementation drift')
 checks=combination_checks()
 for name in ('lifetime','proc_contract'):
  row=old['tests'][name];require(sha(row['path'])==row['sha256'],'reused F355 test evidence drift')
 if args.qualify_existing:
  out=args.qualify_existing.resolve();require(not (out/'result.json').exists(),'immutable completed result')
  isolated='/home/user/openmitrastar-build/'+out.name
  return qualify(out,args,base,sp,old,config,checks,isolated,kernel_source_linux)
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=Path('/workspace/OpenMitraStar-build/f364')/('f364-lifetime-'+stamp);out.mkdir(parents=True,exist_ok=False)
 shutil.copytree(SOURCE,out/'source');shutil.copyfile(base_dir/'a/dependencies.symvers',out/'dependencies.symvers')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');gpl=linux(ROOT/'work/sources/Quantenna-GPL')
 isolated='/home/user/openmitrastar-build/f364-lifetime-'+stamp
 script=f'''set -eu
out={q(linux(out))}
src={q(kernel_source_linux)}
build={q(isolated)}
kout="$build/kernel-context"
tc={q(tc)}
test ! -e "$build"
mkdir "$build"
cp -a --reflink=auto {q(kernel_output_linux)} "$kout"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {sha(config)}
for lane in a b; do
 cp -a "$out/source" "$build/$lane"
 SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build/$lane" QTN_GPL={q(gpl)} KBUILD_EXTRA_SYMBOLS="$out/dependencies.symvers" KCFLAGS="-ffile-prefix-map=$build/$lane=/f364-qdrv" -j4 modules > "$out/build-$lane.log" 2>&1
 mkdir -p "$out/$lane/qdrv"
 cp "$build/$lane/qdrv/qdrv.ko" "$out/$lane/qdrv/qdrv.ko"
 cp "$build/$lane/Module.symvers" "$out/$lane/Module.symvers"
done
cmp "$out/a/qdrv/qdrv.ko" "$out/b/qdrv/qdrv.ko"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {sha(config)}
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr)
 require(run.returncode==0,'qdrv build/reproduction failed: '+str(out))
 return qualify(out,args,base,sp,old,config,checks,isolated,kernel_source_linux)

def qualify(out,args,base,sp,old,config,checks,isolated,kernel_source_linux):
 module=out/'a/qdrv/qdrv.ko';baseline=Path(base['artifacts']['a/temperature/qdrv/qdrv.ko']['path'])
 require(sha(module)==sha(out/'b/qdrv/qdrv.ko'),'paired module bytes differ')
 before,after=qc.normalized_functions(baseline),qc.normalized_functions(module)
 changed=sorted(n for n in set(before)|set(after) if before.get(n)!=after.get(n))
 allowed={'qdrv_control_input','qdrv_control_input_serialized','qdrv_control_init','qdrv_control_exit',
          'qdrv_module_init','qdrv_module_exit','init_module','cleanup_module','qdrv_attr_lifetime_state_show',
          'qdrv_soc_revoke_params','qdrv_soc_publish_params','qdrv_soc_init','qdrv_soc_exit','qdrv_start_dsp_only',
          'qdrv_hostlink_exit','qdrv_wlan_exit','f355_get_reference'}
 unexpected={n for n in changed if n not in allowed and not n.startswith('qdrv_f355_')}
 reviewed={}
 if unexpected:
  require(sha(REVIEW)==REVIEW_SHA,'nonfunctional review not pinned')
  reviewed=json.loads(REVIEW.read_text());require(reviewed['status']=='PASS_REVIEWED_NARROW_NONFUNCTIONAL_DELTA','review status')
  require(reviewed['baseline_module_sha256']==sha(baseline) and reviewed['candidate_module_sha256']==sha(module),'reviewed binaries changed')
  require(unexpected==set(reviewed['functions']),'unreviewed compiled delta '+str(unexpected^set(reviewed['functions'])))
  require(sha(reviewed['disassembly_diff']['path'])==reviewed['disassembly_diff']['sha256'],'reviewed assembly evidence drift')
  for name,proof in reviewed['functions'].items():
   require(proof['baseline']==before[name] and proof['candidate']==after[name] and proof['reviewed_disassembly'],'reviewed function changed '+name)
 for name in ('qdrv_get_internal_temp','qdrv_wps_button_read'):require(before.get(name)==after.get(name),'F363 thermal/WPS machine code changed '+name)
 a,b=qc.inspect(baseline),qc.inspect(module);require(a['parameters']==b['parameters'] and a['functions']==b['functions'],'module profile drift')
 imports,exports=elf_symbols(module);_,old_exports=elf_symbols(baseline);require(exports==old_exports,'qdrv exported ABI drift')
 available={line.split()[1] for file in (Path(base['artifacts']['Module.symvers']['path']),out/'dependencies.symvers') for line in file.read_text().splitlines() if line.strip()}
 require(imports<=available,'unresolved imports '+str(imports-available))
 for name,h in sp['source_hashes'].items():require(sha(out/'source'/name)==h and sha(SOURCE/name)==h,'F364 build source drift')
 result={'schema':'openmitrastar.f364-lifetime-component/v1','status':'PASS_OFFLINE_F363_PLUS_F355_LIFETIME',
         'artifact':item(module),'f363_components':item(args.f363_components_result),'source_manifest':item(SOURCE_PROOF),
         'f355_qualification':item(F355),'reused_tests':old['tests'],'combination_checks':checks,
         'compiled_function_delta':changed,'thermal_and_wps_functions_byte_equivalent':True,
         'nonfunctional_delta_review':item(REVIEW) if reviewed else None,
         'nonfunctional_functions':sorted(unexpected),'no_rebuild_during_qualification':bool(args.qualify_existing),
         'parameter_profile_unchanged':True,'exports_unchanged':True,'imports_resolved':len(imports),
         'reproducible':True,'kernel_config_sha256':sha(config),'kernel_recompiled':False,
         'isolated_module_context':isolated,'kernel_source_readonly':kernel_source_linux,
         'permanent_pin_release_supported':False,'hot_restart_supported':False,
         'hardware_actions':False,'new_radio_modes_enabled':False,'f363_image_required_for_composition':True}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'artifact':result['artifact']},indent=2))
if __name__=='__main__':main()
