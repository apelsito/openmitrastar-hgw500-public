"""F363 sensor owner validators reused from F356; no hardware or filesystem access."""
import hashlib,json,re
PHASE='temperature-activation'
FATAL=re.compile(rb'Kernel panic|Oops:|\bBUG:|Machine Check|machine check|Misaligned Access|Fatal exception|Unable to handle kernel|Data abort|Bus error|EV_(?:TLB|ProtV)|MuC has halted',re.I)
class ProtocolError(ValueError):pass
def require(ok,reason):
    if not ok:raise ProtocolError(reason)
def integer(value,maximum=(1<<64)-1):return type(value) is int and 0<=value<=maximum
def owner(row,token,boot_id,launched_pid,previous=None):
    require(type(row) is dict and row.get('schema')=='openmitrastar.f340-supervisor-state/v1','owner_schema')
    require(row.get('peer_verified') is True and row.get('nonce')==token and row.get('boot_id')==boot_id,'owner_not_live_bound')
    require(integer(row.get('owner_pid'),(1<<31)-1) and row['owner_pid']==launched_pid and row['owner_pid']>1,'owner_pid')
    require(integer(row.get('owner_start_ticks')) and row['owner_start_ticks']>0,'owner_start')
    require(row.get('phase') in ('',PHASE) and row.get('state') in ('idle','waiting-phase','phase-active','ceased-fd-held'),'owner_phase_or_state')
    for key in ('op','ack_sequence','phase_sequence','pet_count','timeout_reported_seconds','last_pet_monotonic_ms','phase_deadline_monotonic_ms','session_deadline_monotonic_ms'):
        require(integer(row.get(key)),key)
    for key in ('error','fd_held','hardware_arm_confirmed','first_pet_confirmed'):require(type(row.get(key)) is bool,key)
    if previous is not None:require(row['owner_start_ticks']==previous['owner_start_ticks'] and row['owner_pid']==previous['owner_pid'],'owner_changed')
    safe={key:row[key] for key in ('state','error','op','ack_sequence','phase_sequence','phase','boot_id','owner_pid','owner_start_ticks','fd_held','hardware_arm_confirmed','first_pet_confirmed','pet_count','timeout_reported_seconds','last_pet_monotonic_ms','phase_deadline_monotonic_ms','session_deadline_monotonic_ms')}
    safe['nonce_sha256']=hashlib.sha256(token.encode('ascii')).hexdigest();safe['peer_verified']=True;return safe
def idle(row):
    require(row['op']==1 and row['ack_sequence']==0 and row['phase_sequence']==0 and row['phase']=='' and row['state']=='idle' and row['error'] is False,'idle_contract')
    require(row['fd_held'] is False and row['hardware_arm_confirmed'] is False and row['first_pet_confirmed'] is False and row['pet_count']==0,'idle_opened_watchdog')
def armed(row,op):
    require(row['op']==op and row['ack_sequence']==1 and row['error'] is False,'arm_or_begin_ack')
    require(row['fd_held'] is True and row['hardware_arm_confirmed'] is True and row['first_pet_confirmed'] is True and row['pet_count']>=1 and row['timeout_reported_seconds']==8,'guardian_not_armed')
    require(row['last_pet_monotonic_ms']<row['phase_deadline_monotonic_ms']<=row['session_deadline_monotonic_ms'],'guardian_deadline')
    if op==2:require(row['state']=='waiting-phase' and row['phase_sequence']==0 and row['phase']=='','arm_phase')
    else:require(op==3 and row['state']=='phase-active' and row['phase_sequence']==1 and row['phase']==PHASE,'begin_phase')
def ceased(row):
    require(row['op']==6 and row['ack_sequence']==1 and row['phase_sequence']==1 and row['phase']==PHASE and row['error'] is False,'cease_ack')
    require(row['state']=='ceased-fd-held' and row['fd_held'] is True and row['hardware_arm_confirmed'] is True,'cease_closed_or_disarmed')
