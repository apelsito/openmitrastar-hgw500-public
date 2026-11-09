"""ActualWEXT461set/get +scannerownedpolicy/toggle/error helperfixture."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
from test_chanset461_kernel_critical_review import PRE
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);base=a.candidate/'source/wlan';inc=(base/'openmitrastar_chanset_kernel.inc').read_text();w=(base/'ieee80211_wireless.c').read_text();sets=[]
 for proc in ['ieee80211_ioctl_setparam','ieee80211_ioctl_getparam']:
  body=function(w,proc+'(');start=body.index('\tcase OM_OEM_PARAM_BW_AUTOSEL:');end=body.index('\n\tcase ',start+1);sets.append(body[start:end])
 test=r'''
#define OM_OEM_PARAM_BW_AUTOSEL 461
static int actual_set(struct ieee80211com*ic,int param,int value){switch(param){SET default:return-22;}}
static int actual_get(struct ieee80211com*ic,int*param){switch(param[0]&0xffff){GET default:return-22;}}
int main(void){struct ieee80211com ic={0};struct scan_state scan={0};int value=0;unsigned cases=0;ic.ic_scan=&scan.base;
for(unsigned upper=0;upper<65536;upper++)for(unsigned edge=0;edge<4;edge++){u32 input=(upper<<16)|(edge==0?0:edge==1?255:edge==2?256:65535);assert(actual_set(&ic,461,(int)input)==0);value=(int)((upper<<16)|461);assert(actual_get(&ic,&value)==0&&value==(input&255)&&!locks);cases++;}
scan.om_chanset_stopping=1;value=42;assert(actual_set(&ic,461,9)==-EBUSY&&actual_get(&ic,&value)==-22);value=461;assert(actual_get(&ic,&value)==-EBUSY&&value==461);scan.om_chanset_stopping=0;ic.ic_scan=NULL;value=461;assert(actual_set(&ic,461,9)==-EAGAIN&&actual_get(&ic,&value)==-EAGAIN&&!locks);printf("{\"cases\":%u,\"scanner_policy_lowbyte\":true,\"missing_or_stopping_refuses\":true}\n",cases);return 0;}
'''.replace('SET',sets[0]).replace('GET',sets[1]);f=a.output/'actual-policy.c';f.write_text(PRE+inc+test);r=subprocess.run([str(a.compiler),'-O1','-std=c11','-I'+str(base),str(f),str(base/'openmitrastar_chanset_recovered.c'),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);result={'status':'PASS_CONSOLIDATED32_ACTUAL_461_WEXT_SCANNER_POLICY_FIXTURE','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':{str(p):sha(p)for p in[Path(__file__),base/'ieee80211_wireless.c',base/'openmitrastar_chanset_kernel.inc',base/'openmitrastar_chanset_recovered.c',a.compiler,f,a.output/'fixture.exe']},'limits':'Typedkernel/scannerlocks fake; actualpolicy/WEXTbody bounded controlflow only; noAPscan/radio/runtime.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
