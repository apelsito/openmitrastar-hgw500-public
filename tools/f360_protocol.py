"""First configuration SAVE validation. No payload is emitted in diagnostics."""
import json,re
import f356_protocol as base
ProtocolError,require,unique,kv,FATAL=base.ProtocolError,base.require,base.unique,base.kv,base.FATAL
# Only the descriptive phase name changes; validate the established wire fields
# through the same owner/sequence/FD/deadline checks, then retain the real name.
PHASE='spi-config-first-save'
def phase_view(row):
 require(row.get('phase') in ('',PHASE),'save_owner_phase');copy=dict(row)
 if copy['phase']==PHASE:copy['phase']=base.PHASE
 return copy
def owner(row,*args,**kwargs):
 checked=base.owner(phase_view(row),*args,**kwargs);checked['phase']=row['phase'];return checked
idle=base.idle
def armed(row,op):return base.armed(phase_view(row),op)
def ceased(row):return base.ceased(phase_view(row))
def loaded(raw,boot):
 rows=kv(raw);require(set(rows)=={'load_rc','loader_report','loader_stderr_present','allow_hw','allow_program','module_present','node_present','boot_id'},'provider_load_fields')
 require(rows['load_rc']=='0' and rows['loader_report']=='ok' and rows['loader_stderr_present']=='0' and rows['allow_hw']=='Y' and rows['allow_program']=='Y' and rows['module_present']=='1' and rows['node_present']=='1' and rows['boot_id']==boot,'provider_program_gate')
 return dict(loaded=True,allow_hw=True,allow_program=True,boot_id=boot)
def saved(raw,payload):
 require(len(raw)<=1024,'save_response_size');row=json.loads(raw,object_pairs_hook=unique)
 require(type(row) is dict and set(row)=={'status','sequence','slot','bytes'} and row['status']=='saved','save_response_fields')
 require(type(row['sequence']) is int and row['sequence']==1 and type(row['slot']) is int and row['slot']==0 and type(row['bytes']) is int and row['bytes']==payload['bytes'],'first_save_contract')
 return dict(row,commit_protection_witnesses_verified_by_pinned_cli=True)
def loaded_payload(raw,payload):
 row=kv(raw);require(row=={'readback_rc':'0','stderr_present':'0','bytes':str(payload['bytes']),'sha256':payload['sha256']},'load_payload_mismatch');return dict(bytes=payload['bytes'],sha256=payload['sha256'],verified=True)
unloaded=base.unloaded
def diagnostic(kind,out,err,code,timeout):
 result=dict(operation=kind,exit_code=code,timeout=bool(timeout),stdout_bytes=len(out),stderr_bytes=len(err),raw_saved=False)
 if kind=='module-load':return base.diagnostic('load',out,err,code,timeout)
 try:
  if kind=='save':
   row=json.loads(out,object_pairs_hook=unique)
   if type(row) is dict and set(row)=={'status','sequence','slot','bytes'} and row['status']=='saved' and all(type(row[k]) is int and 0<=row[k]<(1<<64) for k in ('sequence','slot','bytes')):result['metadata']=row
  elif kind in ('load-readback','unload'):
   row=kv(out);fields={}
   for key,value in row.items():
    if key in ('readback_rc','stderr_present','bytes','unload_rc','module_present','node_present') and re.fullmatch('[0-9]{1,6}',value):fields[key]=value
    elif key=='sha256' and re.fullmatch('[0-9a-f]{64}',value):fields[key]=value
   result['fields']=fields
 except (ValueError,UnicodeError,TypeError):result['partial_or_invalid']=True
 known={b'journal device identity rejected',b'journal ioctl failed',b'journal response rejected',b'journal close failed',b'output write failed',b'journal empty'}
 result['known_errors']=[line.decode('ascii') for line in err.splitlines() if line in known];return result
