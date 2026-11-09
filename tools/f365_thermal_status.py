"""F365 cached access diagnostics; reading these fields does not sample DATA."""
import json,re
import f363_thermal_status as previous
from f336_wdt_ram_executor import require
SCHEMA='openmitrastar.f365-temperature-access/v1'
def unique(pairs):
 out={}
 for key,value in pairs:require(key not in out,'duplicate_diag_key');out[key]=value
 return out
def cached(value,source):
 require(isinstance(value,str) and len(value)<=2048,'diagnostic_size')
 row=json.loads(value,object_pairs_hook=unique);require(type(row) is dict and set(row)=={'schema','source','operation','sequence','complete','errno','read_count','first_word','last_word','elapsed_us','elapsed_valid'},'diagnostic_fields')
 require(row['schema']==SCHEMA and row['source']==source and source in ('hwmon','legacy'),'diagnostic_revision_source')
 require(row['operation'] in (('none','temp1_input','interval') if source=='hwmon' else ('none','legacy')),'diagnostic_operation')
 for key,maximum in [('sequence',(1<<64)-1),('elapsed_us',(1<<64)-1),('read_count',(1<<32)-1),('complete',1),('elapsed_valid',1)]:require(type(row[key]) is int and 0<=row[key]<=maximum,'diagnostic_integer')
 require(type(row['errno']) is int and -4095<=row['errno']<=0,'diagnostic_errno')
 if row['read_count']:
  require(all(type(row[k]) is str and re.fullmatch('0x[0-9a-f]{8}',row[k]) for k in ('first_word','last_word')),'diagnostic_words')
 else:require(row['first_word'] is None and row['last_word'] is None,'diagnostic_zero_reads')
 if not row['complete']:require(row['operation']=='none' and row['sequence']==0 and row['read_count']==0 and row['errno']==0 and row['elapsed_us']==0 and row['elapsed_valid']==0,'diagnostic_empty_state')
 else:require(row['operation']!='none','diagnostic_complete_operation')
 if not row['elapsed_valid']:require(row['elapsed_us']==0,'diagnostic_invalid_elapsed')
 return row
def command():
 return previous.command()+r'''for d in /sys/class/hwmon/hwmon*; do
 [ -r "$d/name" ] || continue
 [ "$(cat "$d/name")" = topaz_internal ] || continue
 printf 'diag_hwmon='; cat "$d/diag_hwmon"
 printf 'diag_legacy='; cat "$d/diag_legacy"
done
'''
def validate(data):
 rows={};plain=[]
 for line in data.decode('ascii').splitlines():
  if line.startswith(('diag_hwmon=','diag_legacy=')):
   key,value=line.split('=',1);require(key not in rows,'duplicate_diag_source');rows[key]=value
  else:plain.append(line)
 result=previous.validate(('\n'.join(plain)+'\n').encode());require(set(rows)=={'diag_hwmon','diag_legacy'},'diagnostic_attrs_missing')
 result['diagnostic_revision']=365
 for source in ('hwmon','legacy'):
  row=cached(rows['diag_'+source],source)
  # Existing callers may have observed ENODEV while disabled. Neither cache
  # is required to be virgin, and those calls must have performed zero reads.
  require(row['read_count']==0 and (not row['complete'] or row['errno']==-19),'inactive_diagnostic_read_sensor')
  result['diag_'+source]=row
 return result
