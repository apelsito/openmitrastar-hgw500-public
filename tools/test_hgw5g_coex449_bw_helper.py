"""Actual changeBW C fixture: wire/map/power/callback order and metadata preservation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);helper=a.source.read_text();c=r'''#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stddef.h>
#include <stdarg.h>
#define IEEE80211_PARAM_BW_SEL_MUC 71
#define BW_HT20 20
#define BW_HT40 40
#define BW_HT80 80
#define CTRY_DEFAULT 0
#define PWR_IDX_20M 0
#define PWR_IDX_40M 1
#define PWR_IDX_80M 2
#define PWR_IDX_BF_OFF 0
#define PWR_IDX_1SS 0
#define isset(p,n) (((p)[(n)>>3]>>((n)&7))&1)
struct ieee80211_channel {uint8_t ic_ieee;int8_t ic_maxpower,ic_maxpower_normal;int8_t ic_maxpower_table[2][4][3];uint32_t flags,calibration_sentinel;};
struct ieee80211com {uint8_t ic_chan_active[32],ic_chan_active_20[32],ic_chan_active_40[32],ic_chan_active_80[32];uint16_t ic_country_code;int ic_nchans;struct ieee80211_channel ic_channels[256];void(*ic_set_channel)(struct ieee80211com*);};
struct ieee80211vap {struct ieee80211com*iv_ic;};
static unsigned wire,channel,logs;static int value_seen;static uint8_t before_map[32],expect_map[32];static struct ieee80211com expected;
static void ieee80211_param_to_qdrv(struct ieee80211vap*v,int id,int bw,void*p,int len){assert(id==71&&!p&&!len&&!wire&&!channel&&!memcmp(v->iv_ic->ic_chan_active,before_map,32));wire++;value_seen=bw;}
static int printk(const char*fmt,...){assert(wire==1&&!channel);logs++;return 0;}
static void setchan(struct ieee80211com*ic){assert(wire==1&&channel==0&&!memcmp(ic,&expected,sizeof(*ic)));channel++;}
'''+helper+r'''
int main(void){struct ieee80211com ic;struct ieee80211vap vap={&ic};unsigned country,delay,pattern,b;int widths[]={20,40,80,0,-1,81};unsigned long cases=0;
for(country=0;country<2;country++)for(delay=0;delay<3;delay++)for(pattern=0;pattern<256;pattern++)for(b=0;b<6;b++){
memset(&ic,0,sizeof(ic));ic.ic_country_code=country?724:0;ic.ic_nchans=256;ic.ic_set_channel=setchan;memset(ic.ic_chan_active,0xa5,32);for(unsigned k=0;k<32;k++){ic.ic_chan_active_20[k]=(uint8_t)pattern;ic.ic_chan_active_40[k]=(uint8_t)(pattern^0x55);ic.ic_chan_active_80[k]=(uint8_t)(pattern^0xaa);}for(unsigned n=0;n<256;n++){struct ieee80211_channel*c=&ic.ic_channels[n];c->ic_ieee=n;c->ic_maxpower=-99;c->ic_maxpower_normal=99;c->flags=0x98765432;c->calibration_sentinel=0x1234abcd;for(unsigned x=0;x<2;x++)for(unsigned y=0;y<4;y++)for(unsigned z=0;z<3;z++)c->ic_maxpower_table[x][y][z]=(int8_t)((n+z*11+x*31+y*5)%127);}
expected=ic;memcpy(before_map,ic.ic_chan_active,32);int bw=widths[b];memcpy(expect_map,bw==40?ic.ic_chan_active_40:(bw==80?ic.ic_chan_active_80:ic.ic_chan_active_20),32);memcpy(expected.ic_chan_active,expect_map,32);if(country&&(bw==20||bw==40||bw==80)){int idx=bw==20?0:(bw==40?1:2);for(unsigned n=0;n<256;n++)if(isset(expect_map,n)){expected.ic_channels[n].ic_maxpower=expected.ic_channels[n].ic_maxpower_table[0][0][idx];expected.ic_channels[n].ic_maxpower_normal=expected.ic_channels[n].ic_maxpower;}}
wire=channel=logs=0;om_ieee80211_change_bw(&vap,bw,delay);assert(wire==1&&value_seen==bw&&channel==(delay==0)&&logs==(country&&bw!=20&&bw!=40&&bw!=80));assert(!memcmp(&ic,&expected,sizeof(ic)));cases++;}
assert(cases==9216UL);return 0;}
'''
 f=a.output/'fixture.c';f.write_text(c);pins={str(a.source):sha(a.source),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');proc=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr;proc=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert proc.returncode==0,proc.stderr
 for path,h in pins.items():assert sha(path)==h
 result=dict(status='PASS_ACTUAL_CHANGE_BW_WIRE_MAP_POWER_CALLBACK_HOST_FIXTURE',hardware_accessed=False,firmware_eligible=False,cases=9216,channel_rows_per_case=256,source_sha256=sha(a.source),callback_order='wire71beforeactivemap/powerbeforeoptionalsetchannel',unchanged_other_fields_full_object=True,limits='Typedfakecallbacks; nohardware/PHY/regulatoryorcalibrationacceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
