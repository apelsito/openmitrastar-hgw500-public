"""Actual494/495WEXT+MDIEproducer/callerfixture; hostfakebeaconcallback only."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def case(t,proc,label):
 b=function(t,proc+'(');s=b.index('\tcase '+label+':');e=b.index('\n\tcase ',s+1);return b[s:e]
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);src=a.candidate/'source/wlan';w=(src/'ieee80211_wireless.c').read_text();setcases='\n'.join(case(w,'ieee80211_ioctl_setparam',n)for n in['OM_OEM_PARAM_MDID','OM_OEM_PARAM_FT_OVER_DS']);getcase=case(w,'ieee80211_ioctl_getparam','OM_OEM_PARAM_MDID').replace('param[0]','*param');unsupported=case(w,'ieee80211_ioctl_getparam','OM_OEM_PARAM_FT_OVER_DS').replace('param[0]','*param');h=(src/'openmitrastar_mdie.h').read_text();helper=h[h.index('static inline'):h.rindex('#endif')];beacon=(src/'ieee80211_beacon.c').read_text();start=beacon.index('\tif(READ_ONCE(vap->om_mdid))');end=beacon.index('\n\n',start);beaconblock=beacon[start:end];out=(src/'ieee80211_output.c').read_text();start=out.index('\t\tif(READ_ONCE(vap->om_mdid))');end=out.index('\n\n',start);probeblock=out[start:end];desc=(src/'ieee80211_beacon_desc.c').read_text();start=desc.index('\tcase 54:');end=desc.index('\n\tcase ',start+1);descblock=desc[start:end]
 pre=r'''#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <limits.h>
typedef uint8_t u8;typedef uint16_t u16;
#define IEEE80211_M_HOSTAP 6
#define OM_OEM_PARAM_MDID 494
#define OM_OEM_PARAM_FT_OVER_DS 495
#define EINVAL 22
#define EOPNOTSUPP 95
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
struct ieee80211vap;struct ieee80211com{void(*ic_beacon_update)(struct ieee80211vap*);};struct ieee80211vap{struct ieee80211com*iv_ic;unsigned iv_opmode;u16 om_mdid;u8 om_ft_over_ds;u32dummy;};
struct ieee80211_node{struct ieee80211vap*ni_vap;};static unsigned updates,descs;static u8 frame[16];
'''.replace('u32dummy;','uint32_t untouched;')
 actual=helper+'\nstatic u8*descriptor(struct ieee80211_node*ni,unsigned id,u8*frm){struct ieee80211vap*vap=ni->ni_vap;switch(id){'+descblock+'default:return frm;}descs++;return frm;}\n#define ieee80211_add_beacon_desc_ie descriptor\nstatic u8*beacon_build(struct ieee80211vap*vap,u8*frm){struct ieee80211_node node={vap};struct ieee80211_node*ni=&node;'+beaconblock+'return frm;}\nstatic u8*probe_build(struct ieee80211vap*vap,u8*frm){'+probeblock+'return frm;}\nstatic void update(struct ieee80211vap*v){updates++;memset(frame,0xa5,sizeof(frame));beacon_build(v,frame+1);}\nstatic int set(struct ieee80211vap*vap,int param,int value){struct ieee80211com*ic=vap->iv_ic;switch(param){'+setcases+'default:return-22;}}\nstatic int get(struct ieee80211vap*vap,int*param){switch(*param&0xffff){'+getcase+unsupported+'default:return-22;}return 0;}\n'
 test=r'''int main(void){struct ieee80211com ic={update};struct ieee80211vap vap={&ic,6,0,0,0x1234abcd};unsigned transactions=0,iecases=0;u8 bytes[8],expected[8];int value;
for(unsigned md=0;md<65536;md++)for(unsigned ft=0;ft<256;ft++){vap.om_mdid=md;vap.om_ft_over_ds=ft;memset(bytes,0xa5,sizeof(bytes));memset(expected,0xa5,sizeof(expected));expected[1]=54;expected[2]=3;expected[3]=(u8)md;expected[4]=(u8)(md>>8);expected[5]=ft?1:0;assert(om_mdie_write(bytes+1,md,ft)==bytes+6&&!memcmp(bytes,expected,sizeof(bytes)));iecases++;}
int inputs[]={INT_MIN,-65537,-1,0,1,65535,65536,INT_MAX};for(unsigned role=0;role<8;role++)for(unsigned input=0;input<8;input++)for(unsigned prior=0;prior<2;prior++){vap.iv_opmode=role;vap.om_mdid=prior?0xabcd:0;vap.om_ft_over_ds=0x77;updates=0;u16 before=vap.om_mdid;int rc=set(&vap,494,inputs[input]);assert(rc==(role==6?0:-22));assert(vap.om_mdid==(role==6?(u16)inputs[input]:before)&&vap.om_ft_over_ds==0x77&&updates==(role==6)&&vap.untouched==0x1234abcd);value=494|0x80000000U;assert(!get(&vap,&value)&&value==vap.om_mdid);u16 md=vap.om_mdid;updates=0;u8 old=vap.om_ft_over_ds;rc=set(&vap,495,inputs[input]);assert(rc==(role==6?0:-22)&&vap.om_ft_over_ds==(role==6?(u8)inputs[input]:old)&&vap.om_mdid==md&&!updates);value=495;assert(get(&vap,&value)==-95&&value==495);transactions++;}
for(unsigned md=0;md<65536;md++){vap.iv_opmode=6;vap.om_mdid=md;vap.om_ft_over_ds=md&255;memset(bytes,0xa5,sizeof(bytes));descs=0;assert(beacon_build(&vap,bytes+1)==bytes+1+(md?5:0)&&descs==(md!=0));memset(bytes,0xa5,sizeof(bytes));assert(probe_build(&vap,bytes+1)==bytes+1+(md?5:0));transactions++;}
assert(iecases==16777216);printf("{\"MDIE_cases\":%u,\"actual_control_and_caller_cases\":%u,\"495_getter_faithful_unsupported\":true}\n",iecases,transactions);return 0;}
''';f=a.output/'actual-mdid-ft.c';f.write_text(pre+actual+test);r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);pins={str(p):sha(p)for p in[Path(__file__),src/'ieee80211_wireless.c',src/'ieee80211_beacon.c',src/'ieee80211_beacon_desc.c',src/'ieee80211_output.c',src/'openmitrastar_mdie.h',a.compiler,f,a.output/'fixture.exe']};result={'status':'PASS_ACTUAL_MDID494_FT495_CONTROL_AND_MDIE_CALLER_BLOCK_FIXTURE','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':pins,'limits':['ActualWEXTcases/conditionalbeacon-probe/IEdescriptorcase/helper; fakebeaconcallback/descriptorallocation.','MDIE16bit×8bitproducerexhausted; callbackresource/lifetime/publishingnotverifiedbyhostfixture.','NoFTauthentication/DSresponse/client/RFacceptance.']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
