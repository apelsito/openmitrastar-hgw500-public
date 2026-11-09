"""Actual public coexistence parser combined with actual BSS geometry helpers.

Reuses retained raw-frame parser fixture declarations, replaces only its fake
allowed-channel helper with extracted geometry/frequency functions, and drives
valid report frames over every byte channel and representative BSS boundaries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

MAIN=r'''
static uint16_t ref_freq(unsigned c){if(c==14)return 2484;if(c<14)return(uint16_t)(2407U+c*5U);if(c<27)return(uint16_t)(2512U+(c-15U)*20U);return(uint16_t)(5000U+c*5U);}
static bool report_conflict(struct ieee80211_channel*b,unsigned c){unsigned sec;if(b->ic_flags&0x20000)sec=(b->ic_freq+20U)&65535;else if(b->ic_flags&0x40000)sec=(b->ic_freq-20U)&65535;else return true;unsigned center=(b->ic_freq+sec)/2,lo=(center-25U)&65535,hi=(center+25U)&65535,f=ref_freq(c);return f>=lo&&f<=hi;}
int main(void){struct ieee80211com ic;struct ieee80211vap v;struct ieee80211_node ni;struct ieee80211_frame wh;struct ieee80211_channel bss,current={9999,0,99};uint8_t bytes[16];unsigned frequencies[]={0,19,20,2407,2412,2422,2437,2462,2484,65510,65535};unsigned long tested=0;
for(unsigned fi=0;fi<11;fi++)for(unsigned bwflags=0;bwflags<4;bwflags++)for(unsigned channel=0;channel<256;channel++)for(unsigned coex=0;coex<32;coex++)for(unsigned policy=0;policy<2;policy++)for(unsigned mode=0;mode<2;mode++){
memset(&ic,0,sizeof(ic));memset(&v,0,sizeof(v));memset(bytes,0,sizeof(bytes));bss.ic_freq=frequencies[fi];bss.ic_flags=(bwflags&1?0x20000:0)|(bwflags&2?0x40000:0);bss.ic_ieee=6;ic.ic_bsschan=&bss;ic.ic_curchan=&current;ic.ic_opmode=6;ic.ic_phymode=mode?9:8;ic.om_20_40_bss_coex=policy;ic.ic_coex_stats_update=stats_cb;v.iv_ic=&ic;ni.ni_vap=&v;ni.ni_coex=0xa5;bytes[2]=72;bytes[3]=1;bytes[4]=coex;bytes[5]=73;bytes[6]=2;bytes[7]=81;bytes[8]=channel;struct sk_buff skb={bytes,9};sends=cancels=bw=stats=report_calls=grant_calls=0;
ieee80211_recv_action_public_coex(&ni,&skb,&wh,(void*)bytes,0);bool downgrade=policy&&mode&&((coex&6)||report_conflict(&bss,channel));assert(ni.ni_coex==coex&&!v.iv_stats.is_rx_elem_toosmall&&!v.iv_stats.is_rx_elem_unknown&&bw==downgrade&&stats==downgrade&&sends==!!(coex&8)&&grant_calls==!!(coex&8));tested++;}
assert(tested==1441792UL);return 0;}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parser-fixture',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);source=a.candidate/'source/wlan/ieee80211_input.c';t=source.read_text();start=t.index('int\nieee80211_20_40_operation_permitted(');end=t.index('int\nieee80211_check_mode(',start);geom=t[start:end];cp=a.candidate/'source/wlan/ieee80211.c';f=cp.read_text();start=f.index('u_int\nieee80211_ieee2mhz(');end=f.index('EXPORT_SYMBOL(ieee80211_ieee2mhz);',start);freq=f[start:end];parser_start=t.index('static void\nieee80211_recv_action_public_coex(');parser_end=t.index('/*\n * Process a public action frame',parser_start);parser=t[parser_start:parser_end]
 text=(a.parser_fixture/'fixture.c').read_text();text=text[:text.index('static void\nieee80211_recv_action_public_coex(')];text=text.replace('struct ieee80211com {int ic_opmode,ic_phymode;','struct ieee80211_channel {uint16_t ic_freq;uint32_t ic_flags;uint8_t ic_ieee;};\nstruct ieee80211com {struct ieee80211_channel*ic_bsschan,*ic_curchan;int ic_opmode,ic_phymode;',1);fake='static int ieee80211_is_40_allowed(struct ieee80211vap*v,int channel){report_calls++;return channel!=report_bad;}';assert text.count(fake)==1;text=text.replace(fake,'',1);defines='''typedef unsigned u_int;
#define IEEE80211_CHAN_2GHZ 0x80U
#define IEEE80211_CHAN_5GHZ 0x100U
#define IEEE80211_CHAN_HT40U 0x20000U
#define IEEE80211_CHAN_HT40D 0x40000U
#define IEEE80211_SEC_CHAN_OFFSET 4
#define IEEE80211_CHAN_SPACE 5
#define IEEE80211_BW_RANGE 25
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)(uintptr_t)0xffff)
''';text+='#include <stdbool.h>\n'+defines+freq+'\n'+geom+'\n'+parser+MAIN;path=a.output/'fixture.c';path.write_text(text);pins={str(source):sha(source),str(cp):sha(cp),str(a.parser_fixture/'fixture.c'):sha(a.parser_fixture/'fixture.c'),str(Path(__file__)):sha(__file__),str(a.compiler):sha(a.compiler)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(path),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr;r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert r.returncode==0,(r.returncode,r.stderr);assert all(sha(p)==h for p,h in pins.items());result=dict(status='PASS_ACTUAL_COEX26_PUBLIC_PARSER_WITH_BSS_GEOMETRY',hardware_accessed=False,firmware_eligible=False,cases=1441792,current_channel_deliberately_different=True,source_sha256=sha(source),limits='Actualrawpublicparser+actualgeometry withfakeBW/stats/send; physicalRX/MuC/PHY/RF/trafficunrun');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
