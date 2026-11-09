"""Same F367r4 firmware/host transport; only phase-aware validation differs."""
from pathlib import Path
import argparse,json,os
import f367r4_campaign_worker as previous
import f367_phase_gate_v2 as phases
from f367_campaign_executor import clients,threading,time,save,require
core=previous.core
capture=previous.capture
baseline=previous.baseline
claim_once=previous.claim_once
class Host(previous.Host):
    def campaign(self, token, uart, output):
            result={};self.stop_attempted=False
            def client(label, ready):
                return clients.run(self,self.plan,self.out/('client-'+label),ready)
            machine=phases.Campaign(self,self.record,client)
            uart.invalidate_prompt();uart.stop_autoboot(120)
            intercept_stop=threading.Event()
            def retain_interceptor():
                while not intercept_stop.wait(30):
                    # Extend observation admission only, never any kernel/WDT timer.
                    # Keep the original byte floor and duplicate suppression intact.
                    uart.auto_until=time.monotonic()+120
                    uart.autoboot=True
            interceptor=threading.Thread(target=retain_interceptor,name='F367-UART-admission',daemon=True)
            self.threads.append(interceptor);interceptor.start()
            self.campaign_partial=machine.result
            try:
                result=machine.run(token)
                return result
            finally:
                # Save partial state before requesting any stop/reset.
                save(self.out/'campaign-before-stop.json',machine.result)
                intercept_stop.set();interceptor.join(timeout=2)
                require(not interceptor.is_alive(),'interceptor_not_contained')
                self.stop_attempted=True
                try:
                    uart.stop_autoboot(120)
                    self.stop_result=self.control('stop')
                    save(self.out/'stop.json',self.stop_result)
                except Exception as error:
                    self.stop_result=dict(confirmed=False,error=type(error).__name__)
                    save(self.out/'stop.json',self.stop_result)

def load_plan(path,digest):
 plan=previous.load_plan(path,digest)
 require(plan.get('host_phase_gate_revision')==2,'phase_gate_revision')
 for module in (previous,phases):
  source=str(Path(module.__file__).resolve());require(plan['sources'].get(source)==baseline.sha(source),'phase_gate_source')
 require(plan['sources'].get(str(Path(__file__).resolve()))==baseline.sha(__file__),'phase_worker_source')
 return plan

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True);p.add_argument('--output-dir',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
 plan=load_plan(a.plan,a.plan_sha256)
 if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID_F367R4_PHASE_GATE_V2',hardware_actions=False)));return 0
 require(os.environ.get('OM_F367_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==core.EVIDENCE_ROOT.resolve(),'owning_launcher_required')
 claim_once(plan,a.plan_sha256)
 return core.run(plan,a.output_dir,host_factory=Host,uart_factory=capture.Uart)
if __name__=='__main__':raise SystemExit(main())
