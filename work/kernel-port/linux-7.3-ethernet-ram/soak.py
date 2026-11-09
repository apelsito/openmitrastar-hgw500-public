"""Bounded traffic/lifecycle campaign on the already-running ETH73 RAM kernel.
No loady, bootm, reboot, module replacement, flash or bootenv operation.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,math,re,socket,statistics,sys,time
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('eth73_executor',HERE/'executor.py')
e=importlib.util.module_from_spec(s);s.loader.exec_module(e)

def parse_net(output):
    result={}
    for line in output.splitlines():
        hit=re.fullmatch(rb'\s*(eth[01]):\s+([0-9 ]+)\s*',line)
        if not hit:continue
        vals=[int(v) for v in hit[2].split()]
        if len(vals)!=16:raise ValueError('Network row does not have 16 counters')
        name=hit[1].decode()
        if name in result:raise ValueError('Duplicate network row')
        result[name]={'rx_bytes':vals[0],'rx_packets':vals[1],'rx_errors':vals[2],'rx_drops':vals[3],
                      'tx_bytes':vals[8],'tx_packets':vals[9],'tx_errors':vals[10],'tx_drops':vals[11]}
    if set(result)!=set(['eth0','eth1']):raise ValueError('Both port rows required')
    return result

def parse_stats(output):
    stats={}
    for line in output.splitlines():
        hit=re.fullmatch(rb'([a-z_0-9]+)=([0-9]+)',line)
        if hit:stats[hit[1].decode()]=int(hit[2])
    for key in ['irq_count','irq_rx_done','irq_tx_done','rx_quiesce_timeouts','rx_restart_total']:
        if key not in stats:raise ValueError('Missing '+key)
    return stats

def udp_window(flow,host,port,sequence):
    flow.safe();flow.b.force_lease();flow.fresh()
    flow.s.write(b'udpecho\n',timeout=3)
    flow.wait(rb'UDP_READY_PORT9009\r?\n',15)
    client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    client.bind(('192.168.1.49',0));client.settimeout(.3)
    start=time.monotonic();rtts=[];sent=0;corrupt=0;unexpected=0
    deadline=start+8.8
    try:
        while time.monotonic()<deadline:
            stamp=time.monotonic();nonce=bytes.fromhex(flow.nonce)
            payload=nonce+sequence.to_bytes(4,'big')+sent.to_bytes(4,'big')+bytes(i%256 for i in range(360))
            sent+=1;client.sendto(payload,(host,port))
            try:
                data,peer=client.recvfrom(1024)
                if peer!=(host,port):unexpected+=1
                elif data!=payload:corrupt+=1
                else:rtts.append((time.monotonic()-stamp)*1000)
            except socket.timeout:pass
            flow.safe()
            rest=.065-(time.monotonic()-stamp)
            if rest>0:time.sleep(rest)
    finally:client.close()
    response=flow.wait(e.PROMPT,20)
    recv=re.findall(rb'(?m)^UDP_RECEIVED=(\d+)\r?$',response)
    echo=re.findall(rb'(?m)^UDP_ECHOED=(\d+)\r?$',response)
    e.m.require(len(recv)==len(echo)==1,'Guest UDP accounting missing')
    return {'window':sequence,'requests':sent,'responses':len(rtts),'corrupt':corrupt,'unexpected_peers':unexpected,
            'guest_received':int(recv[0]),'guest_echoed':int(echo[0]),'payload_bytes':384,
            'seconds':round(time.monotonic()-start,3),'rtt_p50_ms':round(statistics.median(rtts),3) if rtts else None,
            'rtt_max_ms':round(max(rtts),3) if rtts else None,
            'pass':sent==len(rtts)==int(recv[0])==int(echo[0]) and not corrupt and not unexpected}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--windows',type=int,default=15);p.add_argument('--prepare-eth1',action='store_true')
    p.add_argument('--observe',action='store_true');p.add_argument('--reopen',action='store_true')
    p.add_argument('--port',type=int,choices=[0,1],default=0)
    p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token')
    a=p.parse_args();e.m.require(1<=a.windows<=30,'Window bounds')
    a.output.mkdir(exist_ok=False);config=json.loads(a.config.read_text());e.preflight(config)
    session=None;log=e.Log(a.output/'uart-redacted.txt');flow=None
    result={'schema':'openmitrastar.eth73-bounded-soak/v1','status':'STOP','started_utc':datetime.now(timezone.utc).isoformat(),
            'port':'eth'+str(a.port),'reboots':0,'bootm':0,'flash_writes':0,'bootenv_writes':0,'windows':[]}
    try:
        b=e.Backend(a);b.force_lease();session=e.m.continuous_session(log,b)
        flow=e.Flow(b,session,hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32],config=config,output=a.output)
        n=flow.command('echo '+flow.nonce)
        e.m.require(re.findall(rb'(?m)^ETH73_NONCE=([^\r\n]+)\r?$',n)==[flow.nonce.encode()],'Fresh UART nonce mismatch')
        release=flow.command('status');e.m.require(e.KERNEL in release,'Current kernel differs')
        result['uart_nonce_verified']=True
        if a.observe:
            result['before']=parse_net(flow.command('netstats'))
            result['irq_before']=flow.command('interrupts').decode(errors='replace')
            if a.reopen:
                e.m.require(('ETH'+str(a.port)+'_DOWN=0').encode() in flow.command('eth'+str(a.port)+'down'),'Port close failed')
                e.m.require(('ETH'+str(a.port)+'_UP=0').encode() in flow.command('eth'+str(a.port)+'up',seconds=35),'Port reopen failed')
            result['after']=parse_net(flow.command('netstats'))
            result['irq_after']=flow.command('interrupts').decode(errors='replace')
            result['primary_stats']=parse_stats(flow.command('ethstats'))
            result.update(status='PASS_UART_PORT_OBSERVATION',kernel_status=flow.command('status').decode(errors='replace'))
            return
        if a.prepare_eth1:
            e.m.require(b'ETH1_UP=0' in flow.command('eth1up',seconds=35),'Second port open failed')
            e.m.require(b'ETH0_DOWN=0' in flow.command('eth0down'),'Primary stop failed')
            result.update(status='PASS_ETH1_ARMED_FOR_CABLE_MOVE',target='192.168.1.91',net=parse_net(flow.command('netstats')))
            return
        before=parse_net(flow.command('netstats'));stats_before=parse_stats(flow.command('ethstats'))
        irq_before=flow.command('interrupts');result['before']=before;result['stats_before']=stats_before
        result['kernel_status_before']=release.decode(errors='replace')
        with (a.output/'progress.jsonl').open('x',buffering=1) as progress:
            for window in range(a.windows):
                value=udp_window(flow,'192.168.1.'+str(90+a.port),9009,window)
                result['windows'].append(value);progress.write(json.dumps(value)+'\n');print(json.dumps(value),flush=True)
                e.m.require(value['pass'],'Packet loss/corruption or accounting discrepancy')
        after=parse_net(flow.command('netstats'));stats_after=parse_stats(flow.command('ethstats'))
        irq_after=flow.command('interrupts');result.update(after=after,stats_after=stats_after,
             irq_before=irq_before.decode(errors='replace'),irq_after=irq_after.decode(errors='replace'),
             kernel_status_after=flow.command('status').decode(errors='replace'))
        selected='eth'+str(a.port)
        for key in ['rx_errors','tx_errors']:
            e.m.require(after[selected][key]==before[selected][key],'Packet error counter increased')
        e.m.require(stats_after['rx_quiesce_timeouts']==stats_before['rx_quiesce_timeouts'],'RX quiesce timeout')
        result.update(status='PASS_BOUNDED_UDP_CONTINUITY',requests=sum(w['requests'] for w in result['windows']),
                      responses=sum(w['responses'] for w in result['windows']),
                      scope='Rate limited 384-byte echo windows ~15 packets/s. No throughput ceiling, long stress or full firmware soak proof.')
    except BaseException as error:
        result.update(error_type=type(error).__name__,error_reason=str(error));raise
    finally:
        if session:session.close()
        result.update(finished_utc=datetime.now(timezone.utc).isoformat(),raw_uart_saved=False,omitted_lines=log.omitted)
        (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
