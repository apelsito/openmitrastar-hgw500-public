"""Proposed F336 run and file-only evidence checks. Has no hardware executor."""
from pathlib import Path
import argparse,json,time,re,math
import f336_wdt_ram_contract as c

def watchdog_inactive(record):
    reasons=[]
    if record.get('source')!='bootbase-owned-uart':reasons.append('source-not-bound')
    mapping=record.get('map_value')
    if type(mapping)!=int or not 0<=mapping<=0xffffffff or mapping&((1<<29)|(1<<30)):reasons.append('legacy-map-unproven')
    controls=record.get('controls',[]);counters=record.get('counters',[])
    if len(controls)!=2 or any(type(v)!=int or v<0 or v>0xffffffff for v in controls):reasons.append('two-valid-control-reads-required')
    elif any(v&1 for v in controls):reasons.append('watchdog-enable-bit-is-set')
    if len(counters)!=2 or any(type(v)!=int or v<0 or v>0xffffffff for v in counters):reasons.append('two-valid-counter-reads-required')
    elif counters[0]!=counters[1]:reasons.append('counter-moved-while-declared-disabled')
    if not record.get('same_target_and_lease') or not record.get('fresh'):reasons.append('fresh-binding-required')
    return {'watchdog_inactive_observed':not reasons,'reasons':reasons,'flash_allowed_by_f336':False}

def evaluate(trace):
    problems=[]
    baseline=trace.get('baseline',{});ram=trace.get('ram',{});returned=trace.get('return',{})
    if not baseline.get('pinned_f321') or not baseline.get('boot_id'):problems.append('baseline-f321-unproven')
    if ram.get('dt_marker')!='F336_WDT_RAM_ONLY' or '#336' not in ram.get('uts_version','') or not ram.get('uart_bound'):problems.append('ram-kernel-identity-unproven')
    if not ram.get('boot_id') or ram.get('boot_id')==baseline.get('boot_id'):problems.append('ram-boot-id-not-new')
    if trace.get('fallback_reset_requested') is not False:problems.append('fallback-reset-is-not-watchdog-proof')
    events=trace.get('probe_events',[]);ceases=[e for e in events if e.get('event')=='cease']
    armed=[i for i,e in enumerate(events) if e.get('event')=='armed']
    if len(ceases)!=1 or len(armed)!=1 or (ceases and armed and armed[0]>=events.index(ceases[0])):problems.append('arm-and-cease-sequence-missing')
    if ceases and ceases[0].get('fd_held') is not True:problems.append('descriptor-not-held-at-cease')
    if any(e.get('event') in ('verdict','close_after_verdict','controller_negative_verdict') for e in events):problems.append('probe-ended-before-reset-verdict')
    samples=[e for e in events if e.get('event')=='sample']
    if len(samples)<2 or any(e.get('unexplained_counter_increases')!=0 for e in samples):problems.append('counter-reload-observation-inadequate')
    counters=[];times=[]
    for sample in samples:
        ctl=sample.get('control');counter=sample.get('counter');elapsed=sample.get('since_last_pet_ms')
        if not isinstance(ctl,str) or not re.fullmatch('[0-9a-fA-F]{8}',ctl) or not int(ctl,16)&1:problems.append('armed-control-sample-invalid')
        if not isinstance(counter,str) or not re.fullmatch('[0-9a-fA-F]{8}',counter):problems.append('counter-sample-invalid')
        else:counters.append(int(counter,16))
        if type(elapsed)!=int or elapsed<0:problems.append('sample-clock-invalid')
        else:times.append(elapsed)
        if ceases and events.index(sample)<events.index(ceases[0]):problems.append('sample-before-cease')
    if len(counters)>1 and (any(b>a for a,b in zip(counters,counters[1:])) or counters[-1]==counters[0]):problems.append('counter-reloaded-or-did-not-move')
    if any(b<=a for a,b in zip(times,times[1:])):problems.append('sample-clock-not-increasing')
    if ceases and any(e.get('event')=='pet' for e in events[events.index(ceases[0])+1:]):problems.append('pet-event-after-cease')
    if ceases and any(e.get('program_pets')!=ceases[0].get('program_pets') for e in samples):problems.append('pet-after-cease')
    tx=trace.get('last_pet_host_send_ms');rx=trace.get('last_pet_host_ack_ms');reset=trace.get('uart_reset_host_ms')
    clocks_ok=all(type(v) in (int,float) and math.isfinite(v) for v in (tx,rx,reset)) and tx<=rx<reset
    if not clocks_ok:problems.append('reset-clock-domain-or-order-unproven')
    elif reset-rx>40000:problems.append('reset-outside-cessation-window')
    if not trace.get('uart_reset_observed') or trace.get('fatal_or_panic_marker'):problems.append('clean-uart-reset-unproven')
    post=watchdog_inactive(trace.get('post_reset_watchdog',{}))
    if not post['watchdog_inactive_observed']:problems.append('post-reset-watchdog-not-inactive')
    if not returned.get('pinned_f321') or returned.get('dt_marker_present') is not False or returned.get('uts_version')!=baseline.get('uts_version'):problems.append('actual-flash-f321-return-unproven')
    if not returned.get('boot_id') or returned.get('boot_id')==ram.get('boot_id'):problems.append('return-boot-id-not-new')
    return {'status':'CESSATION_RESET_AND_F321_RETURN_OBSERVED' if not problems else 'NOT_ACCEPTED',
            'problems':sorted(set(problems)),'reset_latency_bounds_ms':[reset-rx,reset-tx] if clocks_ok else None,
            'hardware_reset_cause_verified':False,'full_chip_reset_proven':False,'watchdog_clock_measured':False,
            'other_producers_excluded_between_samples':False,'evidence_only_not_hardware_execution':True,
            'flash_allowed_by_f336':False}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build-result',type=Path);ap.add_argument('--probe-result',type=Path);ap.add_argument('--output-dir',type=Path);ap.add_argument('--evaluate',type=Path);args=ap.parse_args()
    if args.evaluate:
        print(json.dumps(evaluate(json.loads(args.evaluate.read_text())),indent=2));return 0
    c.require(args.build_result and args.probe_result and args.output_dir,'build/probe evidence and new output required')
    build=json.loads(args.build_result.read_text());probe=json.loads(args.probe_result.read_text())
    c.require(build['status']=='PASS_OFFLINE_RAM_ARTIFACT_PHYSICAL_GATES_UNRUN' and probe['status']=='PASS_OFFLINE_NO_WATCHDOG_OPEN','unqualified inputs')
    for item in (build['artifact'],probe['artifact']):c.require(c.sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes'],'artifact drift')
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);artifact=build['artifact'];name=Path(artifact['path']).name
    query=[{'command':'md.l 0xe0000004 1','role':'verify legacy map before any watchdog address'},
           {'command':'md.l 0xf4000000 1','role':'CR enable bit; no write'},
           {'command':'md.l 0xf4000008 1','role':'CCVR sample A; no write'},
           {'host_wait_ms':200},
           {'command':'md.l 0xf4000000 1','role':'CR second fresh observation'},
           {'command':'md.l 0xf4000008 1','role':'CCVR sample B; no write'}]
    plan={'schema':'openmitrastar.f336-ram-watchdog-plan/v1','status':'OFFLINE_READY_LIVE_GATES_REQUIRED','created_unix':time.time(),
          'execute_implementation':False,'router_access_performed':False,'flash_allowed':False,'persistent_environment_writes':False,
          'kernel':artifact,'probe':probe['artifact'],'ram':build['memory'],'rootfs':build['rootfs'],
          'requires':['fresh pinned F321 and existing exact restoration/readback evidence','exclusive UART identity/lease and continuous RX capture',
                      'verified current LAN interface/address and attempt-only TFTP server','physical recovery availability for unknown clock/reset behavior'],
          'before_ram_boot':['read current bootcmd/bootselect; never invoke bootselect, runningbootcmd, run, or a script that may saveenv when bootm returns',
                             'evaluate Bootbase watchdog observations; refuse EN set or unknown mapping/state'],
          'watchdog_read_sequence':query,
          'ram_transfer_commands':['setenv ipaddr 192.168.1.90','setenv serverip <fresh-explicit-controller-IP>',f'tftpboot 0x83000000 {name}',
                                   'iminfo 0x83000000',f"crc32 0x83000000 0x{artifact['bytes']:x} 0x84000000",'md.l 0x84000000 1'],
          'expected_ram_crc32':artifact['crc32'],'before_handoff':'Repeat current EN check after transfer; never adopt an armed watchdog',
          'handoff_command':'bootm 0x83000000','ram_identity':{'dt_marker':'F336_WDT_RAM_ONLY','uts_version_contains':'#336','new_boot_id':True,'rootfs_release_still_f321':True},
          'before_arm':['helper --inspect only: no open; verify marker, identity, EN=0, counter visibility and no existing FD owner',
                        'record dw_wdt f336_probe_seen/control if registration failed; absence of /dev/watchdog is not proof of EN=0',
                        'record peer producer audit limits and observe counter reloads during cessation'],
          'probe_protocol':{'argv':['f336-wdt-probe','--session'],'stdin_initial':['ARM'],'pet_schedule':{'commands':24,'interval_ms':1000,'command':'PET'},
                            'then':['STATUS','CEASE'],'descriptor_held_through':'external reset or explicit negative verdict after 40 seconds',
                            'no_reset':'probe emits negative verdict before close; any later reset or SysRq recovery is not watchdog acceptance'},
          'after_reset':['Use continuous UART to establish reset without software fallback/panic',
                         'Repeat Bootbase CR/CCVR/map reads before any further operation; EN surviving reset blocks progression',
                         'Only with watchdog inactive, use separately validated DIRECT bootm of pinned F321 flash uImage; no run/bootselect/runningbootcmd',
                         'Require new boot ID, absent F336 DT marker, baseline F321 uts_version and pinned SSH/platform checks'],
          'not_proven':['watchdog oscillator frequency','full-chip reset or reset-cause bits','CPU/IRQ/bus-halt recovery','radio clients/traffic on new RAM kernel'],
          'recovery_direct_f321':{'status':'REQUIRES_EXACT_BOOTBASE_AND_F321_FLASH_HEADER_CRC_CONTRACT','commands':[],
                                  'rule':'No guessed flash address; no generic run, bootselect or runningbootcmd, even as rollback'},
          'forbidden':['saveenv','set_bootval','bootselect','runningbootcmd','run','bootselection writes','sf erase','sf write','mtd writes','using old bootbase_ram_tftp_one_shot.py',
                       'treating rootfs F321 release text as evidence that the RAM kernel has exited']}
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({'plan':str(out/'plan.json'),'status':plan['status'],'hardware_actions':False}));return 0
if __name__=='__main__':raise SystemExit(main())
