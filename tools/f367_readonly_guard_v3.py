"""Typed guard evidence and one bounded retry for state/owner sampling only."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess,threading,time
import f367r4_phase_worker_v2 as previous
import f367_uart_capture_r2 as redaction
import f367_phase_gate_v2 as phases

core=previous.core
require=core.require
clients=core.clients
save=core.save
READ_ROLES=('snapshot','owner')

class GuardTimeout(core.Failure):
    def __init__(self,operation,contained,receipt):
        super().__init__('local_guard_timeout_'+operation)
        self.operation=operation;self.contained=contained;self.receipt=receipt

class Campaign(phases.Campaign):
    def __init__(self,host,*args,**kwargs):
        self.transport_host=host
        super().__init__(host,*args,**kwargs)
    def run(self,token):
        # Established before the inherited run computes its own horizon, so
        # transport can only stop earlier; it cannot extend that horizon.
        with self.transport_host.read_budget(self.clock()+5400):
            return super().run(token)
    def wait(self,label,predicate,seconds,observer=None):
        with self.transport_host.read_budget(min(self.deadline,self.clock()+seconds)):
            return super().wait(label,predicate,seconds,observer)

class Host(previous.Host):
    def __init__(self,plan,out):
        super().__init__(plan,out)
        self._observation_scope=threading.local()
    def _scope(self):
        if not hasattr(self,'_observation_scope'):
            self._observation_scope=threading.local()
        return self._observation_scope
    @contextmanager
    def operation(self,role):
        scope=self._scope();old=getattr(scope,'operation','control');scope.operation=role
        try:yield
        finally:scope.operation=old
    @contextmanager
    def read_budget(self,deadline):
        scope=self._scope();old=getattr(scope,'deadline',None)
        scope.deadline=min(old,deadline) if old is not None else deadline
        try:yield
        finally:scope.deadline=old
    def _budget(self):
        deadline=getattr(self._scope(),'deadline',None)
        if deadline is not None:require(time.monotonic()<deadline,'readonly_existing_deadline_expired')
    def _save_receipt(self,kind,row):
        folder=self.out/'host-observations';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+kind+'.json')
        with path.open('x',encoding='ascii') as stream:
            stream.write(json.dumps(row,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
        return str(path)
    def _guard(self,network):
        scope=self._scope();role=getattr(scope,'operation','control');attempt=getattr(scope,'attempt',1)
        start=time.monotonic();row=dict(schema='openmitrastar.f367-host-guard/v1',operation=role,attempt=attempt,
            network_check=bool(network),executable='powershell.exe',script='assert_f367_context.ps1',
            started_at_utc=datetime.now(timezone.utc).isoformat(),timeout_seconds=30,
            timed_out=False,source_hashes_verified=False,process_started=False,local_transport_contained=True)
        out=err=b'';process=None;error=None
        try:
            # Both attempts perform every original source and PowerShell check.
            for path,digest in self.plan['sources'].items():require(core.baseline.sha(path)==digest,'source_drift')
            row['source_hashes_verified']=True
            args=[core.desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(core.ROOT/'tools/assert_f367_context.ps1')]
            if network:args.append('-CheckNetwork')
            process=subprocess.Popen(args,env=core.desktop_ps.environment(),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.children.append(process);row.update(process_started=True,pid=process.pid)
            try:out,err=process.communicate(timeout=30)
            except subprocess.TimeoutExpired as timeout:
                row['timed_out']=True;out=timeout.output or b'';err=timeout.stderr or b''
                if process.poll() is None:
                    try:process.kill()
                    except OSError as failure:row['kill_error']=type(failure).__name__
                try:out,err=process.communicate(timeout=3)
                except subprocess.TimeoutExpired as failure:
                    out=failure.output or out;err=failure.stderr or err
                row['local_transport_contained']=process.poll() is not None
            row['exit_code']=process.returncode
        except Exception as failure:
            error=failure;row['exception_type']=type(failure).__name__
            if process is not None:row['local_transport_contained']=process.poll() is not None
        row.update(ended_at_utc=datetime.now(timezone.utc).isoformat(),duration_seconds=round(time.monotonic()-start,3))
        row['streams']={}
        for source,data in (('stdout',out),('stderr',err)):
            lines=[]
            for raw in data.splitlines(keepends=True)[:256]:
                item=redaction.redacted_event(raw)
                if item['kind'] in ('diagnostic','sensitive'):lines.append(item)
            row['streams'][source]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),lines=lines,raw_saved=False)
        row['failure_codes']=sorted(set(code.decode() for code in re.findall(rb'\bF(?:319|325|336|367)_[A-Z0-9_]{1,80}\b',err)))
        passed=error is None and not row['timed_out'] and row.get('exit_code')==0 and out.strip()==b'PASS_F367_CAMPAIGN_CONTEXT' and not err
        row['passed']=passed
        row['output_valid']=out.strip()==b'PASS_F367_CAMPAIGN_CONTEXT' and not err
        receipt=self._save_receipt('guard-'+role,row)
        if error:raise error
        if row['timed_out']:
            raise GuardTimeout(role,row['local_transport_contained'],receipt)
        require(row['local_transport_contained'],'guard_transport_containment_unproven')
        return passed
    def ssh(self,command,data=b'',timeout=20,allow_disconnect=False):
        if command=='/usr/sbin/om-f367-control status':
            role='snapshot'
        elif hasattr(self,'owner_token') and command=='/usr/sbin/om-watchdog-supervisor-f367 --status '+self.owner_token:
            role='owner'
        else:role='control'
        with self.operation(role):
            start=time.monotonic()
            try:
                result=super().ssh(command,data,timeout,allow_disconnect)
            except GuardTimeout:
                raise  # The guard receipt already identifies the origin.
            except core.Failure as error:
                if role in READ_ROLES and str(error) in ('ssh_deadline','ssh_containment_unproven','ssh_failed','ssh_output_limit'):
                    self._save_receipt('ssh-'+role,dict(schema='openmitrastar.f367-read-transport/v1',operation=role,
                        executable='ssh.exe',timeout_seconds=timeout,duration_seconds=round(time.monotonic()-start,3),
                        failure=str(error),exit_code=None,
                        local_transport_contained=False if str(error)=='ssh_containment_unproven' else None,
                        process_reference='not_exposed_by_inherited_ssh_transport',
                        argv_saved=False))
                raise
            return result
    def raw_control(self,action,token=None,expected_rejection=None):
        with self.operation('control'):
            return super().raw_control(action,token,expected_rejection)
    def _retry_read(self,name,reader):
        scope=self._scope();old_attempt=getattr(scope,'attempt',1)
        try:
            for attempt in (1,2):
                self._budget();scope.attempt=attempt
                try:
                    result=reader()
                    self._budget()
                    return result
                except GuardTimeout as error:
                    if error.operation not in READ_ROLES or not error.contained or attempt==2:
                        raise
                    self._budget()
                    self._save_receipt('readonly-retry',dict(schema='openmitrastar.f367-read-retry/v1',
                        operation=name,trigger_operation=error.operation,failed_attempt=1,next_attempt=2,
                        guard_receipt=error.receipt,partial_state_discarded=True,
                        all_guard_checks_repeated=True,deadlines_extended=False,mutation_retried=False))
        finally:scope.attempt=old_attempt
    def snapshot(self):
        scope=self._scope();base_snapshot=super().snapshot
        def pair():
            old=getattr(scope,'in_snapshot',False);scope.in_snapshot=True
            try:return base_snapshot()
            finally:scope.in_snapshot=old
        return self._retry_read('snapshot-and-owner',pair)
    def owner_status(self,initial=False):
        base_owner=super().owner_status
        if getattr(self._scope(),'in_snapshot',False):
            return base_owner(initial)
        return self._retry_read('owner',lambda:base_owner(initial))

    def campaign(self, token, uart, output):
            result={};self.stop_attempted=False
            def client(label, ready):
                return clients.run(self,self.plan,self.out/('client-'+label),ready)
            machine=Campaign(self,self.record,client)
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
