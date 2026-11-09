"""Continue verified ETH73 reset image already staged in Bootbase RAM.
No reboot/loady/transfer; fresh attach, current filesize/iminfo/CRC, one bootm.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,time
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-ethernet-reset-v2'
spec=importlib.util.spec_from_file_location('reset_trial',SOURCE/'executor.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def inherited(config):
    prior=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/eth73-reset-physical-v2'
    r=json.loads((prior/'result.json').read_text());t=json.loads((prior/'ymodem-control-events.json').read_text())
    m.m.require(r['bootm']==r['flash_writes']==r['bootenv_writes']==0 and
                r['artifact']['sha256']==config['sha256'] and t['outcome']=='completed','Prior exact RAM transfer not proven')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(t['finished_at_utc'])).total_seconds()
    m.m.require(0<=age<1800,'Loaded continuation too old')
    return str(prior)
class Flow(m.Flow):
    def wait(self,pattern,seconds):
        # Bootbase echoes may begin with topaz>command. A bare prefix is
        # not the final prompt. Drain the remaining reply until RX is quiet
        # for 150ms, then require the prompt at the end of that complete reply.
        deadline=self.clock()+seconds;data=bytearray();quiet_since=None
        while self.clock()<deadline:
            self.safe();chunk=self.s.read(size=4096,timeout=.05)
            if chunk:
                data+=chunk;quiet_since=None
                m.m.require(len(data)<=262144,'UART response exceeds bound')
                m.m.require(not re.search(m.m.FATAL,data),'Fatal UART marker')
            elif re.search(pattern,data):
                if quiet_since is None:quiet_since=self.clock()
                if self.clock()-quiet_since>=.15:return bytes(data)
        raise TimeoutError('Complete quiet UART prompt not received')
    def run(self):
        inherited(self.config);m.preflight(self.config);self.b.force_lease();self.fresh()
        marker='ETH73ATTACH-'+self.nonce[:20]
        attach=self.command('echo '+marker,m.m.PROMPT)
        m.m.require(re.search(rb'(?m)^'+marker.encode()+rb'\r?$',attach),'Bootbase fresh attach nonce absent')
        m.m.parse_environment(self.command('printenv bootcmd bootselect',m.m.PROMPT))
        # The previous timeout was after iminfo and before physical CRC receipt.
        self.verify_ram();m.preflight(self.config)
        m.m.require(int(m.m.parse_word(self.command('md.l e0000004 1',m.m.PROMPT),'e0000004'),16)&((1<<29)|(1<<30))==0,'Legacy map differs')
        m.m.require(m.m.parse_word(self.command('md.l f4000000 1',m.m.PROMPT),'f4000000')=='00000000','Watchdog differs')
        self.b.force_lease();self.fresh();self.boots+=1;self.s.write(b'bootm 83000000\r',timeout=3)
        boot=self.wait(m.PROMPT,120)
        m.m.require(b'Linux version '+m.KERNEL in boot and b'OPENMITRASTAR_ETH73_PID1_REACHED' in boot,'Fresh kernel/PID1 absent')
        nonce=self.command('echo '+self.nonce)
        m.m.require(re.findall(rb'(?m)^ETH73_NONCE=([^\r\n]+)\r?$',nonce)==[self.nonce.encode()],'Fresh kernel input absent')
        m.m.require(b'ETHLOAD=0' in self.command('ethload',seconds=45),'Driver load failed')
        m.m.require(b'qtn_topaz_emac_eth73 ' in self.command('modules'),'Module absent')
        diag=self.command('netdiag');(self.output/'network-address-before.txt').write_bytes(diag)
        for command in ['eth1up','eth1down','eth1up']:
            r=self.command(command,seconds=35)
            (self.output/(command+'-'+str(len(self.steps))+'.txt')).write_bytes(r)
            m.m.require((b'ETH1_UP=0' if command.endswith('up') else b'ETH1_DOWN=0') in r,'Second-port lifecycle failed')
        diag=self.command('netdiag');(self.output/'network-address-after.txt').write_bytes(diag)
        self.command('eth1state');stats=self.command('eth1stats');(self.output/'eth1stats.txt').write_bytes(stats)
        m.m.require(b'dma_unsafe=0' in stats,'DMA quarantine active')
        self.command('interrupts');net=self.command('netstats');(self.output/'netstats.txt').write_bytes(net)
        import subprocess
        ping=subprocess.run(['C:/Windows/System32/ping.exe','-n','4','-w','1000','192.168.1.91'],capture_output=True,timeout=10)
        (self.output/'ping.stdout').write_bytes(ping.stdout)
        replies=ping.stdout.count(b'TTL=64')
        return {'status':'PASS_RESET_IMAGE_BOOT_ETH1_LIFECYCLE_PING' if replies==4 else 'BOOT_LIFECYCLE_PASS_ETH1_TRAFFIC_PENDING',
                'bootm':self.boots,'reboots':0,'steps':self.steps,'ping_responses':replies,'ping_requests':4,
                'runtime':'RESET_V2_RAM_ETH1_UP_ETH0_DOWN','prior_transfer':inherited(self.config)}
def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--baseline-boot',default='')
    p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token')
    a=p.parse_args();config=json.loads(a.config.read_text());artifact=m.preflight(config);inherited(config)
    if not a.execute:print(json.dumps({'status':'PASS_CONTINUATION_PREFLIGHT','artifact':artifact}));return
    a.output.mkdir(exist_ok=False);log=m.Log(a.output/'uart-redacted.txt');session=flow=None
    result={'status':'STOP_LOADED_CONTINUATION','artifact':artifact,'reboots':0,'bootm':0,'flash_writes':0,'bootenv_writes':0}
    try:
        backend=m.Backend(a);backend.force_lease();session=m.m.continuous_session(log,backend)
        flow=Flow(backend,session,hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32],config=config,output=a.output)
        result.update(flow.run())
    except BaseException as error:
        result.update(error_type=type(error).__name__,error_reason=str(error),steps=flow.steps if flow else [],bootm=flow.boots if flow else 0)
        print('CONTINUATION_STOP '+str(error),flush=True);raise
    finally:
        if session:session.close()
        result.update(raw_uart_saved=False,finished_utc=datetime.now(timezone.utc).isoformat())
        (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
