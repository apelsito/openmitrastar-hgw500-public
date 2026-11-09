"""Combined30 all-old-member padding witness, using retained exact ARC context."""
import argparse,hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/witness_consolidated23_beacon_r12_abi.py';text=original.read_text()
 start=text.index("extensions=[('ieee80211com','om_bss_tm_flags')");end=text.index('\n sizes=',start);text=text[:start]+"extensions=[('ieee80211com','om_20_40_bss_coex')]"+text[end:]
 start=text.index(' old,new=rows');end=text.index(' for path,h in pins.items():',start)
 text=text[:start]+''' old,new=rows
 for t in names:assert old['fields'][t]==new['fields'][t],'old complete member drift '+t
 assert old['sizes']==new['sizes'],'all host and wire sizeof drift'
 policy=new['extensions']['ieee80211com.om_20_40_bss_coex']
 assert policy==old['fields']['ieee80211com']['om_coc_pm_pending']['offset']+1
 assert policy+1==old['fields']['ieee80211com']['om_coc_completed_level']['offset']
 assert policy==22667
'''+text[end:]
 text=text.replace('PASS_ARC_CONSOLIDATED23_FULL_PARSED_PREFIX_AND_DECLARED_EMBEDDING_EXTENTS','PASS_ARC_CONSOLIDATED30_ALL_COMBINED_OLD_MEMBERS_SIZES_AND_POLICY_PADDING')
 text=text.replace("'dependency_pins':len(pins)","'dependency_pins':len(pins),'policy_offset':policy,'policy_width':1,'host_delta':0")
 script=a.output/'adapted-full-abi-witness.py';script.write_text(text);env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools');r=subprocess.run([sys.executable,str(script),'--parent',str(a.parent),'--candidate',str(a.candidate),'--output',str(a.output/'actual')],capture_output=True,env=env);(a.output/'run.stdout').write_bytes(r.stdout);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads((a.output/'actual/result.json').read_text());proof['tool_pins']={str(p):sha(p)for p in[Path(__file__),original,script]};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k]for k in ['status','old_members_checked','host_delta','policy_offset']},indent=2))
if __name__=='__main__':main()
