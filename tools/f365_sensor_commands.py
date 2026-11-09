"""F365 reads cached access evidence immediately after each requested read."""
import re
import f363_sensor_commands as previous
import f365_thermal_status as cache
from f356_protocol import kv
from f336_wdt_ram_executor import require
node_path=previous.node_path
activated=previous.activated
def stage_pair(stage):
 require(re.fullmatch(r'/run/openmitrastar/f365-sensor/[0-9a-f]{32}',stage),'stage_path')
 return stage.replace('/f365-sensor/','/f363-sensor/')
def activation(node,stage):
 old=stage_pair(stage);return previous.activation(node,old).replace(old,stage)
def snapshot(path,stage,prefix):
 lines=[]
 for source in ('hwmon','legacy'):
  key=prefix+'_diag_'+source
  lines.append(f"cache_rc=0; cache_value=$(LC_ALL=C cat {path}/diag_{source} 2>{stage}/{key}.stderr) || cache_rc=$?\ncache_error=$(cat {stage}/{key}.stderr)\nprintf '{key}_rc=%s\\n{key}=%s\\n{key}_stderr=%s\\n' \"$cache_rc\" \"$cache_value\" \"$cache_error\"\n")
 return ''.join(lines)
def sample(node,stage):
 old=stage_pair(stage);path=node_path(node);text=previous.sample(node,old).replace(old,stage)
 text=text.replace("printf 'temp_rc=",snapshot(path,stage,'temp')+"printf 'temp_rc=",1)
 text=text.replace("printf 'interval_rc=",snapshot(path,stage,'interval')+"printf 'interval_rc=",1)
 return text
def split(raw):
 rows=kv(raw);diagnostic={};plain={}
 for key,value in rows.items():
  if re.fullmatch(r'(temp|interval)_diag_(hwmon|legacy)(_rc|_stderr)?',key):diagnostic[key]=value
  else:plain[key]=value
 return plain,diagnostic
def evidence(fields):
 result={}
 for prefix in ('temp','interval'):
  if prefix+'_diag_hwmon_rc' not in fields:continue
  result[prefix]={}
  for source in ('hwmon','legacy'):
   key=prefix+'_diag_'+source;require(fields.get(key+'_rc')=='0' and key in fields and not fields.get(key+'_stderr',''),'cached_read_failed')
   row=cache.cached(fields[key],source);result[prefix][source]=row
  own=result[prefix]['hwmon'];require(own['complete']==1 and own['operation']==('temp1_input' if prefix=='temp' else 'interval'),'stale_hwmon_cache')
 if 'temp' in result and 'interval' in result:require(result['interval']['hwmon']['sequence']==(result['temp']['hwmon']['sequence']+1)&((1<<64)-1),'hwmon_sequence_changed')
 return result
def sampled(raw):
 plain,fields=split(raw);observed=evidence(fields);require('temp' in observed,'cached_temp_evidence_missing')
 answer=previous.sampled(('\n'.join(k+'='+v for k,v in plain.items())+'\n').encode())
 require('interval' in observed and all(observed[p]['hwmon']['errno']==0 and observed[p]['hwmon']['read_count']>0 for p in ('temp','interval')),'successful_read_cache_error')
 return {**answer,'access_diagnostics':observed}
def diagnostic(raw):
 try:
  plain,fields=split(raw);result=previous.diagnostic(('\n'.join(k+'='+v for k,v in plain.items())+'\n').encode())
  result['access_diagnostics']={}
  for prefix in ('temp','interval'):
   if prefix+'_diag_hwmon_rc' not in fields:continue
   result['access_diagnostics'][prefix]={}
   for source in ('hwmon','legacy'):
    key=prefix+'_diag_'+source
    try:
     require(fields.get(key+'_rc')=='0' and key in fields and not fields.get(key+'_stderr',''),'cached_read_failed');result['access_diagnostics'][prefix][source]=cache.cached(fields[key],source)
    except Exception:
     result['access_diagnostics'][prefix][source]={'unavailable':True};result['cached_diagnostic_incomplete']=True
     if re.fullmatch('[0-9]{1,3}',fields.get(key+'_rc','')):result['access_diagnostics'][prefix][source]['read_exit_code']=int(fields[key+'_rc'])
     result['access_diagnostics'][prefix][source]['read_stderr']=previous.stderr_diagnostic(fields.get(key+'_stderr',''),'diag_'+source)
  return result
 except Exception:return {'unparsed_response':True,'bytes':len(raw)}
