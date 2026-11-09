"""Actual contiguous probe RRM/MDIE/Ath caller fragment; bounded fake Ath IE."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);src=a.candidate/'source/wlan'
 t=(src/'ieee80211_output.c').read_text();start=t.index('case IEEE80211_FC0_SUBTYPE_PROBE_RESP:');end=t.index('case IEEE80211_FC0_SUBTYPE_AUTH:',start);t=t[start:end];start=t.index('\t\tif(ic->om_neighbor_report_flags & 1U)\n\t\t\tfrm = om_neighbor_rrm_ie');end=t.index('\n\t\t{',start);fragment=t[start:end]
 assert fragment.index('om_neighbor_rrm_ie')<fragment.index('om_mdie_write')<fragment.index('ieee80211_add_athAdvCap')
 h=(src/'openmitrastar_mdie.h').read_text();md=h[h.index('static inline'):h.rindex('#endif')];rrm=function((src/'openmitrastar_bss_tm.h').read_text(),'static inline u8 *om_neighbor_rrm_ie(')
 pre='''#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;
#define READ_ONCE(x) (x)
struct node{u8 ni_ath_flags;u16 ni_ath_defkeyindex;};struct vap{u16 om_mdid;u8 om_ft_over_ds;struct node *iv_bss;};struct ic{u32 om_neighbor_report_flags;};
static u8*ieee80211_add_athAdvCap(u8*f,u8 a,u16 b){f[0]=221;f[1]=3;f[2]=a;f[3]=(u8)b;f[4]=(u8)(b>>8);return f+5;}
'''
 actual=md+'\n'+rrm+'\nstatic u8*probe(struct vap*vap,struct ic*ic,u8*frm){'+fragment+'return frm;}\n'
 test='''int main(void){struct node ni={7,0xabcd};struct vap vap={0,0,&ni};struct ic ic={0};unsigned cases=0;u8 bytes[32],exp[32];
for(unsigned r=0;r<4;r++)for(unsigned md=0;md<65536;md++)for(unsigned ath=0;ath<3;ath++){unsigned p=1;vap.om_mdid=md;vap.om_ft_over_ds=md&255;vap.iv_bss=ath==0?NULL:&ni;ni.ni_ath_flags=ath==2?7:0;ic.om_neighbor_report_flags=r;memset(bytes,0xa5,sizeof(bytes));memset(exp,0xa5,sizeof(exp));if(r&1){exp[p++]=70;exp[p++]=5;exp[p++]=2;for(unsigned j=0;j<4;j++)exp[p++]=0;}if(md){exp[p++]=54;exp[p++]=3;exp[p++]=(u8)md;exp[p++]=(u8)(md>>8);exp[p++]=(md&255)?1:0;}if(ath==2){exp[p++]=221;exp[p++]=3;exp[p++]=7;exp[p++]=0xcd;exp[p++]=0xab;}assert(probe(&vap,&ic,bytes+1)==bytes+p&&!memcmp(bytes,exp,sizeof(bytes)));cases++;}printf("{\\"actual_probe_order_cases\\":%u}\\n",cases);return 0;}
'''
 # Actual C test literal uses escaped JSON quotes.
 test=test.replace('\\"','\\"')
 f=a.output/'actual-probe-order.c';f.write_text(pre+actual+test);r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);pins={str(x):sha(x)for x in[Path(__file__),src/'ieee80211_output.c',src/'openmitrastar_mdie.h',src/'openmitrastar_bss_tm.h',a.compiler,f,a.output/'fixture.exe']};result={'status':'PASS_ACTUAL_PROBE_RRM_MDIE_ATH_ORDER_BYTES_AND_GUARDS','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':pins,'limits':'Actualcontiguouscallers/RRM/MDIE; fixedfakeAthIEonly. Noactualframeallocation/TX/RFexecution.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
