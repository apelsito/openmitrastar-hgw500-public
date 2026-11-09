"""Run existing descriptor fixture with exact R11c BH selector adaptation.

Original fixture retained untouched; copy and exact selector-only replacements
are saved under the new evidence directory. Host locks remain fakes.
"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 original=ROOT/'tools/test_hgw5g_beacon_descriptor_lifetime.py';text=original.read_text();old="validation_start=beacon.index('\\tIEEE80211_LOCK(ic);',beacon.index('void\\nieee80211_beacon_update('))";assert text.count(old)==1;text=text.replace(old,old.replace('IEEE80211_LOCK(ic)','IEEE80211_LOCK_BH(ic)'),1)
 old="fixture_locks='\\n#define IEEE80211_LOCK(ic) ((void)(ic))\\n#define IEEE80211_UNLOCK(ic) ((void)(ic))\\n'";assert text.count(old)==1;text=text.replace(old,old.replace("\\n'","\\n#define IEEE80211_LOCK_BH(ic) ((void)(ic))\\n#define IEEE80211_UNLOCK_BH(ic) ((void)(ic))\\n'"),1)
 script=a.output/'adapted-descriptor-fixture.py';script.write_text(text);lane=a.output/'actual';env=__import__('os').environ.copy();env['PYTHONPATH']=str(ROOT/'tools');r=subprocess.run([sys.executable,str(script),'--candidate',str(a.candidate),'--output',str(lane)],capture_output=True,env=env);(a.output/'run.stdout').write_bytes(r.stdout);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads((lane/'result.json').read_text());proof['selector_adaptation']='OnlyLOCK_BHselector+twofakeBHmacros; descriptor/APP/dynamiccodeunmodified';proof['tool_pins']={str(p):sha(p)for p in[Path(__file__),original,script]};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':main()
