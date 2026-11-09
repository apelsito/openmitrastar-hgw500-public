"""F367r3 host binding: same core/receipts, activation timeout240, UART captureR2."""
from pathlib import Path
import argparse,json,os
import f367_campaign_executor as core
import f367_uart_capture_r2 as capture
from f367_capture_r2_worker import claim_once
from f367_campaign_executor import require,subprocess,time,datetime,timezone,re,hashlib,evidence_redactor,baseline,Failure

IMAGE_SHA='a9d6283c383f65a0f02ea37c7624910b461e6e48adbf49c678b274af34b3f53c'
class Host(core.Host):
    def raw_control(self, action, token=None, expected_rejection=None):
            require(action in ('activate', 'enter-dfs', 'software-radar', 'stop'), 'control_action')
            if action == 'activate': require(token and re.fullmatch('[0-9a-f]{32}', token), 'activation_token')
            else: require(token is None, 'unexpected_control_token')
            require(self.network_guard(), 'control_network_guard')
            command='/usr/sbin/om-f367-control '+action+(' '+token if token else '')
            started=time.monotonic();started_utc=datetime.now(timezone.utc).isoformat()
            process=subprocess.Popen(self.ssh_argv(command),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.children.append(process)
            timed_out=False;kill_error=None;timeout=240 if action=='activate' else 30
            try:out,err=process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True
                try:process.kill()
                except OSError as error:kill_error=type(error).__name__
                try:out,err=process.communicate(timeout=3)
                except subprocess.TimeoutExpired as error:
                    out=error.output or b'';err=error.stderr or b''
            receipt=dict(schema='openmitrastar.f367-control-receipt/v1',action=action,started_at_utc=started_utc,
                         ended_at_utc=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.monotonic()-started,3),
                         exit_code=process.returncode,timed_out=timed_out,timeout_seconds=timeout,kill_error=kill_error,
                         local_transport_contained=process.poll() is not None,streams={})
            for source,data in (('stdout',out),('stderr',err)):
                lines=[]
                for raw in data.splitlines(keepends=True):
                    original_bytes=len(raw)
                    if token:raw=raw.replace(token.encode(),b'[token-redacted]')
                    raw=re.sub(rb'(?i)("?(?:token|nonce|secret)"?\s*[:=]\s*)("[^"]*"|[^\s,}]+)',rb'\1"[token-redacted]"',raw)
                    item=evidence_redactor.redacted_event(raw)
                    item['bytes']=original_bytes
                    if item['kind'] in ('diagnostic','sensitive'):lines.append(item)
                    if len(lines)>=512:break
                receipt['streams'][source]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),lines=lines,raw_saved=False)
            directory=self.out/'control';directory.mkdir(parents=True,exist_ok=True)
            path=directory/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+action+'.json')
            with path.open('x',encoding='ascii') as stream:
                stream.write(json.dumps(receipt,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
            receipt_ref=dict(receipt_path=str(path),receipt_sha256=baseline.sha(path))
            require(receipt['local_transport_contained'],'control_transport_containment')
            require(not timed_out,'control_timeout_'+action)
            require(len(out)<=262144 and len(err)<=65536,'control_output_limit')
            text=out.decode('ascii',errors='replace')
            if expected_rejection:
                require(process.returncode!=0 and 'OMF367_REJECT reason='+expected_rejection in text,'expected_rejection_missing')
                return dict(action=action,rejected=True,reason=expected_rejection,**receipt_ref)
            require(process.returncode==0,'control_failed_'+action)
            return dict(action=action,exit_code=0,stdout_bytes=len(out),stderr_bytes=len(err),**receipt_ref)

def load_plan(path,digest):
 plan=core.load_plan(path,digest)
 require(plan.get('runtime_revision')=='F367r3' and plan.get('activate_timeout_seconds')==240 and plan.get('uart_semantic_capture_revision')==2,'r2_host_scope')
 image=plan['images']['f367'];require(image['sha256']==IMAGE_SHA and image['bytes']==5459968 and image['full_slot_crc32']=='3def6860','r2_image_scope')
 require(plan.get('repeat_scope')=='one-f367r3-owned-lock-trial' and plan.get('max_completed_executions')==1,'r2_single_operation')
 for module in (core,capture):
  p=str(Path(module.__file__).resolve());require(plan['sources'].get(p)==baseline.sha(p),'r2_reused_source')
 require(plan['sources'].get(str(Path(__file__).resolve()))==baseline.sha(__file__),'r2_worker_binding')
 return plan

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--output-dir',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
 plan=load_plan(a.plan,a.plan_sha256)
 if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID_F367R3',hardware_actions=False)));return 0
 require(os.environ.get('OM_F367_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==core.EVIDENCE_ROOT.resolve(),'owning_launcher_required')
 claim_once(plan,a.plan_sha256)
 return core.run(plan,a.output_dir,host_factory=Host,uart_factory=capture.Uart)
if __name__=='__main__':raise SystemExit(main())
