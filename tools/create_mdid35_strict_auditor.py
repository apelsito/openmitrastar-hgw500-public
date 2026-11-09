"""Prepare immutable auditor skeleton from complete residual audit for MDID35 control."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/audit_hgw5g_coex26_r3_modules.py';text=original.read_text();start=text.index("CHANGED=");end=text.index('\ndef digest',start)
 text=text[:start]+'''CHANGED={'qdrv':set(),'wlan':{'ieee80211_ioctl_getparam','ieee80211_ioctl_setparam','ieee80211_beacon_alloc','ieee80211_add_beacon_desc_ie','ieee80211_send_mgmt'}}
NEW={'qdrv':set(),'wlan':set()}
EXPORTS=set()
RENAME={}
DIAG={}
COMPACT=set()
NOP_DELTA=0

'''+text[end:]
 marker='def digest(b):return hashlib.sha256(b).hexdigest()';text=text.replace(marker,marker+"\ndef norm_sourcepath(s):return s.replace('mdid494-ft495-control-source-20261022T231800Z-r2','mdid494-ft495-source35-20261022T232500Z-r3')",1)
 text=text.replace("return('string',e.cstring(sec,value))","return('string',norm_sourcepath(e.cstring(sec,value)))")
 text=text.replace("strings=lambda z:Counter(v for v in z.split(b'\\0')if v)","strings=lambda z:Counter(norm_sourcepath(v.decode('latin1'))for v in z.split(b'\\0')if v)")
 text=text.replace("assert set(diagnostics)==({k for k in DIAG if k!='qdrv_wlan_exit'}if component=='wlan'else{'qdrv_wlan_exit'})","assert set(diagnostics)==(set(DIAG)if component=='wlan'else set())")
 text=text.replace("expected=(6 if component=='wlan'else 0)if sec=='.text'else 0","expected=(NOP_DELTA if component=='wlan'else 0)if sec=='.text'else 0")
 text=text.replace('591*24','598*24').replace('592*24','601*24').replace("[0]==591 and struct.unpack_from('<H',y,p)[0]==592","[0]==598 and struct.unpack_from('<H',y,p)[0]==601").replace("struct.pack_into('<H',z,p,591)","struct.pack_into('<H',z,p,598)")
 text=text.replace("value-=24","value-=72").replace("y[cut+24:]","y[cut+72:]")
 text=text.replace("assert table_old['value']==table_new['value']and",'assert')
 text=text.replace('PASS_COMPLETE_COEX26_R3_BSS_GEOMETRY_RESIDUAL_SCOPE','PASS_COMPLETE_MDID35_MATCHED_HEADER_RESIDUAL_SCOPE')
 (a.output/'strict-auditor-unfrozen.py').write_text(text);r={'status':'AUDITOR_SKELETON_NOT_QUALIFIED_DIAGNOSTICS_RENAMES_NOP_PENDING_CONTROL','hardware_accessed':False,'firmware_eligible':False,'pins':{str(x):sha(x)for x in[Path(__file__),original,a.output/'strict-auditor-unfrozen.py']}};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
