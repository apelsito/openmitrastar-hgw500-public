"""SOURCE35r3 gate, explicit retained exact-header ABI/syntax and new caller fixtures."""
import argparse,hashlib,json
from pathlib import Path
from recover_hgw5g_driver_ops import Elf
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(path):
 s=str(path).replace('\\','/')
 if len(s)>2 and s[1]==':':s='/mnt/'+s[0].lower()+s[2:]
 return Path(s)if s.startswith('/')else ROOT/s
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--prior',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();pins={};receipts={}
 def read(path):pins[str(path)]=sha(path);return json.loads(path.read_text())
 def importpin(d):
  for path,h in d.items():path=norm(path);assert sha(path)==h,('pin',path);pins[str(path)]=h
 for tree in['source','headers']:
  for x in(a.candidate/tree).rglob('*'):
   if x.is_file():pins[str(x)]=sha(x)
 for x in(a.prior/'headers').rglob('*'):
  if x.is_file():assert sha(x)==sha(a.candidate/x.relative_to(a.prior))
 for name,folder,status in[
 ('paths','mdid494-ft495-path-fixture-20261022T233000Z-r3','PASS_ACTUAL_MDID494_FT495_CONTROL_AND_MDIE_CALLER_BLOCK_FIXTURE'),
 ('order','mdid35-probe-order-fixture-20261022T232900Z-r3','PASS_ACTUAL_PROBE_RRM_MDIE_ATH_ORDER_BYTES_AND_GUARDS'),
 ('admission','mdid35-descriptor54-fixture-20261022T234400Z-r3','PASS_ACTUAL_MDIE54_FULL_ADMISSION_PAYLOAD_AND_DESCRIPTOR_LINK_PATH'),
 ('callback','mdid35-callback-mapping-20261022T233800Z-r3','PASS_OEM_5444_ANONYMOUS_BEACON_CALLBACK_MAPPING_AND_INHERITED_SOURCE_LIFETIME_PATHS')]:
  r=read(ROOT/'outputs/rea'/folder/'result.json');assert r['status']==status;importpin(r['pins']);receipts[name]=r
 abi=read(ROOT/'outputs/rea/mdid494-ft495-full-abi-20261022T231200Z-r2/result.json');assert abi['status']=='PASS_ARC_MDID35_ALL_OLD_VAP_PREFIX_AND_QDRV_VAP_SHIFT4';importpin(read(ROOT/'outputs/rea/mdid494-ft495-full-abi-20261022T231200Z-r2/actual/input-pins.json'))
 syntax=read(ROOT/'outputs/rea/mdid494-ft495-syntax-20261022T231000Z-r2/result.json');assert syntax['status']=='PASS_ACTUAL_TYPED_HEADER_SYNTAX_UNITS';importpin(read(ROOT/'outputs/rea/mdid494-ft495-syntax-20261022T231000Z-r2/input-pins.json'))
 for x in(a.prior/'source').rglob('*'):
  if x.is_file()and x.name!='ieee80211_output.c':assert sha(x)==sha(a.candidate/x.relative_to(a.prior))
 # R3 changes onlyprobe block ordering, otherfive syntaxunitsandallABIheaders exact.
 obj=ROOT/'outputs/rea/mdid494-ft495-syntax-20261022T231000Z-r2/a/wlan/ieee80211_wireless.o';records=Elf(obj).ioctl_records();assert len(records)==601
 r=read(a.candidate/'result.json');assert r['source_original_records']==35 and r['oem_probe_order']==['RRM','MDIE','AthAdvCaps']
 text=(a.candidate/'source/wlan/ieee80211_beacon.c').read_text();start=text.index('ieee80211_beacon_init(');end=text.index('\nstruct sk_buff *',start);part=text[start:end];calls=part.count('ieee80211_add_beacon_desc_ie(')+part.count('ieee80211_add_beacon_desc_header(')+part.count('ieee80211_add_beacon_desc_mandatory_fields(')+2;assert calls<=50
 pins[str(Path(__file__))]=sha(__file__);assert all(sha(path)==h for path,h in pins.items());a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');r={'status':'PASS_SOURCE_ONLY_MDID35_R3_OEM_ORDER_FULL_IE54_ADMISSION_TYPED_ABI_PENDING_MODULES','hardware_accessed':False,'firmware_eligible':False,'source_original_records':35,'qualified_combined_records':None,'private_table_records':601,'MDIE_cases':receipts['paths']['MDIE_cases'],'control_caller_cases':receipts['paths']['actual_control_and_caller_cases'],'probe_order_cases':receipts['order']['actual_probe_order_cases'],'IE54_admission_cases':receipts['admission']['actual_IE54_admission_cases'],'beacon_descriptor_conservative_static_upper_bound':calls,'descriptor_bytes':calls*20,'old_header_ABI_exact_retained':True,'old_syntax_5_units_exact_retained':True,'r3_output_compile_pending':True,'pins':len(pins),'limits':['SOURCE35only; full58freshcompiled×2 r2seed plusr3outputfresh×2 andsame-headercontrol/wholemodulespending.','Exact494HOSTAPlow16 callbackandgetu16;495HOSTAPlow8nocallback/getEOPNOTSUPPretained.','NoFTauth/roaming/key/frameexchangehandler recovery.','NoRF/client/traffic/boot/persistence/recovery/releaseacceptance.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
