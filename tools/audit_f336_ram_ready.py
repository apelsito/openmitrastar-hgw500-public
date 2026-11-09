"""Additional immutable file-only F336 payload/config/peer observations."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,re,struct
from elftools.elf.elffile import ELFFile
import f336_wdt_ram_contract as c
from build_f336_wdt_ram import extract_embedded

def config(path):
    result={}
    for line in path.read_text().splitlines():
        if line.startswith('CONFIG_'):key,value=line.split('=',1);result[key]=value
        elif re.fullmatch(r'# CONFIG_\w+ is not set',line):result[line[2:-11]]='n'
    return result
def delta(a,b):return {k:[a.get(k),b.get(k)] for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build-dir',type=Path,required=True);args=ap.parse_args();build=args.build_dir.resolve()
    report=json.loads((build/'result.json').read_text());c.require(report['status']=='PASS_OFFLINE_RAM_ARTIFACT_PHYSICAL_GATES_UNRUN','build not qualified')
    out=c.ROOT/'outputs/kernel-port'/('f336-ram-readiness-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    raw=(build/'a/f336.raw.bin').read_bytes();dt,address=extract_embedded(build/'a/f336.vmlinux');offset=address-c.LOAD
    c.require(offset>=0 and raw[offset:offset+len(dt)]==dt,'actual decompressed RAM payload lacks reviewed DT')
    f321=config(c.F321/(c.F321_BASE+'.config'));f329=config(c.F329/'f329.config');f336=config(build/'a/f336.config');change=delta(f329,f336)
    c.require(set(change)=={'CONFIG_WATCHDOG_SYSFS','CONFIG_CC_VERSION_TEXT'},'unexpected F329/F336 config delta')
    c.require(change['CONFIG_WATCHDOG_SYSFS']==['n','y'],'unexpected sysfs setting')
    c.require(f336['CONFIG_MODVERSIONS']=='n','module versioning needs additional ABI check')
    audit=json.loads((build/'peer-audit/result.json').read_text());c.require(audit['missing_imports']=={},'peer unresolved imports')
    c.require(audit['kernel_sha256']==c.sha(build/'a/f336.vmlinux'),'peer audit not bound to this kernel')
    literals={name:entry['executable_wdt_literal_hits'] for name,entry in audit['entries'].items() if entry.get('executable_wdt_literal_hits')}
    fw=build/'peer-audit/payloads/lib/firmware/qtn_driver.qtn_ruby.0.bin'
    with fw.open('rb') as f:
        elf=ELFFile(f);cursor=int(elf.header['e_ehsize'])+int(elf.header['e_phnum'])*int(elf.header['e_phentsize']);segments=[]
        for i,seg in enumerate(elf.iter_segments()):
            size=int(seg['p_filesz']);segments.append(dict(index=i,filesz=size,offset=int(seg['p_offset']),loader_sequential_offset=cursor,matching=not size or cursor==int(seg['p_offset'])));cursor+=size
    c.require(all(s['matching'] for s in segments),'firmware scan differs from real sequential loader')
    result=dict(status='PASS_OFFLINE_PAYLOAD_CONFIG_AND_PEER_BINDING',hardware_actions=False,flash_allowed=False,
        build_result_sha256=c.sha(build/'result.json'),kernel_sha256=c.sha(build/'a/f336.vmlinux'),artifact=report['artifact'],
        raw_dtb=dict(address=hex(address),raw_offset=offset,bytes=len(dt),sha256=c.sha(build/'embedded.dtb'),byte_equal=True),
        f321_to_f329_config_delta=delta(f321,f329),f329_to_f336_config_delta=change,
        peer_count=len(audit['entries']),missing_imports={},modversions=False,peer_runtime_acceptance=False,
        firmware_literal_hits=literals,firmware_segment_loader_binding=segments,
        firmware_interpretation='All WDT literal hits in MuC PF_X segment 8 are odd byte offsets: not direct halfword-aligned ARC LIMM references. No CRR literal was found. Data/computed/indirect accesses remain possible. This is neither a proven feeder nor proof of absence.',
        producer_exclusivity_proven=False,
        physical_gate='Keep normal CPU/SSH running and FD open; stop only probe KEEPALIVE. Observe CR EN and CCVR at 200ms intervals. Reload, immobile counter, or no reset within 40s is NOT_ACCEPTED. Software recovery afterward is not watchdog proof.',
        core_worker_gate='F329 max_timeout is bounded to max_hw_heartbeat_ms/1000. Requested timeout8 does not exceed the hardware ceiling, so watchdog_need_worker is false while active/FD held. Closing may change this and occurs only after an explicit negative verdict.',
        reset_cause_and_clock_proven=False)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'output':str(out),'status':result['status'],'config_delta':change,'literal_files':list(literals)},indent=2))
if __name__=='__main__':main()
