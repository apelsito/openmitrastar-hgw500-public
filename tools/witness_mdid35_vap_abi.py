"""FulloldVAP/hostprefix ARC witness fornewMDID/FTtail (+4Bexpected).

Derivesretainedprefixwitness; oldVAPmembers unchanged, qdrvVAPiv size+4 and
followingmembers shift+4; wire/IC/QdrvWLAN/BO/beaconparam unchanged.
"""
import argparse,hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/witness_consolidated23_beacon_r12_abi.py';text=original.read_text();start=text.index("extensions=[('ieee80211com','om_bss_tm_flags')");end=text.index('\n sizes=',start);text=text[:start]+"extensions=[('ieee80211vap','om_mdid'),('ieee80211vap','om_ft_over_ds')]"+text[end:];start=text.index(' old,new=rows');end=text.index(' for path,h in pins.items():',start)
 text=text[:start]+''' old,new=rows
 for t in ['ieee80211com','ieee80211vap','qdrv_wlan','ieee80211_beacon_offsets','ieee80211_beacon_param_t']:assert old['fields'][t]==new['fields'][t],t+' prefix'
 assert new['sizes']['ieee80211vap']==old['sizes']['ieee80211vap']+4
 assert new['sizes']['qdrv_vap']==old['sizes']['qdrv_vap']+4
 for member,x in old['fields']['qdrv_vap'].items():
  y=new['fields']['qdrv_vap'][member]
  if member=='iv':assert x['offset']==y['offset']and y['size']==x['size']+4
  else:assert x['size']==y['size']and y['offset']==x['offset']+4,(member,x,y)
 for t in old['sizes']:
  if t not in ['ieee80211vap','qdrv_vap']:assert old['sizes'][t]==new['sizes'][t],t+'sizeof'
 assert new['extensions']['ieee80211vap.om_mdid']==old['sizes']['ieee80211vap']-2
 assert new['extensions']['ieee80211vap.om_ft_over_ds']==old['sizes']['ieee80211vap']
'''+text[end:];text=text.replace('PASS_ARC_CONSOLIDATED23_FULL_PARSED_PREFIX_AND_DECLARED_EMBEDDING_EXTENTS','PASS_ARC_MDID35_ALL_OLD_VAP_PREFIX_AND_QDRV_VAP_SHIFT4');script=a.output/'adapted-full-vap-witness.py';script.write_text(text);env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools');r=subprocess.run([sys.executable,str(script),'--parent',str(a.parent),'--candidate',str(a.candidate),'--output',str(a.output/'actual')],capture_output=True,env=env);(a.output/'stdout').write_bytes(r.stdout);(a.output/'stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads((a.output/'actual/result.json').read_text());proof['tool_pins']={str(p):sha(p)for p in[Path(__file__),original,script]};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k]for k in['status','old_members_checked']},indent=2))
if __name__=='__main__':main()
