"""Compile ARC layout witnesses for old/new host headers; no runtime access."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shlex,struct,subprocess
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--closure',required=True,type=Path);a=ap.parse_args();manifest=json.loads(a.closure.read_text());base=a.closure.parent
 out=ROOT/'outputs/preflight'/('f344-host-wire-abi-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 qdir=base/'a/qdrv/qdrv';cmd=shlex.split((qdir/'.qdrv_control.o.cmd').read_text().splitlines()[0].split(' := ',1)[1]);clean=[];skip=False
 for arg in cmd:
  if skip:skip=False;continue
  if arg=='-o':skip=True;continue
  if arg=='-c' or arg.startswith('-Wp,') or arg.endswith('/qdrv_control.c'):continue
  clean.append(arg)
 expressions=[
  ('host_ioctl.size','sizeof(struct host_ioctl)'),('host_ioctl.arg','offsetof(struct host_ioctl,ioctl_arg1)'),
  ('shared_params.size','sizeof(struct shared_params)'),('shared_params.csa','offsetof(struct shared_params,csa_lhost)'),
  ('qtn_csa_info.size','sizeof(struct qtn_csa_info)'),('qtn_csa_info.muc_status','offsetof(struct qtn_csa_info,muc_status)'),('qtn_csa_info.lhost_status','offsetof(struct qtn_csa_info,lhost_status)'),
  ('qtn_remain_chan_info.size','sizeof(struct qtn_remain_chan_info)'),
  ('ioctl.key','sizeof(struct ieee80211req_key)'),('ioctl.mlme','sizeof(struct ieee80211req_mlme)'),('ioctl.chanlist','sizeof(struct ieee80211req_chanlist)'),('ioctl.sta_info','sizeof(struct ieee80211req_sta_info)'),('ioctl.scan_result','sizeof(struct ieee80211req_scan_result)'),
  ('host.vap.size','sizeof(struct ieee80211vap)'),('host.ic_vaps','offsetof(struct ieee80211com,ic_vaps)'),('host.ic_curchan','offsetof(struct ieee80211com,ic_curchan)'),('host.ic_scan','offsetof(struct ieee80211com,ic_scan)'),('host.ic_timer_csa','offsetof(struct ieee80211com,ic_timer_csa)'),('host.ic_set_channel','offsetof(struct ieee80211com,ic_set_channel)'),
  ('host.ic_size','sizeof(struct ieee80211com)')]
 prefix=(qdir/'qdrv_control.c').read_text().split('static const struct qtn_auc_stat_field',1)[0]
 scripts=[]
 for lane in ('old','new'):
  extra='offsetof(struct ieee80211com,ic_f344_channel_allowed)' if lane=='new' else 'sizeof(struct ieee80211com)'
  source=prefix+'\nconst unsigned f344_layout[]={'+','.join(e for _,e in expressions)+','+extra+'};\n'
  (out/(lane+'.c')).write_bytes(source.encode())
  args=[v for v in clean if lane=='new' or not(v.startswith('-I') and v.endswith('/headers'))]
  args+=['-I'+linux(qdir),'-c',linux(out/(lane+'.c')),'-o',linux(out/(lane+'.o'))]
  scripts.append(' '.join(shlex.quote(v) for v in args))
 (out/'run.sh').write_bytes(('set -eu\ncd '+shlex.quote(manifest['isolated_module_context'])+'\n'+'\n'.join(scripts)+'\n').encode())
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=60)
 errors=[];values={}
 if p.returncode:errors.append('ARC layout witness compilation failed')
 else:
  for lane in ('old','new'):
   with (out/(lane+'.o')).open('rb') as f:
    e=ELFFile(f);symbol=e.get_section_by_name('.symtab').get_symbol_by_name('f344_layout')[0];section=e.get_section(symbol['st_shndx']);data=section.data()[symbol['st_value']:symbol['st_value']+symbol['st_size']];nums=struct.unpack('<'+'I'*(len(data)//4),data)
   values[lane]={name:value for (name,_),value in zip(expressions,nums)};values[lane]['extension_start']=nums[-1]
  for key in values['old']:
   if key!='host.ic_size' and values['old'][key]!=values['new'][key]:errors.append('wire/prefix layout changed '+key)
  if values['new']['host.ic_size']<=values['old']['host.ic_size']:errors.append('host extension missing')
  if 'ieee80211_f344_policy_abi_v1' not in manifest['modules']['qdrv']['imports']:errors.append('ABI marker dependency missing')
 result={'schema':'openmitrastar.f344-host-wire-abi/v1','status':'PASS_HOST_APPEND_WIRE_LAYOUT_UNCHANGED' if not errors else 'FAIL','errors':errors,'values':values,'closure_sha256':hashlib.sha256(a.closure.read_bytes()).hexdigest(),'stderr':p.stderr[-5000:],'hardware':False,'wire_generation_added':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
