"""Pure F349 validators. No IO, addresses chosen by callers, or hardware API."""
import hashlib,re

PHASE='spi-control-read'
PARAMETERS=('execute_read','controller_resource_claimed','controller_mapped','legacy_map_verified','map_register_value','map_read_count','controller_value','controller_read_count','controller_write_count','transaction_provider_ready')
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
    for key in ('error','fd_held','hardware_arm_confirmed','first_pet_confirmed'):
        require(type(row.get(key)) is bool,key)
    if previous is not None:
        require(row['owner_start_ticks']==previous['owner_start_ticks'] and row['owner_pid']==previous['owner_pid'],'owner_changed')
    safe={key:row[key] for key in ('state','error','op','ack_sequence','phase_sequence','phase','boot_id','owner_pid','owner_start_ticks','fd_held','hardware_arm_confirmed','first_pet_confirmed','pet_count','timeout_reported_seconds','last_pet_monotonic_ms','phase_deadline_monotonic_ms','session_deadline_monotonic_ms')}
    safe['nonce_sha256']=hashlib.sha256(token.encode('ascii')).hexdigest();safe['peer_verified']=True
    return safe
def idle(row):
    require(row['op']==1 and row['ack_sequence']==0 and row['phase_sequence']==0 and row['phase']=='' and row['state']=='idle' and row['error'] is False,'idle_contract')
    require(row['fd_held'] is False and row['hardware_arm_confirmed'] is False and row['pet_count']==0,'idle_opened_watchdog')
def armed(row,op):
    require(row['op']==op and row['ack_sequence']==1 and row['error'] is False,'arm_or_begin_ack')
    require(row['fd_held'] is True and row['hardware_arm_confirmed'] is True and row['first_pet_confirmed'] is True and row['pet_count']>=1 and row['timeout_reported_seconds']==8,'guardian_not_armed')
    require(row['last_pet_monotonic_ms']<row['phase_deadline_monotonic_ms']<=row['session_deadline_monotonic_ms'],'guardian_deadline')
    if op==2:require(row['state']=='waiting-phase' and row['phase_sequence']==0 and row['phase']=='','arm_phase')
    else:require(op==3 and row['state']=='phase-active' and row['phase_sequence']==1 and row['phase']==PHASE,'begin_phase')
def ceased(row):
    require(row['op']==6 and row['ack_sequence']==1 and row['phase_sequence']==1 and row['phase']==PHASE and row['error'] is False,'cease_ack')
    require(row['state']=='ceased-fd-held' and row['fd_held'] is True and row['hardware_arm_confirmed'] is True,'cease_closed_or_disarmed')
def probe(text,boot_id):
    rows={}
    for line in text.decode('ascii').splitlines():
        require('=' in line,'probe_output_line');key,value=line.split('=',1);require(key not in rows,'duplicate_probe_field');rows[key]=value
    require(set(rows)==set(PARAMETERS)|{'load_rc','snapshot_rc','unload_rc','module_present','boot_id','complete'},'probe_fields')
    require(rows['load_rc']=='0' and rows['snapshot_rc']=='0' and rows['unload_rc']=='0' and rows['module_present']=='0' and rows['complete']=='1' and rows['boot_id']==boot_id,'probe_or_unload_failed')
    for key in ('execute_read','controller_resource_claimed','controller_mapped','legacy_map_verified'):require(rows[key]=='Y',key)
    require(rows['transaction_provider_ready']=='N','unexpected_transaction_provider')
    numbers={}
    for key in ('map_register_value','map_read_count','controller_value','controller_read_count','controller_write_count'):
        require(re.fullmatch(r'[0-9]{1,10}',rows[key]) is not None,key);numbers[key]=int(rows[key]);require(numbers[key]<=0xffffffff,key)
    require(numbers['map_read_count']==1 and numbers['controller_read_count']==1 and numbers['controller_write_count']==0,'unexpected_mmio_counts')
    require(numbers['map_register_value']&0x60000000==0,'map_not_legacy')
    return dict(map_value=f"{numbers['map_register_value']:08x}",control_value=f"{numbers['controller_value']:08x}",map_reads=1,control_reads=1,spi_writes=0,transaction_provider_ready=False,module_unloaded=True,boot_id=boot_id,value_interpretation='raw_uninterpreted_control_word')
def uart(raw,observation):
    require(FATAL.search(raw) is None,'fault_in_probe_uart')
    value=rb'(0x[0-9a-fA-F]{1,8}|0)(?![0-9A-Za-z])'
    map_begin=re.findall(rb'OMSPICTRL map-read-begin address=0xe0000004',raw)
    control_begin=re.findall(rb'OMSPICTRL control-read-begin address=0xe2000004 map='+value,raw)
    done=re.findall(rb'OMSPICTRL control-read-done value='+value+rb' map_reads=1 reads=1 writes=0 provider=0',raw)
    released=re.findall(rb'OMSPICTRL released map_reads=1 reads=1 writes=0 provider=0',raw)
    require(len(map_begin)==len(control_begin)==len(done)==len(released)==1,'probe_uart_sequence_counts')
    require(len(re.findall(rb'OMSPICTRL ',raw))==4,'extra_probe_uart_event')
    require(int(control_begin[0],0)==int(observation['map_value'],16) and int(done[0],0)==int(observation['control_value'],16),'uart_sysfs_mismatch')
    require(raw.index(map_begin[0])<raw.index(b'OMSPICTRL control-read-begin')<raw.index(b'OMSPICTRL control-read-done')<raw.index(released[0]),'probe_uart_order')
    lines=[map_begin[0],re.search(rb'OMSPICTRL control-read-begin address=0xe2000004 map='+value,raw).group(0),
           re.search(rb'OMSPICTRL control-read-done value='+value+rb' map_reads=1 reads=1 writes=0 provider=0',raw).group(0),released[0]]
    return dict(map_begin=1,control_begin=1,control_done=1,released=1,fatal_markers=0,validated_lines=[line.decode('ascii') for line in lines])
