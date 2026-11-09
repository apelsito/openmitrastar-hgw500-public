"""Phase-scoped host validation over the unchanged F367 campaign and timers."""
import f367_campaign as original

require=original.require

def validate(row, previous=None, dfs_entered=False):
    require(row.get('schema')=='openmitrastar.f367-state/v1','status_schema')
    require(all(type(row.get(key)) is int and row[key]>=0 for key in original.COMMON),'status_numbers')
    require(row['provider_present']==row['started']==row['hardware_ready']==1,'native_acquisition_unavailable')
    require(row['configured']==row['region_eu']==row['region_es']==1,'regulatory_context_changed')
    require(row['errors']==row['tx_fault_latched']==row['control_fault']==0,'runtime_fault')
    require(row['native_callbacks']==row['provider_callbacks']==0,'unexpected_native_radar_event')
    initial=(not dfs_entered and row['channel']==36 and row['filter_bw']==80 and
             row['cac_active']==row['cac_done']==row['cac_remaining_ms']==
             row['nop_active']==row['nop_remaining_ms']==row['software_injections']==0)
    if not dfs_entered:
        require(initial,'unexpected_pre_dfs_context')
        require(row['doth'] in (0,1) and row['tpc'] in (0,1),'invalid_initial_feature_flags')
    else:
        require(row['doth']==row['tpc']==1,'dfs_feature_flags_lost')
    if row['cac_active']:
        require(dfs_entered and row['ready']==row['cac_valid_continuity']==1 and row['generation']>0 and row['tx_admission']==0,'cac_continuity_or_tx_violation')
    if row['quarantine_remaining_ms']:
        require(row['channel']==36,'dfs_during_boot_quarantine')
    if row['channel']==52 and row['tx_admission']:
        require(dfs_entered and row['ready']==row['cac_done']==1 and row['generation']>0 and row['nop_active']==row['cac_active']==row['quarantine_remaining_ms']==0,'dfs_tx_without_current_cac')
    if previous:
        require(row['monotonic_ms']>previous['monotonic_ms'],'stale_kernel_clock')
        require(row['jobs_completed']>previous['jobs_completed'],'acquisition_stalled')
        if previous['cac_active'] and row['cac_active']:
            require(row['generation']==previous['generation'],'cac_generation_changed')
    return row

class ControlObserver:
    def __init__(self,host,campaign):
        self.host=host;self.campaign=campaign
    def __getattr__(self,name):
        return getattr(self.host,name)
    def control(self,action,expected_rejection=None):
        result=self.host.control(action,expected_rejection=expected_rejection)
        if action=='enter-dfs' and expected_rejection is None:
            require(result.get('action')=='enter-dfs' and result.get('exit_code')==0,'dfs_entry_not_confirmed')
            self.campaign.dfs_entered=True
            self.campaign.result['confirmed_dfs_entries']+=1
        return result

class Campaign(original.Campaign):
    def __init__(self,host,record,client,*args,**kwargs):
        self.dfs_entered=False
        super().__init__(ControlObserver(host,self),record,client,*args,**kwargs)
        self.result['host_phase_gate_revision']=2
        self.result['confirmed_dfs_entries']=0
    def sample(self,label):
        require(self.clock()<self.deadline,'host_campaign_horizon_expired')
        row=self.host.snapshot()
        self.record(label,row)
        validate(row,self.previous,self.dfs_entered)
        self.previous=row
        return row
