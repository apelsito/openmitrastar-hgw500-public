"""Adapt strict449r3wholemoduleaudit to combined29→30exactdiagnostic/table.

Frozencopyonly; retainsallanonymous/symbol/export/data/RELA verification. NoHW.
"""
import argparse,hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/audit_hgw5g_coex26_r3_modules.py';text=original.read_text()
 for x,y in [("(962,'f723','f823')","(962,'0324','0424')"),("(44,'5353','5b53'),(116,'5453','5c53')","(44,'8553','8d53'),(116,'8653','8e53')"),("(76,'d80c','180d')","(76,'980d','d80d')"),("(92,'920d','930d')","(92,'950d','960d')")]:assert text.count(x)==1;text=text.replace(x,y,1)
 text=text.replace('591*24','595*24').replace('592*24','596*24').replace("[0]==591 and struct.unpack_from('<H',y,p)[0]==592","[0]==595 and struct.unpack_from('<H',y,p)[0]==596").replace("struct.pack_into('<H',z,p,591)","struct.pack_into('<H',z,p,595)")
 old="expected=(6 if component=='wlan'else 0)if sec=='.text'else 0";assert text.count(old)==1;text=text.replace(old,"expected=(4 if component=='wlan'else 0)if sec=='.text'else 0",1)
 marker='def digest(b):return hashlib.sha256(b).hexdigest()';assert text.count(marker)==1;text=text.replace(marker,marker+"\ndef norm_sourcepath(s):return s.replace('consolidated29-source-20261022T212500Z-r1','consolidated30-source-20261022T221100Z-r2')",1)
 text=text.replace("return('string',e.cstring(sec,value))","return('string',norm_sourcepath(e.cstring(sec,value)))")
 text=text.replace("strings=lambda z:Counter(v for v in z.split(b'\\0')if v)","strings=lambda z:Counter(norm_sourcepath(v.decode('latin1'))for v in z.split(b'\\0')if v)")
 script=a.output/'adapted-strict-auditor.py';script.write_text(text);env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools');reports={}
 for c in ['qdrv','wlan']:
  r=subprocess.run([sys.executable,str(script),'--old',str(a.parent/c/(c+'.ko')),'--new',str(a.candidate/c/(c+'.ko')),'--component',c],env=env,capture_output=True);(a.output/(c+'.stdout')).write_bytes(r.stdout);(a.output/(c+'.stderr')).write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();reports[c]=json.loads(r.stdout)
 result={'status':'PASS_CONSOLIDATED30_COMPLETE_MODULE_RESIDUALS_PENDING_GLOBAL_PIN_GATE','hardware_accessed':False,'firmware_eligible':False,'audits':reports,'tool_pins':{str(p):sha(p)for p in[Path(__file__),original,script]}};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
