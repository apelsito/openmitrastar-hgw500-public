#!/usr/bin/env python3
"""Current portable Linux 7.3 complete driver/providers build. --plan-only is read-only.

Only caller-supplied local sources/toolchain are used. No download, installation,
router access, firmware packing, Git mutation, or access to private owner assets.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path

GCC_SHA='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
BASE_COMMIT='c03c1a14507dfaf8b856c2608f9ac216021fc222'
EPOCH='1792365298'
GROUPS=('source','headers','providers','kernel-overlay')
MANDATORY_CONFIG={'OPENMITRASTAR_QDRV_COMPAT':'y','WIRELESS_EXT':'y','WEXT_CORE':'y','WEXT_PRIV':'y','NET_SCHED':'y','BRIDGE':'m','GPIOLIB':'y','I2C':'y','CRYPTO_LIB_AES':'m','CFG80211_REQUIRE_SIGNED_REGDB':'y','CFG80211_USE_KERNEL_REGDB_KEYS':'y','CFG80211':'m','MAC80211':'m','RTL8192EE':'m'}
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def safe_relative(value):
 p=Path(value.replace('\\','/'))
 if p.is_absolute()or '..'in p.parts:raise ValueError('Unsafe manifest member: '+value)
 return p
def require(condition,message):
 if not condition:raise ValueError(message)
def arguments():
 p=argparse.ArgumentParser(description=__doc__)
 for name in('driver-source','kernel-source','kernel-context','gpl-root','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--toolchain-prefix',required=True,help='Absolute executable prefix ending in arc-snps-linux-uclibc-')
 p.add_argument('--compiler-sha256',default=GCC_SHA)
 p.add_argument('--expected-config-sha256',required=True,help='Exact SHA256 of the supplied base .config')
 p.add_argument('--expected-kernel-makefile-sha256',required=True)
 p.add_argument('--expected-kernel-commit',default=BASE_COMMIT,help='Required base Git HEAD when supplied kernel source has .git')
 p.add_argument('--jobs',type=int,default=2)
 modes=p.add_mutually_exclusive_group(required=True);modes.add_argument('--plan-only',action='store_true');modes.add_argument('--prepare-only',action='store_true');modes.add_argument('--build',action='store_true')
 return p.parse_args()
def inspect(a):
 paths={name:getattr(a,name).resolve()for name in('driver_source','kernel_source','kernel_context','gpl_root','output')}
 d,k,c,g,o=(paths[n]for n in('driver_source','kernel_source','kernel_context','gpl_root','output'))
 require(not o.exists(),'Output must be a new directory: '+str(o));require(1<=a.jobs<=32,'jobs must be 1..32')
 for root in(d,k,c,g):require(o!=root and root not in o.parents,'Output must be outside every input tree')
 require(all(not any(ch.isspace()for ch in str(root))for root in(d,k,c,g,o)),'Use Linux paths without whitespace for all Kbuild inputs and output')
 for root in(d,k,c,g):require(root.is_dir(),'Missing input directory: '+str(root))
 for name in GROUPS:require((d/name).is_dir(),'Driver package incomplete: '+name)
 for relative in('Makefile','scripts/config','scripts/Makefile.build','include/crypto/aes.h','include/linux/proc_fs.h'):require((k/relative).is_file(),'Kernel package incomplete: '+relative)
 for relative in('common','drivers/include/shared','drivers/include/kernel','include/qtn'):require((g/relative).is_dir(),'GPL header source incomplete: '+relative)
 require((d/'Kbuild').is_file()and(d/'result.json').is_file(),'Driver Kbuild/result.json absent')
 require(sha(c/'.config')==a.expected_config_sha256,'Base config SHA256 mismatch')
 require(sha(k/'Makefile')==a.expected_kernel_makefile_sha256,'Kernel Makefile SHA256 mismatch')
 mk=(k/'Makefile').read_text();require(re.search(r'^VERSION\s*=\s*7\s*$',mk,re.M)and re.search(r'^PATCHLEVEL\s*=\s*3\s*$',mk,re.M),'Kernel source is not Linux 7.3')
 compiler=Path(a.toolchain_prefix+'gcc');require(compiler.is_file(),'Compiler absent: '+str(compiler));require(sha(compiler)==a.compiler_sha256,'Compiler SHA256 mismatch')
 for suffix in('ld','nm','objdump','readelf'):require(Path(a.toolchain_prefix+suffix).is_file(),'Toolchain utility absent: '+suffix)
 cfg=(c/'.config').read_text()
 for key in('ARC_CPU_750D','ARC_MMU_V2','ARC_PAGE_SIZE_8K','ARC_PLAT_TOPAZ_BASIC','MODULES'):require('CONFIG_'+key+'=y'in cfg,'Required base config missing: '+key)
 require('CONFIG_SMP=y'not in cfg and 'CONFIG_MODULE_FORCE_UNLOAD=y'not in cfg,'Unsupported SMP or forced module unload config')
 require((c/'Module.symvers').is_file(),'Base Module.symvers required as reference; it will not substitute the new build')
 commit_check='DECLARED_BASE_COMMIT_NO_GIT_METADATA'
 if(k/'.git').exists():
  head=subprocess.check_output(['git','-C',str(k),'rev-parse','HEAD'],text=True).strip();require(head==a.expected_kernel_commit,'Kernel Git HEAD mismatch')
  commit_check='VERIFIED_GIT_HEAD'
 proof=json.loads((d/'result.json').read_text());files=proof.get('files',{});require(files,'Driver package has no hashed source manifest')
 if proof.get('kbuild_sha256'):require(sha(d/'Kbuild')==proof['kbuild_sha256'],'Driver Kbuild SHA256 mismatch')
 count=0;manifest_members=set()
 for rel,h in files.items():
  member=safe_relative(rel);path=d/member;require(path.is_file(),'Manifest file missing: '+rel);require(sha(path)==h,'Driver input hash mismatch: '+rel);count+=1;manifest_members.add(member.as_posix())
 actual_members={p.relative_to(d).as_posix()for group in GROUPS for p in(d/group).rglob('*')if p.is_file()}
 require(actual_members==manifest_members,'Driver manifest does not cover the complete source/header/provider/overlay package')
 forbidden=[p for group in('source','headers','providers')for p in(d/group).rglob('*')if p.is_file()and(p.suffix in('.o','.ko','.pem','.key')or p.name in('Module.symvers','modules.order'))]
 require(not forbidden,'Source package includes old binaries or private key assets')
 overlay={p.relative_to(d/'kernel-overlay').as_posix():sha(p)for p in(d/'kernel-overlay').rglob('*')if p.is_file()}
 require(overlay,'Kernel ABI overlay absent')
 for rel,h in proof.get('kernel_overlay',{}).items():require(overlay.get(safe_relative(rel).as_posix())==h,'Kernel overlay metadata mismatch: '+rel)
 build=(d/'Kbuild').read_text();objects=re.findall(r'(?:source|providers)/[A-Za-z0-9_./-]+\.o',build)
 declared_modules=set(re.findall(r'\b([A-Za-z0-9_]+)\.o\b',' '.join(l for l in build.splitlines()if re.match(r'^obj-m\s*\+=',l))))
 members={name:set(re.findall(r'(?:source|providers)/[A-Za-z0-9_./-]+\.o',rhs))for name,rhs in re.findall(r'^([A-Za-z0-9_]+)-y\s*:=\s*(.*)$',build,re.M)}
 require(declared_modules and declared_modules==set(members),'Every declared module needs exactly one validated source membership list')
 require(all(members.values()),'Empty module object membership')
 referenced=set().union(*members.values());require(referenced==set(objects),'Unowned or duplicate-declaration Kbuild source paths')
 for obj in referenced:require((d/(obj[:-2]+'.c')).is_file(),'Missing Kbuild source: '+obj)
 for name in declared_modules:
  init_sources=sum(bool(re.search(r'\bmodule_init\s*\(', (d/(obj[:-2]+'.c')).read_text()))for obj in members[name]);require(init_sources<=1,'Multiple module_init sources in '+name)
 for name in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):require(re.search(r'^'+name+r'-y\s*:=',build,re.M),'Kbuild module missing: '+name)
 require('qtn73_support-y'not in build,'Providers with separate module_init must be separate modules')
 required_config=dict(MANDATORY_CONFIG)
 for item in proof.get('new_kernel_config_required',[]):
  match=re.fullmatch(r'(?:CONFIG_)?([A-Z0-9_]+)=(y|m|n)',item);require(match is not None,'Invalid source config requirement: '+item);key,value=match.groups()
  if key in required_config:require(required_config[key]==value,'Source manifest conflicts with required safety config: '+item)
  required_config[key]=value
 require('CONFIG_CFG80211_REQUIRE_SIGNED_REGDB=y'in cfg,'Current kernel base must preserve signed regulatory DB verification')
 ccmp=(d/'source/wlan/ieee80211_crypto_ccmp.c').read_text();require('aes_prepareenckey('in ccmp and'aes_encrypt('in ccmp and'crypto_alloc_cipher('not in ccmp,'CCMP is not adapted to Linux 7.3 libaes')
 compat=(d/'source/qdrv/compat/include/openmitrastar_qdrv_compat.h').read_text();require('pde_data('in compat and'om_linux73_strlcpy'in compat,'Proc/string compatibility missing')
 for marker in('struct_group(headers','qtn_cb','orig_dev','recycle_list'):require(marker in(d/'kernel-overlay/include/linux/skbuff.h').read_text(),'Packet ABI overlay missing: '+marker)
 inputs={str(p):sha(p)for p in(d/'result.json',d/'Kbuild',k/'Makefile',c/'.config',c/'Module.symvers',compiler,Path(__file__).resolve())}
 return paths,{'schema':'openmitrastar.linux73-portable-build-current/v2','status':'PASS_PLAN_ONLY_CURRENT_INPUTS_AND_ALL_MODULE_MEMBERS_VALIDATED','hardware_accessed':False,'firmware_eligible':False,'driver_manifest_files_checked':count,'kbuild_source_units':len(referenced),'kbuild_modules':{name:sorted(members[name])for name in sorted(declared_modules)},'required_kernel_config':required_config,'upstream_kernel_commit':a.expected_kernel_commit,'kernel_commit_check':commit_check,'inputs':inputs,'overlay':overlay,'base_config_reference_only':True,'old_objects_reused':False,'driver_private_key_assets_found':False,'private_runtime_assets_requested':False,'kernel_DT_privacy_not_audited':True}
def commands(a,paths):
 o=paths['output'];kernel=o/'kernel-source';context=o/'kernel-context';module=o/'driver';base=['make','-C',str(kernel),'O='+str(context),'ARCH=arc','CROSS_COMPILE='+a.toolchain_prefix]
 return [base+['olddefconfig'],base+['modules_prepare'],base+['-j'+str(a.jobs),'vmlinux','dtbs','modules'],base+['M='+str(module),'QTN_GPL='+str(paths['gpl_root']),'-j'+str(a.jobs),'modules']]
def prepare(a,paths,r):
 o=paths['output'];o.mkdir(parents=True);k=o/'kernel-source';c=o/'kernel-context';m=o/'driver'
 shutil.copytree(paths['kernel_source'],k,ignore=shutil.ignore_patterns('.git'))
 for rel,h in r['overlay'].items():
  src=paths['driver_source']/'kernel-overlay'/safe_relative(rel);dst=k/safe_relative(rel);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);require(sha(dst)==h,'Overlay copy mismatch')
 c.mkdir();cfg=(paths['kernel_context']/'.config').read_text()
 # This build produces kernel/module artifacts only. Private boot initramfs,
 # credentials, firmware and owner DT data are integrated through separate gates.
 changes=r['required_kernel_config']|{'INITRAMFS_SOURCE':'""'}
 for key,val in changes.items():cfg=re.sub(r'(?m)^(?:CONFIG_'+key+r'=.*|# CONFIG_'+key+r' is not set)\n','',cfg);cfg+='CONFIG_'+key+'='+val+'\n'
 (c/'.config').write_text(cfg);m.mkdir()
 for group in('source','headers','providers'):shutil.copytree(paths['driver_source']/group,m/group)
 kbuild=(paths['driver_source']/'Kbuild').read_text();kbuild=re.sub(r'^QTN_GPL\s*[:?+]?=.*$', 'QTN_GPL ?= $(src)/original-Quantenna-GPL',kbuild,flags=re.M);(m/'Kbuild').write_text(kbuild)
 # Never copy .o/.ko/metadata from the supplied source bundle into a new build.
 forbidden=[p for p in m.rglob('*')if p.is_file()and(p.suffix in('.o','.ko')or p.name in('Module.symvers','modules.order'))];require(not forbidden,'Source package includes old build artifacts')
 r.update(status='PASS_PREPARED_FRESH_LINUX73_KERNEL_AND_DRIVER_SOURCES',output=str(o),private_initramfs_excluded=True)
def main():
 a=arguments()
 try:
  paths,r=inspect(a);r['commands']=commands(a,paths)
  if a.plan_only:print(json.dumps(r,indent=2));return 0
  require(os.name=='posix','Preparation/build requires Linux or WSL')
  prepare(a,paths,r);out=paths['output'];(out/'build-inputs.json').write_text(json.dumps(r,indent=2)+'\n')
  if a.build:
   env=os.environ|{'SOURCE_DATE_EPOCH':EPOCH,'KBUILD_BUILD_TIMESTAMP':'@'+EPOCH,'KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'aelita73','KBUILD_BUILD_VERSION':'1'}
   for i,cmd in enumerate(r['commands']):
    with(out/f'{i:02d}-build.log').open('xb')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True)
   cfg=(out/'kernel-context/.config').read_text()
   for key,val in r['required_kernel_config'].items():require(('CONFIG_'+key+'='+val if val!='n'else'# CONFIG_'+key+' is not set')in cfg,'Final Kconfig omitted or changed '+key)
   require((out/'kernel-context/Module.symvers').is_file(),'New kernel Module.symvers absent')
   modules=list((out/'kernel-context').rglob('*.ko'))+list((out/'driver').rglob('*.ko'))
   required=set(r['kbuild_modules'])|{'cfg80211','mac80211','rtl8192ee','libaes','bridge'}
   require(required<={p.stem for p in modules},'Expected current driver/provider/base modules absent: '+str(sorted(required-{p.stem for p in modules})))
   for module in modules:
    asm=subprocess.check_output([a.toolchain_prefix+'objdump','-d',str(module)],text=True);require(not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),'Forbidden ARC instruction: '+str(module))
   r.update(status='PASS_SINGLE_LINUX73_KERNEL_AND_MODULE_BUILD_PENDING_PAIR_ABI_AND_PHYSICAL_GATES',modules=[{'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':sha(p)}for p in modules])
  r['limits']=['Offline source/build only. Reproducible second build, full import/export/ABI and regression audits are separate.','All base kernel modules and QDRV/WLAN must be rebuilt after packet ABI changes.','No boot image, private owner asset, firmware write, RF/client or release acceptance.'];(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2));return 0
 except Exception as e:print(json.dumps({'status':'NO_GO_LINUX73_PORTABLE_BUILD','error':str(e),'hardware_accessed':False}),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
