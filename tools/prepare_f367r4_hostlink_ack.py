"""Normalize only the three radio-control acknowledgements at their producer."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f367-functional'
DST=ROOT/'work/kernel-port/f367r4-hostlink-ack'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('hostlink source anchor '+a[:80])
 return s.replace(a,b,1)
def main():
 if DST.exists():raise ValueError('immutable R4 source exists')
 DST.mkdir(parents=True)
 for sub in ('kernel','uapi','qdrv'):shutil.copytree(SRC/sub,DST/sub)
 p=DST/'qdrv/qdrv/qdrv_hostlink.c';s=p.read_text()
 s=once(s,'static int qdrv_send_ioctl_owned(struct qdrv_wlan *qw,', '''/* F367r4: this is a bitmask completion, not a POSIX zero-success return.
 * Keep legacy callers unchanged. Only channel/deferred-channel/XMIT opt in. */
static int qdrv_completed_ack_result(int raw)
{
 if(raw<0)return raw;
 if(!(raw&QTN_HLINK_RC_DONE)||(raw&QTN_HLINK_RC_ERR))return -EIO;
 return 0;
}

static int qdrv_send_ioctl_owned(struct qdrv_wlan *qw,''')
 s=once(s,'struct host_ioctl *ioctl, bool retain_published_timeout, bool *retained)','struct host_ioctl *ioctl, bool retain_published_timeout, bool *retained, bool normalized_ack)')
 s=once(s,'#ifdef MTEST\n\treturn 0;','#ifdef MTEST\n\treturn normalized_ack ? -EOPNOTSUPP : 0;')
 s=once(s,'static u32 omhlink_beacon_complete_trace;','static u32 omhlink_beacon_complete_trace;\n\tstatic u32 omf367_ack_trace;')
 s=once(s,'\t\trc = 1;\n\t\tqdrv_free_ioctl(ioctl);','\t\t/* A dead-MAC drop has no descriptor ACK; do not alias it with DONE=1. */\n\t\trc = normalized_ack ? -ENODEV : 1;\n\t\tif(normalized_ack)pr_err_ratelimited("OMF367_HLINK_ACK reason=mac-dead cmd=%u published=0 result=%d\\n",ioctl->ioctl_command,rc);\n\t\tqdrv_free_ioctl(ioctl);')
 s=once(s,'\trc = ioctl->ioctl_rc;','''\trc = ioctl->ioctl_rc;
 if(normalized_ack){
  int raw=rc;
  rc=qdrv_completed_ack_result(raw);
  if(rc||omf367_ack_trace<16){
   pr_info("OMF367_HLINK_ACK cmd=%u raw=%d done=%u err=%u result=%d\\n",ioctl->ioctl_command,raw,!!(raw&QTN_HLINK_RC_DONE),!!(raw&QTN_HLINK_RC_ERR),rc);
   omf367_ack_trace++;
  }
 }''')
 s=s.replace('qdrv_send_ioctl_owned(qw, ioctl, false, NULL);','qdrv_send_ioctl_owned(qw, ioctl, false, NULL, false);')
 s=s.replace('qdrv_send_ioctl_owned(qw, ioctl, true, retained);','qdrv_send_ioctl_owned(qw, ioctl, true, retained, false);')
 anchor='static int qdrv_send_ioctl(struct qdrv_wlan *qw, struct host_ioctl *ioctl)\n{\n\treturn qdrv_send_ioctl_owned(qw, ioctl, false, NULL, false);\n}'
 s=once(s,anchor,anchor+'''\n\nstatic int qdrv_send_ioctl_ack(struct qdrv_wlan *qw, struct host_ioctl *ioctl)
{
 return qdrv_send_ioctl_owned(qw,ioctl,false,NULL,true);
}''')
 from test_f355_lifetime import extract
 for name in ('qdrv_hostlink_setchan','qdrv_hostlink_setchan_deferred','qdrv_hostlink_xmitctl'):
  body=extract(s,name);replacement=once(body,'return qdrv_send_ioctl(qw, ioctl);','return qdrv_send_ioctl_ack(qw, ioctl);');s=once(s,body,replacement)
 p.write_bytes(s.encode())
 pins={p.relative_to(DST).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (DST/sub).rglob('*') if p.is_file()}
 previous={p.relative_to(SRC).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (SRC/sub).rglob('*') if p.is_file()}
 changed=[n for n in pins if pins[n]!=previous[n]]
 if changed!=['qdrv/qdrv/qdrv_hostlink.c']:raise ValueError('unexpected R4 source delta')
 report={'schema':'openmitrastar.f367r4-hostlink-ack-source/v1','status':'PREPARED_FOR_PRODUCER_CONSUMER_TEST','source_pins':pins,'baseline_source':str(SRC),'baseline_pins':previous,'changed_files':changed,'normalized_commands':['IOCTL_DEV_CHANGE_CHANNEL','IOCTL_DEV_CHANGE_CHAN_DEFERRED','IOCTL_DEV_XMITCTL'],'raw_legacy_return_preserved':True,'mac_dead_is_distinct_negative_failure':True,'done_without_err_maps_to_zero':True,'timeout_waits_and_wire_masks_unchanged':True,'hardware_actions':False,'physical_prerequisite':json.loads((SRC/'source-manifest.json').read_text())['physical_prerequisite']}
 (DST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source':str(DST),'hostlink_sha256':sha(p),'changed_files':changed}))
if __name__=='__main__':main()
