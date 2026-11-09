"""F367 bounded campaign logic; I/O belongs to the owning host adapter.

Software radar exercises control plumbing only. No result here certifies RF
silence, calibrated radar detection or release acceptance.
"""
import time

class CampaignError(RuntimeError):
    pass

def require(value, reason):
    if not value:
        raise CampaignError(reason)

COMMON = ('monotonic_ms','channel','filter_bw','phymode','configured','region_eu','region_es','doth','tpc','provider_present','started','hardware_ready','ready','jobs_completed','errors','generation','quarantine_remaining_ms','waiting_detector','cac_active','cac_valid_continuity','cac_done','cac_remaining_ms','nop_active','nop_remaining_ms','tx_admission','tx_stop_command_confirmed','tx_fault_latched','control_fault','software_injections','native_callbacks','provider_callbacks')
PROVIDER_FIELDS = ('provider_started','provider_hardware_ready','provider_ready','provider_callbacks','job_timeouts','protocol_errors','hardware_errors','engine_fault_latched','last_error','ipc_session','service_closes')

def normalize_snapshot(row):
    require(all(type(row.get(key)) is int for key in PROVIDER_FIELDS),'provider_status_fields_missing')
    result=dict(row)
    for alias,source in {'started':'provider_started','hardware_ready':'provider_hardware_ready','ready':'provider_ready'}.items():
        require(alias not in row or row[alias]==row[source],'ambiguous_provider_alias_'+alias)
        result[alias]=row[source]
    errors=sum(row[key] for key in ('job_timeouts','protocol_errors','hardware_errors','engine_fault_latched','service_closes'))+int(row['last_error']!=0)
    require('errors' not in row or row['errors']==errors,'ambiguous_provider_errors')
    result['errors']=errors
    return result

def validate(row, previous=None):
    require(row.get('schema') == 'openmitrastar.f367-state/v1', 'status_schema')
    require(all(type(row.get(key)) is int and row[key] >= 0 for key in COMMON), 'status_numbers')
    require(row['provider_present'] == row['started'] == row['hardware_ready'] == 1, 'native_acquisition_unavailable')
    require(row['configured']==row['region_eu']==row['region_es']==row['doth']==row['tpc']==1,'regulatory_context_changed')
    require(row['errors'] == row['tx_fault_latched'] == row['control_fault'] == 0, 'runtime_fault')
    require(row['native_callbacks'] == 0 and row['provider_callbacks'] == 0, 'unexpected_native_radar_event')
    if row['cac_active']:
        require(row['ready'] == row['cac_valid_continuity'] == 1 and row['tx_admission'] == 0, 'cac_continuity_or_tx_violation')
    if row['quarantine_remaining_ms']:
        require(row['channel'] == 36, 'dfs_during_boot_quarantine')
    if row['channel'] == 52 and row['tx_admission']:
        require(row['ready'] == row['cac_done'] == 1 and row['nop_active'] == row['cac_active'] == row['quarantine_remaining_ms'] == 0, 'dfs_tx_without_current_cac')
    if previous:
        require(row['monotonic_ms'] > previous['monotonic_ms'], 'stale_kernel_clock')
        require(row['jobs_completed'] > previous['jobs_completed'], 'acquisition_stalled')
        if previous['cac_active'] and row['cac_active']:
            require(row['generation'] == previous['generation'], 'cac_generation_changed')
    return row

def timer(row, name, duration):
    start, end = row.get(name+'_started_ms'), row.get(name+'_deadline_ms')
    require(type(start) is int and type(end) is int and end-start >= duration and start > 0, name+'_timer_not_proven')
    return dict(started_ms=start, deadline_ms=end, duration_ms=end-start)

class Campaign:
    def __init__(self, host, record, client, clock=time.monotonic, sleeper=time.sleep):
        self.host=host;self.record=record;self.client=client;self.clock=clock;self.sleep=sleeper
        self.deadline=None;self.previous=None
        self.result=dict(schema='openmitrastar.f367-physical-campaign/v1',status='RUNNING',software_radar_origin='SOFTWARE_INJECTION',rf_silence_proven=False,calibrated_radar_detection_pass=False,release_pass=False,clients=[])
    def sample(self, label):
        require(self.clock() < self.deadline, 'host_campaign_horizon_expired')
        row=self.host.snapshot()
        self.record(label,row)  # Preserve a failed snapshot before raising.
        validate(row,self.previous)
        self.previous=row
        return row
    def wait(self, label, predicate, seconds, observer=None):
        deadline=min(self.deadline,self.clock()+seconds)
        while self.clock() < deadline:
            row=self.sample(label)
            if observer:observer(row)
            if predicate(row):return row
            self.sleep(5)
        raise CampaignError(label+'_deadline')
    def rejection(self, reason, deadline):
        answer=self.host.control('enter-dfs',expected_rejection=reason)
        self.record('expected-rejection',answer)
        self.sleep(1)
        row=self.sample('after-rejected-reentry')
        if reason=='nop-active':require(row['nop_deadline_ms']==deadline,'rejection_changed_nop_deadline')
        return row
    def cac(self, label):
        self.host.control('enter-dfs')
        seen=[]
        def observe(row):
            require(row['channel']==52 and row['filter_bw']==20,'dfs_target_not_52_20')
            if row['cac_active']:
                if not seen:seen.append((timer(row,'cac',70000),row['generation']))
                else:require(row['cac_deadline_ms']==seen[0][0]['deadline_ms'] and row['generation']==seen[0][1],'cac_deadline_or_generation_changed')
        row=self.wait(label,lambda r:r['cac_done']==r['ready']==r['tx_admission']==1 and r['cac_active']==0,115,observe)
        require(bool(seen),'cac_active_not_observed')
        require(row['monotonic_ms']>=seen[0][0]['deadline_ms'] and row['generation']==seen[0][1],'cac_ended_early_or_stale')
        return dict(timer=seen[0][0],generation=row['generation'],ready=row)
    def run(self, token):
        self.deadline=self.clock()+5400
        self.result['activation']=self.host.activate(token)
        first=self.sample('native-and-quarantine')
        require(first['channel']==36 and first['filter_bw']==80 and first['software_injections']==0,'bootstrap_not_r3_profile')
        self.result['quarantine_initial_ms']=first['quarantine_remaining_ms']
        self.wait('boot-quarantine',lambda r:r['quarantine_remaining_ms']==0,1860)
        self.result['first_cac']=self.cac('first-cac')
        require(self.deadline-self.clock()>=600,'insufficient_horizon_for_first_client')
        self.result['clients'].append(self.client('first',self.result['first_cac']['ready']))
        before=self.sample('before-software-radar')
        require(before['software_injections']==0 and before['nop_active']==0 and before['channel']==52,'software_injection_precondition')
        self.result['software_injection']=self.host.control('software-radar')
        row=self.wait('software-evacuation',lambda r:r['channel']==36 and r['nop_active']==1 and r['software_injections']==1,20)
        self.result['nop']=timer(row,'nop',1800000)
        require(row['tx_fault_latched']==0 and row['control_fault']==0,'evacuation_unconfirmed')
        self.rejection('nop-active',self.result['nop']['deadline_ms'])
        late=[]
        def nop_observe(current):
            require(current['channel']==36 and current['software_injections']==1,'unexpected_nop_state')
            if current['nop_active']:
                require(current['nop_deadline_ms']==self.result['nop']['deadline_ms'],'nop_deadline_changed')
                if 30000<=current['nop_remaining_ms']<=60000 and not late:
                    late.append(self.rejection('nop-active',self.result['nop']['deadline_ms']))
        row=self.wait('non-occupancy',lambda r:r['nop_active']==r['nop_remaining_ms']==0,1860,nop_observe)
        require(row['monotonic_ms']>=self.result['nop']['deadline_ms'] and late,'nop_expired_early_or_late_rejection_missing')
        self.result['second_cac']=self.cac('post-nop-cac')
        second=self.result['second_cac'];first=self.result['first_cac']
        require(second['timer']['started_ms']>=self.result['nop']['deadline_ms'] and second['generation']!=first['generation'],'new_cac_not_proven')
        require(self.deadline-self.clock()>=600,'insufficient_horizon_for_second_client')
        self.result['clients'].append(self.client('post-nop',second['ready']))
        self.result['final_snapshot']=self.sample('final-dfs-service')
        self.result['status']='PASS_F367_DFS_SOFTWARE_CONTROL_AND_CLIENT_TRAFFIC'
        return self.result
