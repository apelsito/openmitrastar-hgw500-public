"""Qualify Coex26 incremental module closure, immutable proofs and residuals."""
import argparse
import hashlib
import json
from pathlib import Path
from audit_hgw5g_coex26_r3_modules import audit
from qualify_f370_qdrv_module import Elf
from recover_hgw5g_driver_ops import Elf as OpsElf

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(p):
 s=str(p).replace('\\','/')
 if len(s)>2 and s[1]==':':s='/mnt/'+s[0].lower()+s[2:]
 return Path(s)if s.startswith('/')else ROOT/s

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--first',type=Path,required=True);p.add_argument('--second',type=Path,required=True);p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);pins={};result=dict(status='NO_GO_COEX26_CLOSURE',hardware_accessed=False,firmware_eligible=False)
 try:
  def read(path):path=Path(path);raw=path.read_bytes();pins[str(path)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
  def import_pins(path):
   for p,h in read(path).items():p=norm(p);assert sha(p)==h,'input drift '+str(p);pins[str(p)]=h
  parent=ROOT/'outputs/rea/coc491-source25-postcompletion-20261022T181500Z-r6';parentmods=ROOT/'outputs/rea/driver5g-ops-20261022-coc25-joint-a-r6';pq=read(ROOT/'outputs/rea/driver5g-ops-20261022-coc25-qualification-r6/result.json');assert pq['status']=='PASS_OFFLINE_COC25_INITIALIZED_RETAINED_IC_SEVEN_MODULE_CLOSURE'
  br=read(a.build/'result.json');assert br['status']=='PASS_COEX26_INPUT_REVISION_PAIRED_SOURCE_CLOSURE'and br['new_input_compiles']==2 and br['retained_source26_changed_compiles']==6 and br['qualified_parent_whole_units_reused']==108 and br['reproducible'];import_pins(a.build/'input-pins.json')
  mods=[read(d/'result.json')for d in(a.first,a.second)];assert all(r['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'and r['complete_modules']==7 and r['modpost_diagnostics']=='empty'for r in mods)
  for d in(a.first,a.second):import_pins(d/'input-pins.json')
  cp=read(a.candidate/'result.json');assert cp['total_original_entries_added']==26 and cp['old_header_lines_preserved']
  for rel,h in cp['changed_sources'].items():file=a.candidate/rel;assert sha(file)==h;pins[str(file)]=h
  abi_dir=ROOT/'outputs/rea/coex449-source26-full-abi-20261022T192100Z-r2';abi=read(abi_dir/'result.json');assert abi['status']=='PASS_ARC_COEX26_ALL_OLD_FIELDS_WIRE_SIZES_PADDING_BYTE'and abi['host_delta']==0;import_pins(abi_dir/'input-pins.json');assert abi['rows'][1]['extensions']==[22667,1]
  old=(parent/'headers/net80211/ieee80211_var.h').read_text();new=(a.candidate/'headers/net80211/ieee80211_var.h').read_text();normalized=new.replace('\tbool om_coc_pm_pending; u8 om_20_40_bss_coex; /* OEM449: prior padding. */','\tbool om_coc_pm_pending;').replace('void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap); void om_ieee80211_change_bw(struct ieee80211vap *vap,int bw,int delay_ch_switch);','void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap);');assert normalized==old and len(new.splitlines())==len(old.splitlines())==2327
  evidence=[('coex449-source26-public-action-20261022T191600Z-r1','PASS_ACTUAL_COEX449_PUBLIC_ACTION_LENGTH_POLICY_CONSUMER'),('coex449-source26-policy-consumers-20261022T191800Z-r2','PASS_ACTUAL_COEX26_TIMER_SCAN_ASSOC_STA_OBSS_CONSUMER_FIXTURE'),('coex449-source26-setter-20261022T192300Z-r1','PASS_ACTUAL449_BOOL_SETTER_NO_OTHER_MUTATION'),('coex449-changebw-fixture-20261022T191100Z-r1','PASS_ACTUAL_CHANGE_BW_WIRE_MAP_POWER_CALLBACK_HOST_FIXTURE'),('coex449-changebw-arc-20261022T191200Z-r1','PASS_ARC_ACTUAL_TYPED_CHANGE_BW_HELPER')];proof=[]
  for folder,status in evidence:
   d=ROOT/'outputs/rea'/folder;r=read(d/'result.json');assert r['status']==status;proof.append(r);import_pins(d/'input-pins.json')
   for f in d.iterdir():
    if f.is_file():pins[str(f)]=sha(f)
  assert proof[0]['source_sha256']==sha(ROOT/'outputs/rea/coex449-source26-stable-lines-20261022T192000Z-r2/source/wlan/ieee80211_input.c')and proof[2]['source_sha256']==sha(a.candidate/'source/wlan/ieee80211_wireless.c')
  current_input=(a.candidate/'source/wlan/ieee80211_input.c').read_text();start=current_input.index('static void\nieee80211_recv_action_public_coex(');end=current_input.index('/*\n * Process a public action frame',start);assert hashlib.sha256(current_input[start:end].encode()).hexdigest()==proof[0]['function_sha256'],'prior public-parser body differs from current source'
  helper=(ROOT/'outputs/rea/coex449-changebw-helper-20261022T191000Z-r1/om_coex449_change_bw.c').read_text();assert helper in(a.candidate/'source/wlan/ieee80211_node.c').read_text();assert hashlib.sha256(helper.encode()).hexdigest()==proof[3]['source_sha256']==cp['helper_sha256']
  geometry=[]
  for folder,status in [('coex449-source26-bss-geometry-fixture-20261022T192700Z-r1','PASS_ACTUAL_COEX26_OEM_BSS_LOW16_SIGNED8_GEOMETRY'),('coex449-source26-public-bss-geometry-20261022T192800Z-r2','PASS_ACTUAL_COEX26_PUBLIC_PARSER_WITH_BSS_GEOMETRY')]:
   d=ROOT/'outputs/rea'/folder;r=read(d/'result.json');assert r['status']==status and r['source_sha256']==sha(a.candidate/'source/wlan/ieee80211_input.c');geometry.append(r);import_pins(d/'input-pins.json')
   for f in d.iterdir():
    if f.is_file():pins[str(f)]=sha(f)
  review=read(a.review);assert review['status']=='PASS_INDEPENDENT_COEX26_R3_BSS_GEOMETRY_AND_CONSUMER_SOURCE_SCOPE_PENDING_MODULES'and not review['hardware_accessed'];
  for row in review.get('evidence_pins',[]):file=norm(row['path']);assert sha(file)==row['sha256'];pins[str(file)]=row['sha256']
  negative_dir=ROOT/'outputs/rea/driver5g-ops-20261022-coex26-r3-negative-audit-r1';negative=read(negative_dir/'result.json');assert negative['status']=='PASS_ELEVEN_SOURCE26_R3_PARSED_NEGATIVE_DELTA_CASES'and negative['cases']==11;import_pins(negative_dir/'input-pins.json')
  reports={}
  for component in('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
   fp=a.first/component/(component+'.ko');sp=a.second/component/(component+'.ko');op=parentmods/component/(component+'.ko');assert sha(fp)==sha(sp);pins[str(fp)]=pins[str(sp)]=sha(fp);pins[str(op)]=sha(op)
   if component in('qdrv','wlan'):reports[component]=audit(Elf(op),Elf(fp),component)
   else:assert sha(fp)==sha(op);reports[component]=dict(status='BYTE_IDENTICAL_WHOLE_PARENT_PROVIDER',sha256=sha(fp))
  oldops=OpsElf(parentmods/'wlan/wlan.ko').ioctl_records();newops=OpsElf(a.first/'wlan/wlan.ko').ioctl_records();assert newops[:591]==oldops and[(r['cmd'],r['set_args'],r['get_args'],r['name'])for r in newops[591:]]==[(449,18433,0,'20_40_bss_coex')]
  for name in('windows-oem-coex449-changebw-20261022T190000Z-r1','windows-oem-coex449-power-helper-20261022T190200Z-r1','windows-oem-coex449-starttimer-20261022T190300Z-r1','windows-oem-coex449-check40-20261022T190300Z-r1'):
   d=ROOT/'outputs/rea'/name;r=read(d/'result.json');assert r['exit_code']==0 and r['target_unchanged'];pins[str(d/'rea.json')]=r['rea_output_sha256'];assert sha(d/'rea.json')==r['rea_output_sha256']
  for f in(Path(__file__),Path(__file__).with_name('audit_hgw5g_coex26_r3_modules.py'),Path(__file__).with_name('qualify_f370_qdrv_module.py'),Path(__file__).with_name('recover_hgw5g_driver_ops.py')):pins[str(f)]=sha(f)
  for p,h in pins.items():assert sha(p)==h,'postqualification drift'+p
  (a.output/'complete-module-audit.json').write_text(json.dumps(reports,indent=2)+'\n');(a.output/'qualification-input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/Path(__file__).name).write_bytes(Path(__file__).read_bytes());result.update(status='PASS_OFFLINE_COEX26_R3_OEM_BSS_GEOMETRY_TIMER_RX_BW_MODULE_CLOSURE',reproducible=True,private_records=592,original_records_recovered=26,remaining_original_records=18,new_input_compiles=2,retained_source26_changed_compiles=6,qualified_parent_whole_units_reused=108,old_field_abi=abi['old_members_checked'],old_sizes_offsets_unchanged=True,new_policy_offset=22667,public_action_cases=proof[0]['cases'],other_consumer_cases=proof[1]['cases'],setter_cases=proof[2]['cases'],bw_helper_cases=proof[3]['cases'],geometry_pair_cases=geometry[0]['pair_cases'],geometry_report_cases=geometry[0]['report_cases'],actual_parser_geometry_cases=geometry[1]['cases'],negative_cases=11,pins_verified=len(pins),modules=mods[0]['modules'],limits='Typedwholeparentclosureadmitted by384oldIC/210VAP/72QDRVoffsetwidthsizeandunchangedheaderline witness. Actualrecv_mgmt gatefragments tested; otherfullframeparsers notfullyreplayed. Publiccoexparserbounds safetydeviation declared. VoidBWcallbacks do not proveMuC/PHY/RF/regulatory/traffic/persistence/release; inheritedCoC25initializedretainedscope andNAC/twoEOPNOTSUPPlimits remain.')
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
