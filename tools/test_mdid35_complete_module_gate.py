"""Run frozen strict MDID35 residual audit and parsed negative controls."""
import argparse,copy,hashlib,importlib.util,json
from pathlib import Path
from qualify_f370_qdrv_module import Elf
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--auditor',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();spec=importlib.util.spec_from_file_location('mdid35auditor',a.auditor);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);audit=mod.audit;a.output.mkdir(parents=True);pins={str(x):sha(x)for x in[Path(__file__),a.auditor]};reports={};neg=[]
 for c in['qdrv','wlan']:
  op=a.old/c/(c+'.ko');np=a.new/c/(c+'.ko');old,new=Elf(op),Elf(np);pins[str(op)]=sha(op);pins[str(np)]=sha(np);reports[c]=audit(old,new,c)
  for kind in ['function','anonymous','data','relocation','symbol','new_symbol']:
   e=copy.deepcopy(new)
   def byte(sec,pos):z=bytearray(e.byname[sec]['data']);z[pos]^=1;e.byname[sec]['data']=bytes(z)
   name='qdrv_wlan_80211_send'if c=='qdrv'else'ieee80211_setmode';s=next(s for s in e.syms if s['name']==name)
   if kind=='function':byte(e.symsection(s),s['value'])
   elif kind=='anonymous':
    fs=sorted([s for s in e.syms if s['type']==2 and s['size']and e.symsection(s)=='.text'],key=lambda s:s['value']);p=0
    for f in fs:
     if f['value']-p>20:byte('.text',p+8);break
     p=max(p,f['value']+f['size'])
    else:raise AssertionError('anonymousnotfound'+c)
   elif kind=='data':sec=next(x for x in['.data','.rodata']if x in e.byname and e.byname[x]['data']);byte(sec,0)
   elif kind=='relocation':r=next(r for r in e.relas if r['section']==e.symsection(s)and s['value']<=r['offset']<s['value']+s['size']);r['addend']+=4
   elif kind=='symbol':s['other']=1
   else:t=copy.deepcopy(s);t['name']='unexpected_new_symbol';e.syms.append(t)
   try:audit(old,e,c)
   except(AssertionError,ValueError)as ex:neg.append({'component':c,'case':kind,'rejected':True,'reason':str(ex)})
   else:raise AssertionError('negativeaccepted'+c+'/'+kind)
 for c in['wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth']:
  op=a.old/c/(c+'.ko');np=a.new/c/(c+'.ko');assert sha(op)==sha(np),('ancillarynotexact',c);pins[str(op)]=pins[str(np)]=sha(op);reports[c]={'status':'BYTE_IDENTICAL_WHOLE_MATCHED_HEADER_CONTROL_MODULE','sha256':sha(op)}
 assert all(sha(p)==h for p,h in pins.items());r={'status':'PASS_MDID35_COMPLETE_MATCHED_HEADER_MODULE_RESIDUALS_AND_TWELVE_PARSED_NEGATIVES','hardware_accessed':False,'firmware_eligible':False,'audits':reports,'negative_cases':neg,'negative_count':len(neg)};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');print(json.dumps({'status':r['status'],'negative_count':len(neg)},indent=2))
if __name__=='__main__':main()
