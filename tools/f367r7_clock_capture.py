"""Preserve published clock/guard integers; do not infer physical clock drift."""
import json,os,time
import f367r6_campaign_worker as previous

FIELDS=('policy_initialized','tick_hz','jiffies_u32','boot_until_ticks','cac_until_ticks','nop_until_ticks','nop_policy',
        'quarantine_ns_remaining_ms','quarantine_tick_remaining_ms','cac_ns_remaining_ms','cac_tick_remaining_ms','nop_ns_remaining_ms','nop_tick_remaining_ms',
        'transition_prepared','switch_inflight','monotonic_ms','quarantine_active','quarantine_started_ms','quarantine_deadline_ms','quarantine_remaining_ms',
        'cac_active','cac_started_ms','cac_deadline_ms','cac_remaining_ms','nop_active','nop_started_ms','nop_deadline_ms','nop_remaining_ms',
        'channel','filter_bw','configured','region_eu','region_es','control_fault','tx_fault_latched')

def clock_observation(row):
    safe={key:row[key] for key in FIELDS if type(row.get(key)) is int and row[key]>=0}
    return dict(schema='openmitrastar.f367r7-clock-observation/v1',snapshot=safe,
                missing_or_invalid_fields=[key for key in FIELDS if key not in safe],
                physical_clock_drift_measured=False,deadlines_modified=False)

class Host(previous.Host):
    def record(self,label,row):
        if 'monotonic_ms' in row:
            evidence=clock_observation(row)
            evidence.update(stage=label,host_monotonic_ms=round(time.monotonic()*1000))
            with (self.out/'clock-snapshots.jsonl').open('a',encoding='ascii') as stream:
                stream.write(json.dumps(evidence)+'\n');stream.flush();os.fsync(stream.fileno())
            previous.core.save(self.out/'clock-progress.json',evidence)
            # Failed capture remains on disk before the existing STOP/return.
            previous.require(not evidence['missing_or_invalid_fields'],'r7_clock_capture_incomplete')
        return super().record(label,row)
