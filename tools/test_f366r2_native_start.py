"""Execute actual qdrv admission/handler bodies and rejected native-start cases."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f366r2/qdrv/qdrv/qdrv_control.c'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;typedef uint8_t u8;
#define IEEE80211_ADDR_LEN 6
#define BIT(n) (1u<<(n))
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_CHAN_ANYC ((struct channel*)-1)
#define pr_err(...) do{}while(0)
#define pr_info(...) do{}while(0)
#define printk(...) do{}while(0)
struct device{int unused;};struct qdrv_mac{int unused;};struct channel{unsigned ic_ieee;};
struct qdrv_wlan{struct{unsigned ic_opmode,ic_radar_bw;struct channel*ic_curchan;}ic;};
static struct qdrv_mac mac;static struct channel channel;static struct qdrv_wlan wlan;
static int openmitrastar_sequential_bringup,openmitrastar_clearsram_only,openmitrastar_core_start_only;
static int openmitrastar_sequential_started,openmitrastar_single_vap_create,openmitrastar_sequential_vap_created,openmitrastar_sequential_mac0_valid;
static u8 openmitrastar_sequential_mac0[6];static unsigned openmitrastar_sequential_mask;
static int openmitrastar_sequential_cleared,openmitrastar_sequential_wps_gpio4_configured;
static int openmitrastar_native_radar_diagnostic;static bool f366_native_radar_attempted;
static unsigned called,checks;static bool missing;
static int qdrv_parse_mac(const char*s,u8*out){(void)s;memset(out,0,6);return 0;}
static int qdrv_sequential_set_bit(const char*s,u32*out){(void)s;*out=0;return -1;}
static struct qdrv_mac*qdrv_control_mac_get(struct device*d,const char*s){(void)d;assert(!strcmp(s,"0"));return missing?NULL:&mac;}
static struct qdrv_wlan*qdrv_control_wlan_get(struct qdrv_mac*m){assert(m==&mac);return &wlan;}
static void qdrv_radar_enable(const char*region){assert(f366_native_radar_attempted&&!strcmp(region,"eu"));called++;}
static void qdrv_radar_disable(void){assert(0);}
#define CHECK(x) do{checks++;assert(x);}while(0)
static void reset(void){openmitrastar_sequential_bringup=1;openmitrastar_clearsram_only=openmitrastar_core_start_only=0;openmitrastar_sequential_started=openmitrastar_sequential_vap_created=openmitrastar_single_vap_create=openmitrastar_sequential_mac0_valid=1;openmitrastar_native_radar_diagnostic=1;f366_native_radar_attempted=false;called=0;missing=false;channel.ic_ieee=36;wlan.ic.ic_curchan=&channel;wlan.ic.ic_radar_bw=80;wlan.ic.ic_opmode=IEEE80211_M_HOSTAP;}
'''
TEST=r'''
int main(void){char*good[]={"radar","enable","eu"};char*off[]={"radar","disable","eu"};char*region[]={"radar","enable","us"};char*extra[]={"radar","enable","eu","extra"};char*get[]={"get","0","info"};
 reset();openmitrastar_native_radar_diagnostic=0;CHECK(qdrv_sequential_precheck(3,good)==-EPERM&&!called);
 reset();openmitrastar_sequential_started=0;CHECK(qdrv_sequential_precheck(3,good)==-EPERM&&!called);
 reset();openmitrastar_sequential_vap_created=0;CHECK(qdrv_sequential_precheck(3,good)==-EPERM&&!called);
 reset();openmitrastar_core_start_only=1;CHECK(qdrv_sequential_precheck(3,good)==-EPERM&&!called);
 reset();CHECK(qdrv_sequential_precheck(3,off)==-EPERM);CHECK(qdrv_command_radar(NULL,3,off)==-EPERM&&!called);
 reset();CHECK(qdrv_sequential_precheck(3,region)==-EPERM);CHECK(qdrv_command_radar(NULL,3,region)==-EPERM&&!called);
 reset();CHECK(qdrv_sequential_precheck(4,extra)==-EPERM);CHECK(qdrv_command_radar(NULL,4,extra)==-EPERM&&!called);
 reset();missing=true;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&!called&&!f366_native_radar_attempted);
 reset();channel.ic_ieee=52;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&!called);
 reset();wlan.ic.ic_radar_bw=20;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&!called);
 reset();wlan.ic.ic_opmode=1;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&!called);
 reset();wlan.ic.ic_curchan=IEEE80211_CHAN_ANYC;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&!called);
 reset();wlan.ic.ic_curchan=NULL;CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&!called);
 reset();CHECK(!qdrv_sequential_precheck(3,good));CHECK(!qdrv_command_radar(NULL,3,good)&&called==1&&f366_native_radar_attempted);
 CHECK(qdrv_sequential_precheck(3,good)==-EPERM);CHECK(qdrv_command_radar(NULL,3,good)==-EPERM&&called==1);
 CHECK(!qdrv_sequential_precheck(3,get));CHECK(f366_native_radar_attempted);
 printf("F366R2_ACTUAL_START_GATE_PASS checks=%u hardware=0 failure_consumes_attempt=1\n",checks);return 0;}
'''
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f366r2-start-gate-'+stamp);out.mkdir(parents=True,exist_ok=False)
 s=SOURCE.read_text();macros='\n'.join(line for line in s.replace('\\\n','').splitlines() if line.startswith('#define OMQDRVSEQ_'))
 (out/'test.c').write_bytes((PRE+macros+'\n'+extract(s,'qdrv_sequential_precheck')+extract(s,'qdrv_command_radar')+TEST).encode())
 script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -pedantic '{linux(out/'test.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=30)
 result={'schema':'openmitrastar.f366r2-native-start-tests/v1','status':'PASS_ACTUAL_QDRV_NATIVE_START_ADMISSION' if not run.returncode else 'FAIL','source':{'path':str(SOURCE),'sha256':sha(SOURCE)},'stdout':run.stdout.strip(),'stderr':run.stderr[-3000:],'hardware_actions':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
