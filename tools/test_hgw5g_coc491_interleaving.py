"""Deterministic actual-source PM producer/CSA completion/stop interleavings.

Reuse the pinned full host fixture's extracted real helper bodies, replace its
main only, and inject producers immediately after real queue-lock releases.
Assertions cover completion-only runs, combined completion+request, trigger
snapshot, later-producer retention, immediate completion scheduling and stop.
No schedule exploration beyond stated hooks or physical behavior is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

MAIN=r'''
static struct ieee80211com*hook_ic;static unsigned hook_at,unlock_seen,hook_action;
static void test_unlock_hook(void){if(!hook_at||++unlock_seen!=hook_at)return;unsigned action=hook_action;hook_at=0;if(action==1)om_ieee80211_pm_queue_node_join(hook_ic);else if(action==2)ieee80211_pm_queue_work(hook_ic);else if(action==3)om_ieee80211_coc_quiesce(hook_ic);}
static void setup(struct ieee80211com*ic,struct ieee80211vap*v,struct ieee80211_channel*bss){memset(ic,0,sizeof(*ic));memset(v,0,sizeof(*v));bss->ic_flags=0;bss->ic_ieee=44;ic->ic_bsschan=bss;ic->ic_vaps.first=v;v->iv_dev=&dev;v->iv_opmode=6;ic->ic_dfs_is_eu_region=eu_cb;ic->ic_check_channel=check_cb;ic->om_coc_move_ndfs=1;ic->om_coc_last_switch=9;idle=0;eu=true;lookup_kind=2;check_ok=1;csa_rc=0;hook_at=unlock_seen=hook_action=0;reset();}
int main(void){struct ieee80211com ic;struct ieee80211vap v;struct ieee80211_channel bss;
/* Noactualproducer means no PMtransaction invented by an idle worker. */
setup(&ic,&v,&bss);om_coc_update_pm(&ic);assert(!qos_count&&!pick_count&&!queue_count&&!ic.om_coc_pm_pending);
/* Completion-only preserves sampledlevel even if idlestate changes later. */
setup(&ic,&v,&bss);ic.ic_csa_reason=9;idle=1;om_coc_finish_csa((uintptr_t)&ic);assert(finish_count==1&&queue_count==1&&!qos_count&&ic.om_coc_completion_pending&&!ic.om_coc_pm_pending);idle=0;reset();om_coc_update_pm(&ic);assert(qos_count==1&&qos_level==5&&!pick_count&&!ic.om_coc_completion_pending&&!ic.om_coc_pm_pending);
/* Nodejoincoalescedwithcompletion remains anactualnewtransaction. */
setup(&ic,&v,&bss);ic.ic_csa_reason=9;om_coc_finish_csa((uintptr_t)&ic);om_ieee80211_pm_queue_node_join(&ic);assert(ic.om_coc_completion_pending&&ic.om_coc_pm_pending&&ic.om_coc_pm_trigger==13&&delay_seen==0);reset();om_coc_update_pm(&ic);assert(qos_count==2&&pick_count==1&&check_count==1&&csa_count==1&&!ic.om_coc_pm_pending&&!ic.om_coc_completion_pending);
/* Producerafterconsume ownsnextpending request, cannotrewritecurrentcause. */
setup(&ic,&v,&bss);ic.om_coc_pm_pending=true;ic.om_coc_pm_trigger=0;hook_ic=&ic;hook_at=1;hook_action=1;om_coc_update_pm(&ic);assert(qos_count==1&&!pick_count&&queue_count==1&&ic.om_coc_pm_pending&&ic.om_coc_pm_trigger==13);reset();om_coc_update_pm(&ic);assert(qos_count==1&&pick_count==1&&csa_count==1&&!ic.om_coc_pm_pending);
/* Genericafterconsumenodejoin doesnoterasecause13; futuregenericretained. */
setup(&ic,&v,&bss);ic.om_coc_pm_pending=true;ic.om_coc_pm_trigger=13;hook_ic=&ic;hook_at=1;hook_action=2;om_coc_update_pm(&ic);assert(qos_count==1&&pick_count==1&&csa_count==1&&ic.om_coc_pm_pending&&ic.om_coc_pm_trigger==0);reset();om_coc_update_pm(&ic);assert(qos_count==1&&!pick_count&&!ic.om_coc_pm_pending);
/* Produceratcompletiondrain isretained ratherthanconsumedwithoutwork. */
setup(&ic,&v,&bss);ic.om_coc_completion_pending=true;ic.om_coc_completed_level=5;hook_ic=&ic;hook_at=2;hook_action=1;om_coc_update_pm(&ic);assert(qos_count==1&&qos_level==5&&!pick_count&&ic.om_coc_pm_pending&&ic.om_coc_pm_trigger==13);reset();om_coc_update_pm(&ic);assert(qos_count==1&&pick_count==1&&!ic.om_coc_pm_pending);
/* Completionpublicationpendingforcesbothgenericandjoinqueueimmediate. */
for(unsigned join=0;join<2;join++){setup(&ic,&v,&bss);ic.om_coc_completion_pending=true;idle=1;ic.ic_flags_qtn=32;ic.ic_opmode=1;if(join)om_ieee80211_pm_queue_node_join(&ic);else ieee80211_pm_queue_work(&ic);assert(delay_seen==0&&queue_count==1&&ic.om_coc_pm_pending);}
/* Stopwinsbeforequeuepublication: everyproducer/worker/callback refuses. */
setup(&ic,&v,&bss);om_ieee80211_coc_quiesce(&ic);reset();ieee80211_pm_queue_work(&ic);om_ieee80211_pm_queue_node_join(&ic);om_coc_update_pm(&ic);om_coc_finish_csa((uintptr_t)&ic);assert(!queue_count&&!qos_count&&!pick_count&&!finish_count&&!ic.om_coc_pm_pending);
assert(!irqdepth);return 0;}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);r=json.loads((a.fixture/'result.json').read_text());source=a.candidate/'source/wlan/ieee80211.c';assert sha(source)==r['source_sha256'];base=a.fixture/'fixture.c';text=base.read_text();text=text[:text.index('int main(void)')];needle='#define spin_unlock_irqrestore(lock,flags) do{assert(*(lock)==1);*(lock)=0;local_irq_restore(flags);}while(0)';assert text.count(needle)==1;text=text.replace(needle,'static void test_unlock_hook(void);\n'+needle.replace('local_irq_restore(flags);','local_irq_restore(flags);test_unlock_hook();'),1)+MAIN;f=a.output/'fixture.c';f.write_text(text);pins={str(source):sha(source),str(base):sha(base),str(a.fixture/'result.json'):sha(a.fixture/'result.json'),str(a.compiler):sha(a.compiler),str(Path(__file__)):sha(__file__)};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');proc=subprocess.run([str(a.compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(proc.stderr);assert proc.returncode==0,proc.stderr;proc=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(proc.stderr);assert proc.returncode==0,(proc.returncode,proc.stderr)
 for path,h in pins.items():assert sha(path)==h
 result=dict(status='PASS_ACTUAL_COC491_DEFERRED_COMPLETION_PRODUCER_INTERLEAVINGS',hardware_accessed=False,firmware_eligible=False,cases=9,hook_scope='Producerinjectedafterrealqueue-lockrelease1or2; noexhaustiveconcurrencyclaim',source_sha256=sha(source),limits='Deterministichostcallbackschedule, validobjectlifetime only; stopduringrunningworker requiresexternalcanceljoin andphysicalPM/CSAacceptance remainsUNRUN');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
