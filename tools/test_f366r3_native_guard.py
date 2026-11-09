"""Run the actual R3 guard with the real RAM-only radar_bw producer case."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import test_f366r2_native_start as previous
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f366r3/qdrv/qdrv/qdrv_control.c'
WLAN=ROOT/'work/linux510-radio-port/quantenna/wlan/ieee80211_wireless.c'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f366r3-guard-'+stamp);out.mkdir(parents=True,exist_ok=False)
 s=SOURCE.read_text();macros='\n'.join(line for line in s.replace('\\\n','').splitlines() if line.startswith('#define OMQDRVSEQ_'))
 pre=previous.PRE.replace('struct channel','struct ieee80211_channel')
 pre=pre.replace('struct qdrv_wlan{struct{unsigned ic_opmode,ic_radar_bw;struct ieee80211_channel*ic_curchan;}ic;};','struct ieee80211com{unsigned ic_opmode,ic_radar_bw,ic_phymode;struct ieee80211_channel*ic_curchan;};\nstruct qdrv_wlan{struct ieee80211com ic;};')
 pre=pre.replace('#include <stdio.h>','#include <stdio.h>\n#include <stdarg.h>\nstatic char guard_log[2048];static unsigned ram_reads;\nstatic void test_log(const char*fmt,...){va_list ap;if(!strstr(fmt,"OMF366_NATIVE_GUARD"))return;va_start(ap,fmt);vsnprintf(guard_log,sizeof(guard_log),fmt,ap);va_end(ap);}\n#define READ_ONCE(v) (ram_reads++,(v))\n#define IEEE80211_PARAM_RADAR_BW 235')
 pre=pre.replace('#define pr_info(...) do{}while(0)','#define pr_info(...) test_log(__VA_ARGS__)')
 pre=pre.replace('called=0;missing=false;','called=0;missing=false;ram_reads=0;guard_log[0]=0;wlan.ic.ic_phymode=13;')
 producer='case IEEE80211_PARAM_RADAR_BW:\n\t\tic->ic_radar_bw = value;\n\t\tbreak;'
 assert producer in WLAN.read_text()
 pre+='\nstatic void original_radar_bw_setparam(struct ieee80211com*ic,int param,int value){switch(param){'+producer+'default:assert(0);}}\n'
 extra=r'''
 reset();wlan.ic.ic_radar_bw=0;
 CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&!called);
 CHECK(strstr(guard_log,"reason=radar-filter-not-80")&&strstr(guard_log,"channel=36 radar_bw=0 phymode=13")&&strstr(guard_log,"reads=ram-only")&&ram_reads==5);
 original_radar_bw_setparam(&wlan.ic,235,80);
 CHECK(wlan.ic.ic_radar_bw==80&&wlan.ic.ic_opmode==6&&wlan.ic.ic_phymode==13&&wlan.ic.ic_curchan->ic_ieee==36);
 ram_reads=0;CHECK(!qdrv_command_radar(NULL,3,good)&&called==1&&f366_native_radar_attempted);
 CHECK(strstr(guard_log,"reason=allow")&&strstr(guard_log,"radar_bw=80 phymode=13")&&ram_reads==5);
 CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&strstr(guard_log,"reason=attempt-already-used"));
 reset();wlan.ic.ic_opmode=1;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&strstr(guard_log,"reason=not-ap"));
 reset();channel.ic_ieee=52;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&strstr(guard_log,"reason=not-channel36"));
 reset();missing=true;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&strstr(guard_log,"reason=missing-mac")&&ram_reads==0);
 reset();{char*off_literal[]={"radar","off"};CHECK(qdrv_command_radar(NULL,2,off_literal)==-EPERM&&!called&&strstr(guard_log,"reason=command-not-exact-eu"));}
'''
 test=previous.TEST.replace(' printf("F366R2_ACTUAL_START_GATE_PASS',extra+' printf("F366R3_ACTUAL_GUARD_AND_PRODUCER_PASS')
 (out/'test.c').write_bytes((pre+macros+'\n'+extract(s,'qdrv_sequential_precheck')+extract(s,'qdrv_command_radar')+test).encode())
 script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -pedantic '{linux(out/'test.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=30)
 result={'schema':'openmitrastar.f366r3-guard-tests/v1','status':'PASS_ACTUAL_QDRV_GUARD_AND_RADAR_BW_PRODUCER' if not run.returncode else 'FAIL','source':{'path':str(SOURCE),'sha256':sha(SOURCE)},'producer':{'path':str(WLAN),'sha256':sha(WLAN),'case_sha256':hashlib.sha256(producer.encode()).hexdigest()},'stdout':run.stdout.strip(),'stderr':run.stderr[-3000:],'hardware_actions':False,'runtime_state_in_fixture':'explicitly simulated, not evidence of the R2 physical rejection value'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
