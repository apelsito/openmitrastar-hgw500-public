"""Actual OEM449 BSS geometry helpers against independent low16 reference.

Exhaust every8-bit scan channel pair at representative BSS frequency edges;
exhaust every16-bit BSS frequency with representative scan channels. Current
channel intentionally differs. IncludeNULL/ANYCBSS guard cases separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);source=a.candidate/'source/wlan/ieee80211_input.c';t=source.read_text();start=t.index('int\nieee80211_20_40_operation_permitted(');end=t.index('int\nieee80211_check_mode(',start);helpers=t[start:end];cp=a.candidate/'source/wlan/ieee80211.c';x=cp.read_text();start=x.index('u_int\nieee80211_ieee2mhz(');end=x.index('EXPORT_SYMBOL(ieee80211_ieee2mhz);',start);freqhelper=x[start:end]
 c=r'''#include <stdint.h>
#include <stddef.h>
#include <assert.h>
typedef unsigned u_int;
#define READ_ONCE(x) (x)
#define IEEE80211_CHAN_2GHZ 0x80U
#define IEEE80211_CHAN_5GHZ 0x100U
#define IEEE80211_CHAN_HT40U 0x20000U
#define IEEE80211_CHAN_HT40D 0x40000U
#define IEEE80211_SEC_CHAN_OFFSET 4
#define IEEE80211_CHAN_SPACE 5
#define IEEE80211_BW_RANGE 25
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)(uintptr_t)0xffff)
struct ieee80211_channel {uint16_t ic_freq;uint32_t ic_flags;uint8_t ic_ieee;};
struct ieee80211com {struct ieee80211_channel*ic_bsschan,*ic_curchan;};
struct ieee80211vap {struct ieee80211com*iv_ic;};
'''+freqhelper+'\n'+helpers+r'''
static uint16_t frequency(unsigned channel){if(channel==14)return 2484;if(channel<14)return(uint16_t)(2407U+channel*5U);if(channel<27)return(uint16_t)(2512U+(channel-15U)*20U);return(uint16_t)(5000U+channel*5U);}
static int expected_pair(struct ieee80211_channel*b,uint8_t p,uint8_t s){unsigned secfreq;int secchan;if(b->ic_flags&0x20000){secfreq=(b->ic_freq+20U)&65535;secchan=(int8_t)(b->ic_ieee+4);}else if(b->ic_flags&0x40000){secfreq=(b->ic_freq-20U)&65535;secchan=(int8_t)(b->ic_ieee-4);}else return 0;unsigned center=(b->ic_freq+secfreq)/2;unsigned low=(center-25U)&65535,high=(center+25U)&65535;unsigned pf=frequency((unsigned)(int)(int8_t)p),sf=s?frequency((unsigned)(int)(int8_t)s):0;int in=(pf>low&&pf<high)||(sf>low&&sf<high);if(!in)return 1;if((int)b->ic_ieee==(int)(int8_t)p&&!s)return 1;return(int)b->ic_ieee==(int)(int8_t)p&&secchan==(int)(int8_t)s;}
static int expected_report(struct ieee80211_channel*b,unsigned channel){unsigned secfreq;if(b->ic_flags&0x20000)secfreq=(b->ic_freq+20U)&65535;else if(b->ic_flags&0x40000)secfreq=(b->ic_freq-20U)&65535;else return 0;unsigned center=(b->ic_freq+secfreq)/2,low=(center-25U)&65535,high=(center+25U)&65535,f=frequency(channel);return f<low||f>high;}
int main(void){struct ieee80211_channel bss,current={9999,0,99};struct ieee80211com ic={&bss,&current};struct ieee80211vap vap={&ic};unsigned long paircases=0,reportcases=0;unsigned fs[]={0,1,19,20,24,25,2407,2412,2422,2437,2447,2462,2472,2484,65510,65516,65535};unsigned channels[]={0,1,6,14,127,128,255};
for(unsigned bw=0;bw<4;bw++)for(unsigned fi=0;fi<17;fi++)for(unsigned bi=0;bi<7;bi++){bss.ic_freq=fs[fi];bss.ic_ieee=channels[bi];bss.ic_flags=(bw&1?0x20000:0)|(bw&2?0x40000:0);for(unsigned p=0;p<256;p++)for(unsigned s=0;s<256;s++){assert(ieee80211_20_40_operation_permitted(&vap,p,s)==expected_pair(&bss,p,s));paircases++;}for(unsigned p=0;p<256;p++){assert(ieee80211_is_40_allowed(&vap,p)==expected_report(&bss,p));reportcases++;}}
for(unsigned bw=0;bw<4;bw++)for(unsigned f=0;f<65536;f++){bss.ic_freq=f;bss.ic_ieee=6;bss.ic_flags=(bw&1?0x20000:0)|(bw&2?0x40000:0);for(unsigned i=0;i<7;i++){unsigned p=channels[i],s=channels[(i+3)%7];assert(ieee80211_20_40_operation_permitted(&vap,p,s)==expected_pair(&bss,p,s));assert(ieee80211_is_40_allowed(&vap,p)==expected_report(&bss,p));paircases++;reportcases++;}}
ic.ic_bsschan=NULL;assert(!ieee80211_20_40_operation_permitted(&vap,1,5)&&!ieee80211_is_40_allowed(&vap,6));ic.ic_bsschan=IEEE80211_CHAN_ANYC;assert(!ieee80211_20_40_operation_permitted(&vap,1,5)&&!ieee80211_is_40_allowed(&vap,6));assert(paircases==33030144UL&&reportcases==1956864UL);return 0;}
'''
 f=a.output/'fixture.c';f.write_text(c);pins={str(source):sha(source),str(cp):sha(cp),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');proc=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr;proc=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(proc.stderr);assert proc.returncode==0,(proc.returncode,proc.stderr);assert all(sha(p)==h for p,h in pins.items());result=dict(status='PASS_ACTUAL_COEX26_OEM_BSS_LOW16_SIGNED8_GEOMETRY',hardware_accessed=False,firmware_eligible=False,pair_cases=33030144,report_cases=1956864,invalid_bss_cases=4,current_channel_deliberately_different=True,source_sha256=sha(source),helper_sha256=hashlib.sha256(helpers.encode()).hexdigest(),limits='Arithmetic+typedhelperproof withvalidBSSobject; noRF/PHY/trafficorfullparseracceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
