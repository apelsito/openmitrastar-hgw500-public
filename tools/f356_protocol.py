"""F356 pure validators; no hardware or filesystem access."""
import hashlib,json,re
PHASE='spi-identify-observe'
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
def unique(pairs):
    result={}
    for key,value in pairs:require(key not in result,'duplicate_json_key');result[key]=value
    return result
def kv(raw):
    require(len(raw)<=8192,'field_output_size');rows={}
    for line in raw.decode('ascii').splitlines():
        require('=' in line,'field_output_line');key,value=line.split('=',1);require(key not in rows,'duplicate_field');rows[key]=value
    return rows
def loaded(raw,boot):
    row=kv(raw);require(set(row)=={'load_rc','loader_report','loader_stderr_present','allow_hw','allow_program','module_present','node_present','boot_id'},'provider_load_fields')
    require(row['load_rc']=='0' and row['loader_report']=='ok' and row['loader_stderr_present']=='0','provider_load_failed')
    require(row['allow_hw']=='Y' and row['allow_program']=='N' and row['module_present']=='1' and row['node_present']=='1' and row['boot_id']==boot,'provider_gate_or_identity')
    return dict(loaded=True,allow_hw=True,allow_program=False,boot_id=boot)
def observed(raw,expected_control):
    require(len(raw)<=1024,'observe_output_size');row=json.loads(raw,object_pairs_hook=unique)
    require(type(row) is dict and set(row)=={'status','id','control','status_register','security_register','common_bp0','exact_part_verified'},'observe_fields')
    require(row['status']=='observed' and row['exact_part_verified'] is False,'observe_status')
    require(type(row['id']) is str and re.fullmatch('[0-9a-f]{6}',row['id']) is not None and row['id']=='c22018','unsupported_observed_id')
    require(type(row['control']) is str and re.fullmatch('[0-9a-f]{8}',row['control']) is not None and int(row['control'],16)==expected_control,'observe_control_changed')
    require(integer(row['status_register'],255) and integer(row['security_register'],255) and integer(row['common_bp0'],1),'observe_numeric_fields')
    require(not row['status_register']&1,'observe_wip')
    expected=not row['status_register']&0x3f and not row['security_register']&0x9c
    require(row['common_bp0']==int(expected),'observe_protection_consistency')
    # The pinned F351 CLI emits this JSON only after checking all response
    # statuses and claimed/quarantined==0, then closing its misc-device FD.
    return dict(row,release_verified_by_pinned_cli=True,claimed=False,quarantined=False,part_family='UNKNOWN_35F_OR_36E')
def unloaded(raw):
    row=kv(raw);require(row=={'unload_rc':'0','module_present':'0','node_present':'0'},'provider_unload_unverified');return dict(module_absent=True,node_absent=True)
MARKER=re.compile(rb'OMF356 observe rc=(-?[0-9]{1,11}) id=([0-9a-f]{6}) control=([0-9a-f]{8}) status=([0-9a-f]{2}) security=([0-9a-f]{2}) valid=([0-9a-f]{2}) claimed=([01]) quarantined=([01])(?![0-9A-Za-z])')
def marker_diagnostic(raw):
    rows=[];matches=list(MARKER.finditer(raw))
    for match in matches[:4]:
        rc=int(match[1]);valid=int(match[6],16)
        if not -(1<<31)<=rc<(1<<31) or valid&~15:continue
        rows.append(dict(rc=rc,id=match[2].decode(),control=match[3].decode(),status_register=int(match[4],16),security_register=int(match[5],16),valid_mask=valid,claimed=bool(int(match[7])),quarantined=bool(int(match[8])),read_validity=dict(id=bool(valid&1),control=bool(valid&2),status=bool(valid&4),security=bool(valid&8))))
    return dict(marker_count=raw.count(b'OMF356 observe '),parsed_count=len(matches),markers=rows,fatal_seen=FATAL.search(raw) is not None,raw_saved=False)
def marker_verified(raw,observation):
    data=marker_diagnostic(raw);require(not data['fatal_seen'],'fatal_in_observe_uart')
    require(data['marker_count']==1 and data['parsed_count']==1 and len(data['markers'])==1,'observe_marker_cardinality')
    row=data['markers'][0];require(row['rc']==0 and row['valid_mask']==15 and row['claimed'] is False and row['quarantined'] is False,'observe_marker_not_released')
    require(all(row[k]==observation[k] for k in ('id','control','status_register','security_register')),'observe_marker_cli_mismatch');return row
def diagnostic(kind,out,err,code,timed_out):
    result=dict(operation=kind,exit_code=code,timeout=bool(timed_out),stdout_bytes=len(out),stderr_bytes=len(err),raw_saved=False)
    if kind in ('load','unload'):
        allowed={'load_rc','unload_rc','loader_report','loader_stderr_present','allow_hw','allow_program','module_present','node_present','boot_id'};fields={}
        for line in out[:8192].splitlines():
            if b'=' not in line:continue
            key,value=line.split(b'=',1)
            try:key=key.decode('ascii');value=value.decode('ascii')
            except UnicodeError:continue
            if key not in allowed:continue
            if re.fullmatch(r'[0-9]{1,3}|Y|N|ok|other|load_fail|open_fail|usage|[0-9a-f-]{36}',value):fields[key]=value
        result['fields']=fields
    elif kind=='observe':
        try:result['observation']=observed(out,4)
        except (ValueError,UnicodeError,TypeError):result['complete_valid_observation']=False
    errors={b'journal device identity rejected',b'journal ioctl failed',b'journal response rejected',b'journal close failed',b'output write failed'}
    result['known_errors']=[line.decode('ascii') for line in err.splitlines() if line in errors]
    return result
