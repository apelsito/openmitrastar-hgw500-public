"""SOURCE29 beacon integration delta against same-header exactCoC25 control.

Existing strict R12 checker reused without editing it; only target-specific
diagnosticlineencodings/renumbering/count/dataoffsets are adapted on a frozen
copy. Reports QDRV/WLAN only; complete metadata/ancillary/pins finalgate separate.
"""
import argparse,hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replace(text,a,b):assert text.count(a)==1,a;return text.replace(a,b,1)
def main():
 p=argparse.ArgumentParser();p.add_argument('--control',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/qualify_consolidated23_beacon_r12.py';t=original.read_text()
 t=replace(t,"'CSWTCH.94':'CSWTCH.89'","'CSWTCH.96':'CSWTCH.91'")
 t=replace(t,"(958,246,2),(959,35,36)","(962,247,3),(963,35,36)")
 t=replace(t,"(44,70,120),(116,71,121)","(44,83,133),(116,84,134)")
 t=replace(t,"(76,152,88),(77,12,13)","(76,216,152),(77,12,13)")
 t=replace(t,"(92,145,148)","(92,146,149)")
 t=replace(t,"'ieee80211com_media_change':[(204,93,29),(205,8,9)],",'')
 t=replace(t,"(166,142,78),(167,2,3),(1134,14,206),(1180,78,14),(1181,4,5)","(166,144,80),(167,8,9),(1146,16,208),(1192,80,16),(1193,10,11)")
 t=replace(t,"(42,33,36)","(42,190,193)");t=replace(t,"(44,62,65)","(44,219,222)")
 t=replace(t,"'consolidated23-beacon-r12-control-source-20261022T204600Z-r1','consolidated23-beacon-r12-source-20261022T203200Z-r2'","'consolidated29-control-source-20261022T213300Z-r1','consolidated29-source-20261022T212500Z-r1'")
 start=t.index("   elif k[0]=='ieee80211_get_prichan_list_by_operating_class':");end=t.index("   elif k[0]=='ieee80211_compile_action_measurement_11k':",start)
 replacement="""   elif k[0]=='ieee80211_get_prichan_list_by_operating_class':
    assert c=='wlan'and len(x)==176 and len(y)==172 and x[34]==39 and y[34]==37;z[34]=39;assert x[62:70]==bytes.fromhex('0a22800f0000ed0b')and y[54:58]==bytes.fromhex('bfda546a');assert(0xbf<<4)==0xbf0 and 0xbf0==0xbed+3
    z[54:58]=b'';z[62:62]=x[62:70]
   elif k[0]=='ieee80211com_media_change':
    assert len(x)==260 and len(y)==264 and x[36]==219 and y[36]==223 and x[174]==155 and y[174]==157;z[36]=219;z[174]=155
    assert x[202:206]==bytes.fromhex('8a229f0f')and y[202:210]==bytes.fromhex('0a22800f00000108');z[202:210]=x[202:206]
    for pos in range(206,len(x)):
     if z[pos]!=x[pos]:assert pos in [252,258] and (x[pos]-z[pos])==2,(pos,x[pos],z[pos]);z[pos]=x[pos]
"""
 t=t[:start]+replacement+t[end:]
 t=replace(t,"{'ieee80211_get_prichan_list_by_operating_class','ieee80211_compile_action_measurement_11k'}if c=='wlan'","{'ieee80211_get_prichan_list_by_operating_class','ieee80211_compile_action_measurement_11k','ieee80211com_media_change'}if c=='wlan'")
 t=replace(t,"if e is n and k[0]=='ieee80211_get_prichan_list_by_operating_class':rel=62 if rel==58 else(rel-4 if rel>=70 else rel)","if e is n and k[0]=='ieee80211_get_prichan_list_by_operating_class':rel=58 if rel==62 else(rel+4 if rel>=58 else rel)")
 t=replace(t,"if e is n and k[0]=='ieee80211_compile_action_measurement_11k':rel=308 if rel==304 else(rel-4 if rel>=316 else rel)","if e is n and k[0]=='ieee80211_compile_action_measurement_11k':rel=308 if rel==304 else(rel-4 if rel>=316 else rel)\n   if e is n and k[0]=='ieee80211com_media_change':rel=rel-4 if rel>=210 else rel")
 t=t.replace('4536+14232','4536+14280').replace('589*24','591*24').replace('593*24','595*24').replace("'private_records':593","'private_records':595")
 marker="  if c=='wlan'and t['name']=='ieee80211_beacon_update':";start=t.index(marker);end=t.index('\n for sec,s in o.byname.items():',start);t=t[:end]+"\n  if c=='wlan'and t['name']=='ieee80211_vap_detach'and t['newsize']==466:\n   end=t['new']+t['newsize'];assert n.byname[t['section']]['data'][end:end+2]==bytes.fromhex('e078');t['newsize']+=2"+t[end:]
 t=replace(t,"bytes.fromhex('4d020000')and y[1356:1360]==bytes.fromhex('51020000')","bytes.fromhex('4f020000')and y[1356:1360]==bytes.fromhex('53020000')")
 script=a.output/'adapted-strict-residual.py';script.write_text(t);env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools');r=subprocess.run([sys.executable,str(script),'--control',str(a.control),'--candidate',str(a.candidate),'--output',str(a.output/'actual')],capture_output=True,env=env);(a.output/'stdout').write_bytes(r.stdout);(a.output/'stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads((a.output/'actual/result.json').read_text());proof['adaptation_pins']={str(p):sha(p)for p in[Path(__file__),original,script]};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':main()
