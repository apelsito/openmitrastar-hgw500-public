"""CompleteSOURCE32residual and11parsednegativecases, nohardware."""
import argparse,copy,hashlib,json
from pathlib import Path
from qualify_f370_qdrv_module import Elf
from audit_consolidated32_modules import audit
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);reports={};negative=[];pins={str(Path(__file__)):sha(__file__),str(Path(__file__).with_name('audit_consolidated32_modules.py')):sha(Path(__file__).with_name('audit_consolidated32_modules.py'))}
 for c in['wlan','wlan_scan_ap']:
  op=a.parent/c/(c+'.ko');np=a.candidate/c/(c+'.ko');old,new=Elf(op),Elf(np);pins[str(op)]=sha(op);pins[str(np)]=sha(np);reports[c]=audit(old,new,c)
  kinds=['function','anonymous','data','relocation','symbol','new_symbol']if c=='wlan'else['function','data','relocation','symbol','new_symbol']
  for kind in kinds:
   e=copy.deepcopy(new)
   def byte(sec,pos):z=bytearray(e.byname[sec]['data']);z[pos]^=1;e.byname[sec]['data']=bytes(z)
   name='ieee80211_setmode'if c=='wlan'else'ap_start';s=next(s for s in e.syms if s['name']==name)
   if kind=='function':byte(e.symsection(s),s['value'])
   elif kind=='anonymous':
    fs=sorted([s for s in e.syms if s['type']==2 and s['size']and e.symsection(s)=='.text'],key=lambda s:s['value']);end=0
    for f in fs:
     if f['value']-end>20:byte('.text',end+8);break
     end=max(end,f['value']+f['size'])
    else:raise AssertionError('anonymousnotfound')
   elif kind=='data':sec=next(sec for sec in['.rodata','.data']if sec in e.byname and e.byname[sec]['data']);byte(sec,0)
   elif kind=='relocation':r=next(r for r in e.relas if r['section']==e.symsection(s)and s['value']<=r['offset']<s['value']+s['size']);r['addend']+=4
   elif kind=='symbol':s['other']=1
   else:t=copy.deepcopy(s);t['name']='unexpected_new_symbol';e.syms.append(t)
   try:audit(old,e,c)
   except(AssertionError,ValueError)as ex:negative.append({'component':c,'case':kind,'rejected':True,'reason':str(ex)})
   else:raise AssertionError('negativeaccepted '+c+'/'+kind)
 for path,h in pins.items():assert sha(path)==h
 r={'status':'PASS_CONSOLIDATED32_COMPLETE_RESIDUALS_AND_ELEVEN_PARSED_NEGATIVES','hardware_accessed':False,'firmware_eligible':False,'audits':reports,'negative_cases':negative,'negative_count':len(negative)};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');print(json.dumps({'status':r['status'],'negative_count':len(negative),'receipt_sha256':sha(a.output/'result.json')},indent=2))
if __name__=='__main__':main()
