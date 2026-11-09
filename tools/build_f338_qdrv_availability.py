"""Offline build of the qdrv asynchronous detector-readiness handshake."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,shutil,subprocess
import f334_qdrv_contract as elf

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/linux510-radio-port/quantenna-f338-availability'
PROVIDER=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f338-kernel-20260921T130742Z/a/kernel/Module.symvers'
BASELINE=ROOT/'outputs/kernel-port/f334-qdrv-profile-20260921T105936Z/qdrv-f334-external-radar.ko'
KERNEL='/home/user/mitrastar-linux-5.10.260'
KOUT='/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def function(source,name):
    match=re.search(r'(?m)^(?:static )?(?:void|int|bool) '+name+r'\([^;]*?\)\n\{',source)
    assert match,name
    start=match.start();index=match.end();level=1
    while level:level+=(source[index]=='{')-(source[index]=='}');index+=1
    return source[start:index]

def contracts():
    source=(SOURCE/'qdrv/qdrv_radar.c').read_text();helper=(SOURCE/'qdrv/qdrv_f332_ready.inc').read_text()
    start=function(source,'start_cac');complete=function(source,'cac_completed_action');after=function(source,'qdrv_radar_on_newchan')
    assert start.index('qdrv_f332_begin_cac')<start.index('mod_timer')
    assert complete.index('qdrv_f332_complete_cac')<complete.index('sys_enable_xmit()')
    assert after.index('qdrv_f332_wait_ready')<after.index('start_cac()')
    assert after.index('qdrv_f332_wait_ready')<after.index('sys_enable_xmit()')
    tasklet=function(source,'qdrv_ocac_tasklet')
    assert tasklet.index('radar_set_scan_context')<tasklet.index('qdrv_f332_wait_ready')<tasklet.index('radar_record_buffer_pt')
    assert 'actual_dwell_time' not in tasklet
    assert 'qdrv_f332_ocac_record' in tasklet and 'if(overflow)' in tasklet
    rec=function(helper,'qdrv_f332_ocac_record')
    assert rec.index('spin_lock(&radar->lock)')<rec.index('index = radar->array_ps')<rec.index('ARRAY_SIZE(radar->ocac_radar_pts)')<rec.index('radar->ocac_radar_pts[index]')
    assert rec.index('qdrv_f332.begin_generation != generation')<rec.index('ocac_accum_cac_time_ms +=')
    exitfn=function(source,'qdrv_radar_exit')
    assert exitfn.index('qdrv_f332_ready_join')<exitfn.index('radar_wait_stopped')<exitfn.index('memset(&qdrv_radar_cb')
    assert 'if(rc)return rc' in exitfn
    soc=function((SOURCE/'qdrv/qdrv_soc.c').read_text(),'qdrv_soc_exit')
    assert soc.index('qdrv_radar_exit')<soc.index('qdrv_muc_exit')<soc.index('qdrv_soc_revoke_params')
    assert 'qdrv_radar_on_newchan()' in function(source,'qdrv_radar_enable_radar_detection')
    assert 'qdrv_radar_on_newchan()' in function(source,'radar_pm_notify')
    assert 'CAC_PERIOD\t\t(70 * HZ)' in source and 'CAC_WEATHER_PERIOD_EU\t(600 * HZ)' in source
    health=(SOURCE/'qdrv/qdrv_f338_availability.inc').read_text()
    init=function(source,'qdrv_radar_init')
    assert init.index('qdrv_f338_health_init')<init.index('radar_register_availability')
    assert init.index('qdrv_radar_configured = true')<init.index('radar_register_availability')
    assert 'qdrv_radar_exit(mac)' in init
    assert 'qdrv_f338_enable_tx' in function(source,'sys_enable_xmit')
    assert complete.index('ic_mark_channel_dfs_cac_status(ic, chan, IEEE80211_CHAN_DFS_CAC_IN_PROGRESS, false)')<complete.index('if (!sys_enable_xmit())')
    assert 'cancel_delayed_work_sync' not in health and 'del_timer_sync' not in health
    assert 'start_nonoccupy' not in health and 'qdrv_radar_detected(' not in health
    assert 'if (!ieee80211_is_chan_radar_detected(channel)' in health
    assert health.index('static bool qdrv_f338_enable_tx')<health.index('sys_raw_enable_xmit()')<health.index('qdrv_f332_generation() != generation')
    return source,exitfn

def shutdown_harness(exitfn):
    prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define RUBY_M2L_IRQ_LO_OCAC 1
#define PM_QOS_POWER_SAVE 1
struct qdrv_mac {int unit,irq;};
struct channel_context {unsigned ic_nchans;struct {int sta_radar_timer;} sta_dfs_info;};
static struct {bool enabled;struct channel_context*ic;struct {bool initialized;int sample_work;}muc_sampling;int ocac_tasklet,cac_timer,dfs_cs_timer,nonoccupy_timer[3],pm_notifier;} qdrv_radar_cb;
static bool qdrv_radar_configured,qdrv_radar_first_call,qdrv_radar_sta_dfs;
static unsigned steps[32],count;static int drain_rc;
static void add(unsigned value){steps[count++]=value;}
static void qdrv_f332_ready_join(void){add(1);}
static void sys_disable_xmit(void){add(2);}
static void qdrv_mac_disable_irq(struct qdrv_mac*m,int irq){(void)m;(void)irq;add(3);}
static void synchronize_irq(int irq){(void)irq;add(4);}
static void tasklet_kill(int*p){(void)p;add(5);}
static void cancel_delayed_work_sync(int*p){(void)p;add(6);}
static void del_timer_sync(int*p){(void)p;add(7);}
static void qdrv_radar_disable(void){add(8);qdrv_radar_cb.enabled=false;}
static void pm_qos_remove_notifier(int n,int*p){(void)n;(void)p;add(9);}
static void sys_stop_radarmod(void){add(10);}
static int radar_wait_stopped(void){add(11);return drain_rc;}
'''
    tail=r'''
static void setup(struct channel_context*ic){memset(&qdrv_radar_cb,0,sizeof(qdrv_radar_cb));qdrv_radar_cb.ic=ic;qdrv_radar_cb.enabled=true;qdrv_radar_cb.muc_sampling.initialized=true;qdrv_radar_configured=true;count=0;drain_rc=0;}
int main(void){struct qdrv_mac mac={0,7};struct channel_context ic={2,{0}};
 setup(&ic);assert(qdrv_radar_exit(&mac)==0);assert(!qdrv_radar_cb.ic&&!qdrv_radar_configured&&qdrv_radar_first_call);assert(steps[0]==1&&steps[count-1]==11);
 setup(&ic);drain_rc=-11;assert(qdrv_radar_exit(&mac)==-11);assert(qdrv_radar_cb.ic==&ic&&qdrv_radar_configured);
 count=0;qdrv_radar_configured=false;assert(qdrv_radar_exit(&mac)==0);assert(count==1);
 puts("F332_QDRV_TEARDOWN_PASS cases=3 real_exit_function=1 hardware=0");return 0;}
'''
    return prefix+'\n'+exitfn+'\n'+tail

def main():
    source,exitfn=contracts()
    assert ' qdrv_radar_compat.o ' not in (SOURCE/'qdrv/Makefile').read_text()
    assert PROVIDER.is_file()
    out=ROOT/'outputs/kernel-port'/('f338-qdrv-availability-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(SOURCE,out/'source');shutil.copyfile(Path(__file__),out/Path(__file__).name)
    (out/'test_shutdown.c').write_text(shutdown_harness(exitfn),encoding='ascii')
    (out/'source-contract.json').write_text(json.dumps({'status':'PASS_SOURCE_ORDER_AND_LIFETIME','checks':24,'hardware':False},indent=2)+'\n')
    q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
    script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic "$out/source/tests/test_ready.c" -o "$out/test_ready"
"$out/test_ready" >"$out/ready-tests.log"
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic "$out/test_shutdown.c" -o "$out/test_shutdown"
"$out/test_shutdown" >"$out/shutdown-tests.log"
cc -std=c11 -O0 -Wall -Wextra -Werror -pedantic -fanalyzer "$out/source/tests/test_ready.c" -o "$out/analyze_ready" >"$out/analyzer.log" 2>&1
test "$(sha256sum {q(KOUT)}/.config | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
cp {q(KOUT)}/.config "$out/kernel.config"
cp {q(linux(PROVIDER))} "$out/provider-Module.symvers"
awk '$3 !~ /\\/qdrv\\/qdrv$/ {{print}}' {q(linux(ROOT/'work/linux510-radio-port/quantenna/Module.symvers'))} >"$out/dependencies.symvers"
for kind in a b; do
 build=$(mktemp -d /home/user/openmitrastar-build/f338-qdrv-availability-$kind-XXXXXXXX)
 echo "$build" >"$out/$kind-directory.txt"
 cp -a "$out/source"/. "$build"/
 SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 \\
 make -C {q(KERNEL)} O={q(KOUT)} ARCH=arc CROSS_COMPILE="$tc" M="$build" QTN_GPL={q(linux(ROOT/'work/sources/Quantenna-GPL'))} KBUILD_EXTRA_SYMBOLS="$out/dependencies.symvers $out/provider-Module.symvers" KBUILD_MODPOST_WARN=1 -j8 modules >"$out/build-$kind.log" 2>&1
 if grep -Eq 'undefined!|ERROR: modpost|error:' "$out/build-$kind.log"; then exit 1; fi
 if grep -Eq 'qdrv_(f338_availability.inc|radar.c):.*frame size' "$out/build-$kind.log"; then exit 1; fi
 cp "$build/qdrv/qdrv.ko" "$out/qdrv-$kind.ko"
 cp "$build/Module.symvers" "$out/qdrv-$kind-Module.symvers"
 modinfo "$out/qdrv-$kind.ko" >"$out/modinfo-$kind.txt"
 "${{tc}}nm" -u "$out/qdrv-$kind.ko" >"$out/imports-$kind.txt"
done
cmp "$out/qdrv-a.ko" "$out/qdrv-b.ko"
'''
    (out/'build.sh').write_bytes(script.encode())
    p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','bash','--noprofile','--norc','-s'],input=script.encode(),capture_output=True,timeout=900)
    (out/'stdout.log').write_bytes(p.stdout);(out/'stderr.log').write_bytes(p.stderr)
    if p.returncode:
        print(json.dumps({'status':'FAIL_BUILD_OR_TEST','output':str(out),'returncode':p.returncode}));return 1
    candidate=elf.inspect(out/'qdrv-a.ko');baseline=elf.inspect(BASELINE);elf.assert_profile(candidate,baseline)
    imports=(out/'imports-a.txt').read_text()
    for name in ('radar_get_status','radar_start','radar_set_chan','radar_set_scan_context','radar_ready_generation','radar_wait_stopped','radar_register_availability'):
        assert ' U '+name+'\n' in imports,name
    assert any('qtn_radar_f338' in s for s in candidate['modinfo'] if s.startswith('depends='))
    result={'schema':'openmitrastar.f338-qdrv-availability/v1','status':'PASS_OFFLINE_AVAILABILITY_HANDSHAKE_AND_LIFETIME','generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'artifact':{'path':str(out/'qdrv-a.ko'),'bytes':candidate['bytes'],'sha256':candidate['sha256']},
      'reproducible':sha(out/'qdrv-a.ko')==sha(out/'qdrv-b.ko'),'parameter_profile_identical_to_f334':True,'parameter_count':len(candidate['parameters']),
      'ready_tests':(out/'ready-tests.log').read_text().strip(),'shutdown_tests':(out/'shutdown-tests.log').read_text().strip(),'static_source_checks':24,'analyzer':'PASS',
      'provider_symvers':str(PROVIDER),'provider_symvers_sha256':sha(PROVIDER),'hardware_actions':False,'physical_or_rf_acceptance':False,
      'sources':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sorted(SOURCE.rglob('*')) if p.is_file()]}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps({k:v for k,v in result.items() if k!='sources'},indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
