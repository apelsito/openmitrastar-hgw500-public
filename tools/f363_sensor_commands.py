"""Fixed single-attempt sysfs operations for the F363 temperature campaign."""
import re
from f336_wdt_ram_executor import require
from f356_protocol import kv
def node_path(name):
 require(re.fullmatch(r'hwmon[0-9]{1,3}',name),'sensor_node_name');return '/sys/class/hwmon/'+name
def activation(node,stage):
 path=node_path(node);require(re.fullmatch(r'/run/openmitrastar/f363-sensor/[0-9a-f]{32}',stage),'stage_path')
 return f'''rc=0; printf '1\\n' >{path}/experimental_enable 2>{stage}/activation.stderr || rc=$?
printf 'activation_rc=%s\\n' "$rc"
printf 'enabled='; cat {path}/enabled
printf 'activation_attempted='; cat {path}/activation_attempted
printf 'activation_error='; cat {path}/activation_error
'''
def sample(node,stage):
 path=node_path(node);require(re.fullmatch(r'/run/openmitrastar/f363-sensor/[0-9a-f]{32}',stage),'stage_path')
 return f'''rc=0; value=$(LC_ALL=C cat {path}/temp1_input 2>{stage}/sample.stderr) || rc=$?
printf 'temp_rc=%s\\ntemp_mc=%s\\n' "$rc" "$value"
error=$(cat {stage}/sample.stderr)
printf 'temp_stderr=%s\\n' "$error"
[ "$rc" = 0 ] || exit 0
rc=0; value=$(LC_ALL=C cat {path}/interval 2>{stage}/interval.stderr) || rc=$?
printf 'interval_rc=%s\\ninterval_mc=%s\\n' "$rc" "$value"
error=$(cat {stage}/interval.stderr)
printf 'interval_stderr=%s\\n' "$error"
'''
def activated(raw):
 rows=kv(raw);require(rows==dict(activation_rc='0',enabled='1',activation_attempted='1',activation_error='0'),'sensor_activation_failed');return rows
def sampled(raw):
 rows=kv(raw);require(set(rows)=={'temp_rc','temp_mc','temp_stderr','interval_rc','interval_mc','interval_stderr'} and rows['temp_rc']=='0' and rows['interval_rc']=='0' and not rows['temp_stderr'] and not rows['interval_stderr'],'sensor_sample_failed')
 require(re.fullmatch(r'-?[0-9]{1,6}',rows['temp_mc']) and re.fullmatch(r'-?[0-9]{1,6} -?[0-9]{1,6}',rows['interval_mc']),'sensor_sample_format')
 temp=int(rows['temp_mc']);low,high=map(int,rows['interval_mc'].split());require(-40000<=temp<=125000 and temp%5000==0 and -40000<=high<=125000 and high%5000==0 and low==high-5000,'sensor_interval_outside_oem_curve')
 return dict(temp_upper_mc=temp,interval_lower_mc=low,interval_upper_mc=high,independent_reads=True,calibration_verified=False)
ERROR_NAMES={
 'Resource temporarily unavailable':'EAGAIN','Try again':'EAGAIN',
 'Connection timed out':'ETIMEDOUT',
 'Numerical result out of range':'ERANGE','Result too large':'ERANGE','Math result not representable':'ERANGE',
 'Invalid argument':'EINVAL','Input/output error':'EIO','No such device':'ENODEV',
 'No such file or directory':'ENOENT','Permission denied':'EACCES','Operation not permitted':'EPERM',
 'Bad address':'EFAULT','Interrupted system call':'EINTR','Device or resource busy':'EBUSY','Cannot allocate memory':'ENOMEM'}
def stderr_diagnostic(value,attribute):
 if not value:return dict(present=False)
 match=re.fullmatch(r'cat: (/sys/class/hwmon/hwmon[0-9]{1,3}/'+attribute+r'|read error): (.{1,128})',value)
 if not match or match[2] not in ERROR_NAMES:return dict(present=True,unrecognized_or_redacted=True,bytes=len(value.encode('ascii')))
 return dict(present=True,attribute=attribute,exact_stderr=value,message=match[2],errno_name_from_message=ERROR_NAMES[match[2]],errno_observed_directly=False)
def diagnostic(raw):
 try:
  rows=kv(raw);require(set(rows)<={'activation_rc','enabled','activation_attempted','activation_error','temp_rc','temp_mc','temp_stderr','interval_rc','interval_mc','interval_stderr'},'sensor_diagnostic_keys')
  result={}
  for key,value in rows.items():
   if key in ('temp_stderr','interval_stderr'):result[key]=stderr_diagnostic(value,'temp1_input' if key=='temp_stderr' else 'interval')
   else:require(len(value)<=32 and re.fullmatch(r'[-0-9 ]*',value),'sensor_diagnostic_value');result[key]=value
  return result
 except Exception:return {'unparsed_response':True,'bytes':len(raw)}
