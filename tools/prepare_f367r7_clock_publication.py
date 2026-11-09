"""Align public remaining time with the unchanged two-clock admission guard."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f367r5-regulatory-profile'
DST=ROOT/'work/kernel-port/f367r7-clock-publication'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('clock source anchor '+a[:90])
 return s.replace(a,b,1)
def main():
 if DST.exists():raise ValueError('immutable R7 source exists')
 DST.mkdir(parents=True)
 for name in ('kernel','uapi','qdrv'):shutil.copytree(SRC/name,DST/name)
 p=DST/'qdrv/qdrv/qdrv_f367_control.inc';s=p.read_text()
 s=once(s,'void qdrv_f367_channel_fault(int error)', '''static u64 f367_ticks_remaining(u32 now,u32 deadline)
{
 if(f367_due(now,deadline))return 0;
 return div_u64((u64)(u32)(deadline-now)*1000ULL+HZ-1,HZ);
}
static u64 f367_max_remaining(u64 ns,u64 ticks){return ns>ticks?ns:ticks;}
static void f367_policy_clock_reject(const struct f367_ap_policy*p,u32 ticks,u64 now,u64 qend,u64 nend,bool prepared)
{
 const char*reason=!p->initialized?"uninitialized":!f367_due(ticks,p->boot_until)?"boot-ticks":
  (p->nop&&!f367_due(ticks,p->nop_until))?"nop-ticks":now<qend?"boot-ns":
  (p->nop&&now<nend)?"nop-ns":prepared?"transition":"unknown";
 pr_warn_ratelimited("OMF367_POLICY_CLOCK_REJECT reason=%s policy_initialized=%u tick_hz=%u jiffies_u32=%u boot_until_ticks=%u nop_until_ticks=%u nop_policy=%u transition_prepared=%u monotonic_ns=%llu quarantine_deadline_ns=%llu nop_deadline_ns=%llu quarantine_ns_remaining_ms=%llu quarantine_tick_remaining_ms=%llu\\n",
  reason,p->initialized,HZ,ticks,p->boot_until,p->nop_until,p->nop,prepared,
  (unsigned long long)now,(unsigned long long)qend,(unsigned long long)nend,
  (unsigned long long)f367_remaining(now,qend),(unsigned long long)f367_ticks_remaining(ticks,p->boot_until));
}
void qdrv_f367_channel_fault(int error)''')
 s=once(s,'u32 generation=qdrv_f332_generation(),provider_channel=0,provider_bw=0,request_generation;','u32 tick_now;u64 qns,qtk,cns,ctk,nns,ntk,qremaining,cremaining,nremaining;\n u32 generation=qdrv_f332_generation(),provider_channel=0,provider_bw=0,request_generation;')
 s=once(s,'spin_lock_irqsave(&f367_policy_lock,flags);policy=f367_policy;','spin_lock_irqsave(&f367_policy_lock,flags);policy=f367_policy;tick_now=(u32)jiffies;')
 s=once(s,' quarantine=!policy.initialized||now<qend;\n nop=policy.nop&&(!f367_due((u32)jiffies,policy.nop_until)||now<nend);', ''' qns=f367_remaining(now,qend);qtk=policy.initialized?f367_ticks_remaining(tick_now,policy.boot_until):0;
 cns=policy.cac_pending?f367_remaining(now,cend):0;ctk=policy.cac_pending?f367_ticks_remaining(tick_now,policy.cac_until):0;
 nns=policy.nop?f367_remaining(now,nend):0;ntk=policy.nop?f367_ticks_remaining(tick_now,policy.nop_until):0;
 qremaining=f367_max_remaining(qns,qtk);cremaining=f367_max_remaining(cns,ctk);nremaining=f367_max_remaining(nns,ntk);
 quarantine=!policy.initialized||qremaining!=0;
 nop=policy.nop&&nremaining!=0;''')
 s=once(s,'(unsigned long long)f367_ms(qstart),(unsigned long long)f367_ms(qend),(unsigned long long)f367_remaining(now,qend),','(unsigned long long)f367_ms(qstart),(unsigned long long)f367_ms(qend),(unsigned long long)qremaining,')
 s=once(s,'(unsigned long long)(policy.cac_pending?f367_remaining(now,cend):0),','(unsigned long long)cremaining,')
 s=once(s,'(unsigned long long)(nop?f367_remaining(now,nend):0),','(unsigned long long)nremaining,')
 fields=['policy_initialized','tick_hz','jiffies_u32','boot_until_ticks','cac_until_ticks','nop_until_ticks','nop_policy']
 times=['quarantine_ns_remaining_ms','quarantine_tick_remaining_ms','cac_ns_remaining_ms','cac_tick_remaining_ms','nop_ns_remaining_ms','nop_tick_remaining_ms']
 fmt=''.join('\\"'+name+'\\":%u,' for name in fields)+''.join('\\"'+name+'\\":%llu,' for name in times)
 s=once(s,'\\"rf_silence_proven\\":false}',fmt+'\\"rf_silence_proven\\":false}')
 s=once(s,'target_present,target_active,target_dfs,target_radar,publish_allowed);', '''target_present,target_active,target_dfs,target_radar,publish_allowed,
  policy.initialized,HZ,tick_now,policy.boot_until,policy.cac_until,policy.nop_until,policy.nop,
  (unsigned long long)qns,(unsigned long long)qtk,(unsigned long long)cns,(unsigned long long)ctk,(unsigned long long)nns,(unsigned long long)ntk);''')
 s=once(s,'unsigned long flags;bool allowed;u64 now=ktime_get_ns();(void)parameter;', 'unsigned long flags;bool allowed,observed_prepared;u64 now=ktime_get_ns(),observed_qend,observed_nend;u32 observed_ticks;\n struct f367_ap_policy observed_policy;(void)parameter;')
 guard='''  allowed=f367_dfs_clear(&f367_policy,(u32)jiffies)&&now>=f367_quarantine_deadline_ns&&
   (!f367_policy.nop||now>=f367_nop_deadline_ns)&&!f367_transition_prepared;'''
 assert s.count(guard)==1
 s=once(s,guard,guard+'''
  /* IRQs remain disabled: these are the same values consumed by the guard. */
  observed_policy=f367_policy;observed_ticks=(u32)jiffies;
  observed_qend=f367_quarantine_deadline_ns;observed_nend=f367_nop_deadline_ns;observed_prepared=f367_transition_prepared;''')
 s=once(s,'if(!allowed)return f367_control_reject("prepare-policy-clock-nop-or-transition",-EBUSY);', '''if(!allowed){f367_policy_clock_reject(&observed_policy,observed_ticks,now,observed_qend,observed_nend,observed_prepared);return f367_control_reject("prepare-policy-clock-nop-or-transition",-EBUSY);}''')
 p.write_bytes(s.encode())
 previous=json.loads((SRC/'source-manifest.json').read_text());pins={p.relative_to(DST).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (DST/sub).rglob('*') if p.is_file()}
 changed=[name for name,digest in pins.items() if previous['source_pins'].get(name)!=digest];assert changed==['qdrv/qdrv/qdrv_f367_control.inc']
 # These guards/deadline producers are intentionally unchanged in this revision.
 assert guard in s
 for name in ('qdrv_f367_ap.inc','f367_ap_policy.h','qdrv_radar.c'):assert sha(DST/'qdrv/qdrv'/name)==sha(SRC/'qdrv/qdrv'/name)
 report=dict(schema='openmitrastar.f367r7-clock-source/v1',status='PREPARED_FOR_AFFECTED_CLOCK_CHECKS',source_pins=pins,baseline_source=str(SRC),baseline_pins=previous['source_pins'],changed_files=changed,admission_guard_unchanged=guard,deadline_producers_unchanged=True,physical_prerequisite=previous['physical_prerequisite'],userspace_pins=previous['userspace_pins'],producer_and_layout_pins=previous['producer_and_layout_pins'],hardware_actions=False)
 (DST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(source=str(DST),changed_files=changed)))
if __name__=='__main__':main()
