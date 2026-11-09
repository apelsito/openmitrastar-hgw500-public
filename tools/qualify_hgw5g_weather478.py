"""34originalrecords sourceclosure preserving32 and boundedweatherpolicy only."""
import argparse,hashlib,json
from pathlib import Path
from audit_hgw5g_weather478_modules import audit
from qualify_f370_qdrv_module import Elf
from recover_hgw5g_driver_ops import Elf as OpsElf
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(p):
 s=str(p).replace('\\','/')
 if len(s)>2 and s[1]==':':s='/mnt/'+s[0].lower()+s[2:]
 return Path(s)if s.startswith('/')else ROOT/s
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--pair',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);pins={};r=dict(status='NO_GO_WEATHER478_SOURCE34_QUALIFICATION',hardware_accessed=False,firmware_eligible=False)
 try:
  def read(p):p=Path(p);pins[str(p)]=sha(p);return json.loads(p.read_text())
  def import_pins(p):
   for path,h in read(p).items():path=norm(path);assert sha(path)==h,'drift '+str(path);pins[str(path)]=h
  parent=ROOT/'outputs/rea/consolidated32-source-20261022T222600Z-r2';pm=ROOT/'outputs/rea/consolidated32-pair-20261022T223400Z-r2/a-joint';pc=ROOT/'outputs/rea/consolidated32-global-checkpoint-20261022T224200Z-r2';pq=read(pc/'result.json');assert pq['status']=='PASS_OFFLINE_CONSOLIDATED32_SCANNER_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT'and pq['offline_original_records_reconstructed']==32;import_pins(pc/'input-pins.json')
  cp=read(a.candidate/'result.json');assert cp['source_original_records']==34;allowed={'headers/net80211/ieee80211_var.h','source/qdrv/qdrv_wlan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c'};assert set(cp['changed_sources'])==allowed
  for f in('source','headers'):
   old={p.relative_to(parent).as_posix():sha(p)for p in(parent/f).rglob('*')if p.is_file()};new={p.relative_to(a.candidate).as_posix():sha(p)for p in(a.candidate/f).rglob('*')if p.is_file()};assert set(old)==set(new)and{k for k in old if old[k]!=new[k]}==allowed.intersection(old)
   for rel,h in new.items():pins[str(a.candidate/rel)]=h
  removals={'headers/net80211/ieee80211_var.h':[(' u8 om_weather_cac_enabled; /* OEM478: former padding. */','')],'source/qdrv/qdrv_wlan.c':[('\tic->om_weather_cac_enabled = 0;\n','')],'source/wlan/ieee80211_scan_ap.c':[('\t\tif (!READ_ONCE(ic->om_weather_cac_enabled) &&\n\t\t    ieee80211_is_on_weather_channel(ic, ic_best_chan)) {','\t\tif (ieee80211_is_on_weather_channel(ic, ic_best_chan)) {')],'source/wlan/ieee80211_wireless.c':[('#define OM_OEM_PARAM_WEATHER_CAC_ENABLE 478\n',''),('\n\tcase OM_OEM_PARAM_WEATHER_CAC_ENABLE:\n\t\tWRITE_ONCE(ic->om_weather_cac_enabled,!!value);\n\t\treturn 0;\n',''),('\n\tcase OM_OEM_PARAM_WEATHER_CAC_ENABLE:\n\t\tparam[0]=READ_ONCE(ic->om_weather_cac_enabled);\n\t\treturn 0;\n',''),('\n\t{OM_OEM_PARAM_WEATHER_CAC_ENABLE,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,0,"wea_cac_en"},\n\t{OM_OEM_PARAM_WEATHER_CAC_ENABLE,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"get_wea_cac_en"},','')]}
  for rel,subs in removals.items():
   text=(a.candidate/rel).read_text();assert sha(a.candidate/rel)==cp['changed_sources'][rel]
   for old,new in subs:assert text.count(old)==1;text=text.replace(old,new,1)
   assert text==(parent/rel).read_text(),'sourceinverse '+rel
  b=read(a.pair/'result.json');assert b['status']=='PASS_WEATHER478_SOURCE34_THREE_UNITS_PAIRED_SEVEN_MODULES_PENDING_GLOBAL'and b['new_compiled_units']==6 and b['exact_parent32_objects_reused']==110 and b['reproducible'];import_pins(a.pair/'input-pins.json');mods=[]
  for lane in('a','b'):
   d=a.pair/(lane+'-joint');v=read(d/'result.json');assert v['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'and v['complete_modules']==7 and v['modpost_diagnostics']=='empty';import_pins(d/'input-pins.json');mods.append(v)
  receipts={};directories={'abi':'weather478-all-abi-20261022T234000Z-r1','default':'weather478-default-proof-20261022T235200Z-r1','consumers':'weather478-actual-consumers-20261022T210300Z-r2','policy461':'weather478-policy461-20261022T235600Z-r1','negative':'weather478-negative-20261022T235700Z-r2'};statuses={'abi':'PASS_ARC_WEATHER478_ALL_OLD_FIELDS_WIRE_SIZES_FORMER_PADDING22605','default':'PASS_WEATHER478_OEM_ZERO_INIT_BOOLEAN_AP_SOURCE_DEFAULT_FRAGMENTS','consumers':'PASS_WEATHER478_ACTUAL_AP_POLICY_AND_WEXT_SOURCE_CONSUMERS','policy461':'PASS_CONSOLIDATED32_ACTUAL_461_WEXT_SCANNER_POLICY_FIXTURE','negative':'PASS_SIXTEEN_WEATHER478_PARSED_NEGATIVE_DELTA_CASES'}
  for key,name in directories.items():
   d=ROOT/'outputs/rea'/name;v=read(d/'result.json');assert v['status']==statuses[key]
   if(d/'input-pins.json').exists():import_pins(d/'input-pins.json')
   if(d/'ap-policy/input-pins.json').exists():import_pins(d/'ap-policy/input-pins.json')
   for path,h in v.get('pins',{}).items():path=norm(path);assert sha(path)==h;pins[str(path)]=h
   for path in d.rglob('*'):
    if path.is_file():pins[str(path)]=sha(path)
   receipts[key]=v
  assert receipts['abi']['host_delta']==0 and receipts['abi']['rows'][1]['extensions']['weather478']=={'offset':22605,'size':1};assert receipts['default']['constructor_cases']==256 and receipts['consumers']['ap_policy_cases']==57344 and receipts['consumers']['wext_cases']==655360 and receipts['policy461']['cases']==262144 and receipts['negative']['cases']==16
  reports={}
  for c in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
   op=pm/c/(c+'.ko');fp=a.pair/'a-joint'/c/(c+'.ko');sp=a.pair/'b-joint'/c/(c+'.ko');assert sha(fp)==sha(sp);pins[str(op)]=sha(op);pins[str(fp)]=pins[str(sp)]=sha(fp)
   if c in('qdrv','wlan','wlan_scan_ap'):reports[c]=audit(Elf(op),Elf(fp),c)
   else:assert sha(op)==sha(fp);reports[c]=dict(status='BYTE_IDENTICAL_WHOLE_PARENT32_MODULE',sha256=sha(fp))
  old=OpsElf(pm/'wlan/wlan.ko').ioctl_records();new=OpsElf(a.pair/'a-joint/wlan/wlan.ko').ioctl_records();assert len(old)==598 and new[:598]==old and [(r['cmd'],r['set_args'],r['get_args'],r['name'])for r in new[598:]]==[(478,18433,0,'wea_cac_en'),(478,0,18433,'get_wea_cac_en')]
  for path in[Path(__file__),Path(__file__).with_name('audit_hgw5g_weather478_modules.py'),Path(__file__).with_name('build_hgw5g_weather478_pair.py'),Path(__file__).with_name('prepare_hgw5g_weather478_source.py')]:pins[str(path)]=sha(path)
  assert all(sha(p)==h for p,h in pins.items());(a.output/'complete-module-audit.json').write_text(json.dumps(reports,indent=2)+'\n');(a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes());r.update(status='PASS_OFFLINE_WEATHER478_SOURCE34_BOOLEAN_AP_SELECTION_SEVEN_MODULE_CLOSURE',complete_original_records=34,remaining_original_records=10,private_table_records=600,old_private_records_exact=598,reproducible=True,all_461_hooks_preserved=True,cac_radar_600s_source_paths_unchanged=True,weather_flag_offset=22605,weather_flag_size=1,weather_default=0,fresh_source_compiles=6,parent32_whole_objects_reused=110,ap_policy_cases=57344,wext_cases=655360,default_fragment_cases=256,policy461_cases=262144,all_old_members_checked=receipts['abi']['old_members_checked'],negative_cases=16,current_pins_verified=len(pins),modules=mods[0]['modules'],inherited_limits=pq['limits'],limits=cp['limits']+receipts['default']['limits']+['WholeAPsource20MHzfakecheck/alternatecallbacks;notallOEMmetric/width/rankequivalence','Setterboolall32bitvalue→u8read/write exactly; noRF/CACtimer/radar/regulatoryacceptance','No467includedinSOURCE34; jointboundedcombine separate','NoHW/client/traffic/coldboot/persistence/rollback/releaseacceptance'])
 except Exception as ex:r['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return int(not r['status'].startswith('PASS_'))
if __name__=='__main__':raise SystemExit(main())
