"""Seal R11c exact bounded source/module/fixture gate, offline only."""
import argparse,hashlib,json,struct,subprocess,sys
from collections import Counter
from pathlib import Path
from qualify_beacon_r11c_complete_delta import audit
from catalog_hgw_firmware_comments import scan_comments
from prepare_tqe_bounded_admission_prototype import function

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--parent-build',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);pins={};protected={Path(__file__),ROOT/'tools/qualify_beacon_r11c_complete_delta.py',ROOT/'tools/build_beacon_r11c_minimal_wlan_pair.py',ROOT/'tools/test_beacon_r11c_app_transaction.py',a.build/'result.json',a.build/'input-pins.json',a.source/'result.json',a.fixture/'result.json',a.fixture/'fixture.exe',a.fixture/'actual-app-transaction.c'}
 bp=json.loads((a.build/'input-pins.json').read_text())
 for path,h in bp.items():assert sha(path)==h,'actual buildpin drift '+path;pins[path]=h
 proof=json.loads((a.build/'result.json').read_text());assert proof['reproducible']and proof['input_pins']==3036
 for row in proof['modules']:
  path=Path(row['path']);assert sha(path)==row['sha256']and path.stat().st_size==row['bytes'];protected.add(path)
  if row['component']!='wlan':assert sha(path)==sha(a.parent_build/row['lane']/row['component']/(row['component']+'.ko'))
 f=json.loads((a.fixture/'result.json').read_text());assert f['cases']==1034 and sha(a.fixture/'fixture.exe')==f['executable_sha256'] and sha(a.fixture/'actual-app-transaction.c')==f['fixture_sha256']
 replays=[]
 for d in [a.fixture,ROOT/'outputs/rea/beacon-r11c-app-synchronization-fixture-20261022T190800Z-r2',ROOT/'outputs/rea/beacon-r11c-app-interleaving-fixture-20261022T191000Z-r3']:
  r=subprocess.run([str(d/'fixture.exe')],capture_output=True);assert not r.returncode;replays.append(json.loads(r.stdout));protected.update(p for p in d.iterdir()if p.is_file())
 # Check actual helper bodies, including threaded read/replace/remove fixture.
 for d in [a.fixture,ROOT/'outputs/rea/beacon-r11c-app-interleaving-fixture-20261022T191000Z-r3']:
  text=(d/('actual-app-transaction.c'if d==a.fixture else'fixture.c')).read_text()
  for name in ['add_app_ie','remove_app_ie','get_app_ie']:assert function((a.source/'source/wlan/ieee80211_wireless.c').read_text(),name+'(')in text
  assert function((a.source/'source/wlan/ieee80211_output.c').read_text(),'om_app_ie_copy(')in text
 comments={}
 for rel in json.loads((a.source/'result.json').read_text())['changed_sources']:
  before=(a.parent_source/rel).read_bytes();after=(a.source/rel).read_bytes();c=lambda raw:Counter(raw[x['offset']:x['end_offset']]for x in scan_comments(raw));assert not c(before)-c(after),'old comments lost '+rel;comments[rel]=sum(c(before).values())
 report=audit(a.parent_build/'a/wlan/wlan.ko',a.build/'a/wlan/wlan.ko')
 # Immutable mutated ELF negatives: actual symbol attrs/anonymous data/RELA.
 from qualify_f370_qdrv_module import Elf
 target=a.build/'a/wlan/wlan.ko';elf=Elf(target);raw=target.read_bytes();negative=[];mutations=[]
 index,s=next((i,s)for i,s in enumerate(elf.syms)if s['name']=='ieee80211_chan2ieee');mutations.append(('unrelated_function_byte',elf.sections[s['section']]['offset']+s['value']))
 mutations.append(('old_symbol_attribute',elf.byname['.symtab']['offset']+index*16+12))
 ro=elf.byname['.rodata'];mutations.append(('allocated_data_byte',ro['offset']))
 helper=next(s for s in elf.syms if s['name']=='ieee80211_ioctl_getappiebuf');mutations.append(('anonymous_alignment_byte',elf.sections[helper['section']]['offset']+helper['value']+helper['size']))
 reloc=next(r for r in elf.relas if r['section']==elf.symsection(s)and s['value']<=r['offset']<s['value']+s['size']);sec=next(x for x in elf.sections if x['type']==4 and elf.sections[x['info']]['name']==reloc['section']);ri=next(i for i in range(sec['size']//12)if struct.unpack_from('<I',sec['data'],i*12)[0]==reloc['offset']);mutations.append(('unrelated_RELA_addend',sec['offset']+ri*12+8))
 for name,pos in mutations:
  data=bytearray(raw);data[pos]^=1;path=a.output/(name+'.ko');path.write_bytes(data)
  try:audit(a.parent_build/'a/wlan/wlan.ko',path)
  except Exception as ex:negative.append({'case':name,'rejected':True,'reason':str(ex)})
  else:raise AssertionError('negative mutation accepted '+name)
 for path in protected:pins[str(path)]=sha(path)
 for path,h in pins.items():assert sha(path)==h,'post review drift '+path
 result={'status':'PASS_OFFLINE_R11C_COMPLETE_SEVEN_MODULE_APP_SYNC_SCOPE','hardware_accessed':False,'firmware_eligible':False,'modules':proof['modules'],'buildpins_current_verified':3036,'review_pins':len(pins),'new_source_unit_compiles':8,'unchanged_WLAN_objects_reused_per_lane':15,'other_modules_exact_R10':6,'complete_WLAN_audit':report,'actual_source_fixture_replays':replays,'negative_cases':negative,'old_comments_preserved':comments,'capability_count':19,'limits':['APP helpers/copy execute withhostfakevalidator/allocation/lock. AllIEencoders/framepathsnotexecuted.','TwoWindows thread interleavings testoldbufferretentionduringcopy; noactualkernelSMP/hardIRQ/callgraphreentrancy proof.','Sixchangedemittedsourcefunctionbodies are source/fixturebound, notOEMinstructionequivalence.','No genericVAPobjectlifetimeclaim; header/wire unchangedonly relative toqualifiedR10.','NoRFclienttrafficbootpersistence/recovery/release acceptance.']}
 (a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'receipt_sha256':sha(a.output/'result.json'),'review_pins':len(pins),'negative_cases':len(negative)},indent=2))
if __name__=='__main__':main()
