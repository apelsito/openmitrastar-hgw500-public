"""Close F352 offline using its already-built ABI-matched module; no new clone."""
from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,os,re,shlex,shutil,struct,subprocess
from elftools.elf.elffile import ELFFile
import dtb_find_nodes
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/kernel-port/f352-dual-emac-20260921T162320Z'
SOURCE=ROOT/'work/kernel-port/modules/f352_dual_emac'
SHA='41c5cb625b22776d0075207760df59fd20d4a34bddb1c7568adfa83391cbc05e'
def check(ok,reason):
 if not ok:raise ValueError(reason)
def space():check(shutil.disk_usage('C:/').free>500*1024*1024,'C_free_must_exceed_500MiB')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def linux(path):p=Path(path).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def atomic(path,data):
 space();tmp=path.with_name(path.name+'.tmp');tmp.write_bytes(data);check(tmp.read_bytes()==data,'short_write');os.replace(tmp,path)
def embedded(path):
 with path.open('rb') as stream:
  elf=ELFFile(stream);symbol=elf.get_section_by_name('.symtab').get_symbol_by_name('__dtb_topaz_mitrastar_squashfs_begin')[0];address=int(symbol['st_value'])
  for section in elf.iter_sections():
   base=int(section['sh_addr']);size=int(section['sh_size'])
   if base<=address<base+size:
    data=section.data()[address-base:];length=struct.unpack_from('>I',data,4)[0];check(data[:4]==b'\xd0\x0d\xfe\xed' and length<=len(data),'embedded_bounds');return data[:length]
 raise ValueError('embedded_dtb_absent')
def main():
 space();base=json.loads((BASE/'result.json').read_text(encoding='ascii'));check(base['status']=='PASS_OFFLINE_DUAL_PORT_DRIVER','baseline_result')
 check(base['artifact']['sha256']==SHA and base['artifact']['bytes']==24544 and base['reproducible'] is True,'module_metadata')
 compiled=['qtn-topaz-emac-f352.c','f352_contract.h','f352_pair.inc','Makefile','test_f352_contract.c']
 for name in compiled:check(sha(SOURCE/name)==base['sources'][str(SOURCE/name)],'compiled_input_drift_'+name)
 check(sha(BASE/'a/qtn-topaz-emac-f352.ko')==sha(BASE/'b/qtn-topaz-emac-f352.ko')==SHA,'double_build_bytes')
 check((BASE/'tests.log').read_text(encoding='ascii').strip()=='F352_CONTRACT_PASS checks=4933 hardware_actions=0','contract_tests')
 check(sha(ROOT/'tools/build_f352_dual_emac.py')=='d0b13263ec99c64607e477ba71abacaa379d53c62655392b5fc97f2793d7c122','restored_builder_exact');ast.parse((ROOT/'tools/build_f352_dual_emac.py').read_bytes())
 kernel=next(Path(path) for path in base['sources'] if path.endswith('.vmlinux'));dtb=kernel.with_suffix('.dtb');config=kernel.with_suffix('.config')
 for path in (kernel,dtb,config):check(sha(path)==base['sources'][str(path)],'baseline_artifact_drift')
 check(embedded(kernel)==dtb.read_bytes(),'kernel_dtb_sidecar_not_embedded')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/kernel-port'/('f352-qualified-'+stamp);out.mkdir(exist_ok=False)
 for name in ('a','b','source'):(out/name).mkdir()
 for lane in ('a','b'):shutil.copyfile(BASE/lane/'qtn-topaz-emac-f352.ko',out/lane/'qtn-topaz-emac-f352.ko')
 for path in SOURCE.iterdir():
  if path.is_file():space();shutil.copyfile(path,out/'source'/path.name)
 shutil.copyfile(dtb,out/'f340-embedded.dtb')
 inputs=[*(path for path in SOURCE.iterdir() if path.is_file()),ROOT/'tools/prepare_f352_dual_emac.py',ROOT/'tools/build_f352_dual_emac.py',ROOT/'tools/test_f352_bridge.py',Path(__file__),Path(dtb_find_nodes.__file__),BASE/'result.json',BASE/'tests.log',BASE/'elf.txt',BASE/'imports.txt',kernel,dtb,config]
 for name in ['drivers/ruby/arasan_emac_ahb.c','drivers/ruby/emac_lib.c','drivers/topaz/switch_emac.c','common/ruby_arasan_emac_ahb.h','common/ruby_platform.h','common/ruby_board_db.h']:inputs.append(ROOT/'work/sources/Quantenna-GPL'/name)
 for name in ['etc/init.d/S40network','scripts/mac_setlocal']:inputs.append(ROOT/'work/hgw500-rootfs-live/squashfs-root'/name)
 inputs.append(ROOT/'outputs/port-parity/hgw500-20260921T095258Z/f321-public-code/usr__sbin__om-radio5-start')
 pins={str(path):sha(path) for path in inputs};q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
 script=f'''set -eu
out={q(linux(out))}
dtc -I dtb -O dts "$out/f340-embedded.dtb" > "$out/f340-embedded.dts" 2> "$out/dtc-baseline.log"
cat "$out/f340-embedded.dts" "$out/source/f352-disabled.dtsi" > "$out/f352-disabled.dts"
dtc -I dts -O dtb "$out/f352-disabled.dts" -o "$out/f352-disabled.dtb" 2> "$out/dtc-candidate.log"
python3 {q(linux(ROOT/'tools/test_f352_bridge.py'))} --result "$out/bridge-tests.json" > "$out/bridge-tests.stdout" 2> "$out/bridge-tests.stderr"
{q(tc+'objdump')} -d --disassemble=qtn_emac_probe {q(linux(kernel))} > "$out/f340-probe.disassembly.txt"
{q(tc+'objdump')} -d --disassemble=qtn_emac_open {q(linux(kernel))} > "$out/f340-open.disassembly.txt"
'''
 atomic(out/'qualify.sh',script.encode('ascii'));run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'qualify.sh')],capture_output=True,timeout=90)
 atomic(out/'stdout.log',run.stdout);atomic(out/'stderr.log',run.stderr);check(run.returncode==0,'qualification_commands_failed')
 before={n['path']:dict(n['props']) for n in dtb_find_nodes.parse(out/'f340-embedded.dtb')};after={n['path']:dict(n['props']) for n in dtb_find_nodes.parse(out/'f352-disabled.dtb')}
 expected={path:dict(props) for path,props in before.items()};expected['/soc/ethernet@e8000000'].update(compatible=b'openmitrastar,f352-dual-emac\0',status=b'disabled\0');expected['/soc/ethernet@e8000000']['qtn,f352-dual-direct']=b''
 check(after==expected,'dt_change_outside_three_ethernet_properties');bridge=json.loads((out/'bridge-tests.json').read_text(encoding='ascii'));check(bridge['passed'] is True and len(bridge['cases'])==12,'bridge_tests')
 probe=(out/'f340-probe.disassembly.txt').read_text(encoding='ascii');check(len(re.findall(r'\bbl(?:\.d)?\s+[^\n]*<register_netdev>',probe))==1,'baseline_single_register_call')
 check(b'Topaz direct EMAC RAM-rescue driver, no HBM/TQE/MTD path' in kernel.read_bytes(),'baseline_direct_driver_marker')
 for path,digest in pins.items():check(sha(path)==digest,'source_drift')
 result=dict(schema='openmitrastar.f352-qualified/v1',status='PASS_OFFLINE_DUAL_ETHERNET_PARITY_STEP',hardware_actions=False,firmware_created=False,source_pins=pins,
  artifact=dict(path=str(out/'a/qtn-topaz-emac-f352.ko'),bytes=24544,sha256=SHA),compiled_inputs_unchanged=True,reproducible_module=True,original_build=str(BASE/'result.json'),reused_isolated_context=base['isolated_module_context'],new_clones=0,
  core_tests=4933,bridge_tests=12,gcc_analyzer='PASS_FROM_SOURCE_MATCHED_BUILD',kernel_abi='F340 Linux 5.10.260-openmitrastar-radiohw ARC700 v4',
  dt=dict(path=str(out/'f352-disabled.dtb'),sha256=sha(out/'f352-disabled.dtb'),status='disabled',embedded_f340_verified=True,changed_node='/soc/ethernet@e8000000',changed_properties=['compatible','status','qtn,f352-dual-direct'],all_other_properties_preserved=True),
  findings=dict(f340_registered_netdevs=1,f340_simultaneous_physical_macs=1,f340_selection='first_linked_port_at_ndo_open_only',f340_switch_emac_mode='symbols_only',f352_registered_netdevs=2,f352_dma='independent_per_MAC',phy_pairs=[{'netdev_order':0,'mac':1,'phy':3,'irq':20},{'netdev_order':1,'mac':0,'phy':1,'irq':19}],physical_connector_labels='NOT_ESTABLISHED',secondary_mac='OEM first-octet +2 from effective runtime primary, never logged'),
  limits=['Physical connector/link/traffic/dual-port acceptance UNRUN','No TQE accelerated forwarding, VLAN/QoS/offload parity claim','No flash, radio or AELITA operation','Both MAC reset bits and DMA soft reset checked; no global IOSS/NETSS/PHY reset','Default DT disabled; future candidate must explicitly integrate driver and startup helper','Initial DT MACs provisional; real secondary address is applied by runtime helper before eth1 UP','This step does not complete overall OEM Ethernet or release acceptance'])
 atomic(out/'result.json',(json.dumps(result,indent=2)+'\n').encode('ascii'));print(json.dumps(dict(status=result['status'],result=str(out/'result.json'),sha256=sha(out/'result.json'),artifact=result['artifact'],C_free=shutil.disk_usage('C:/').free),indent=2))
if __name__=='__main__':main()
