"""Relink the exact F358 C/config with only the qualified F352 DT binding."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,hashlib,json,shlex,shutil,subprocess
from elftools.elf.elffile import ELFFile
from dtb_find_nodes import parse
from f336_wdt_ram_contract import serialize,node_map,reservations
from build_f340_watchdog_kernel import extract_embedded
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
BASE='/home/user/openmitrastar-build/f358-flash-arbitration-20260921T173956Z'
INPUT=DEVICE/'analysis/f358-flash-arbitration-20260921T173956Z/a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def item(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def main():
 assert shutil.disk_usage('C:/').free>500*1024*1024
 assert sha(INPUT/'f358.config')=='f374913b8d2adc7c4138af32263b650eeb967b4defc0139cfd00e6bff7ba1118'
 assert sha(INPUT/'f358.dtb')=='d317a0b3680631548796909ec6970c4e3c2f4d204a2f5b83e601c88931937a47'
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=DEVICE/'analysis'/('f362-dual-ethernet-kernel-'+stamp);out.mkdir(parents=True)
 dt=out/'f362.dtb';nodes=copy.deepcopy(parse(INPUT/'f358.dtb'));node=next(n for n in nodes if n['path']=='/soc/ethernet@e8000000')
 assert dict(node['props'])['status']==b'okay\0'
 node['props']=[(k,b'openmitrastar,f352-dual-emac\0' if k=='compatible' else v) for k,v in node['props']]+[('qtn,f352-dual-direct',b'')]
 dt.write_bytes(serialize(nodes,(INPUT/'f358.dtb').read_bytes()))
 old=node_map(INPUT/'f358.dtb');new=node_map(dt);diff=[(path,key) for path in set(old)|set(new) for key in set(old.get(path,{}))|set(new.get(path,{})) if old.get(path,{}).get(key)!=new.get(path,{}).get(key)]
 assert sorted(diff)==[('/soc/ethernet@e8000000','compatible'),('/soc/ethernet@e8000000','qtn,f352-dual-direct')]
 assert reservations(dt.read_bytes())==reservations((INPUT/'f358.dtb').read_bytes())
 build='/home/user/openmitrastar-build/f362-dual-ethernet-'+stamp;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');q=shlex.quote
 script=f'''set -eu
out={q(linux(out))}
base={q(BASE)}
build={q(build)}
tc={q(tc)}
test ! -e "$build"
mkdir -p "$build"
cp -a --reflink=auto "$base/a" "$build/a"
cp "$out/f362.dtb" "$build/a/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb"
SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f358-flash-arbitration KBUILD_BUILD_VERSION=358 make -s -C "$base/linux" O="$build/a" ARCH=arc CROSS_COMPILE="$tc" KCFLAGS="-ffile-prefix-map=$base/a=/f358-output" -j8 vmlinux uImage.bin > "$out/build.log" 2>&1
cmp "$out/f362.dtb" "$build/a/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb"
cp "$build/a/vmlinux" "$out/f362.vmlinux"
cp "$build/a/arch/arc/boot/uImage.bin" "$out/f362.uncompressed.uImage"
cp "$build/a/.config" "$out/f362.config"
if [ -f "$build/a/Module.symvers" ]; then cp "$build/a/Module.symvers" "$out/Module.symvers"; else cp "$build/a/vmlinux.symvers" "$out/Module.symvers"; fi
"${{tc}}objcopy" -O binary -R .note -R .note.gnu.build-id -R .comment -S "$out/f362.vmlinux" "$out/f362.raw.bin"
python3 - "$base/a" "$build/a" "$out/object-delta.json" <<'PY'
import pathlib,sys,hashlib,json
a,b=map(pathlib.Path,sys.argv[1:3]);changed=[];count=0
for p in a.rglob('*.o'):
 r=p.relative_to(a);other=b/r
 if other.is_file():
  count+=1
  if hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(other.read_bytes()).digest():changed.append(str(r))
pathlib.Path(sys.argv[3]).write_text(json.dumps(dict(compared=count,changed=changed)))
PY
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr)
 assert run.returncode==0,run.stderr.decode(errors='replace')[-1000:]
 qualify(out,build)

def qualify(out,build):
 dt=out/'f362.dtb';old=node_map(INPUT/'f358.dtb');new=node_map(dt)
 diff=[(path,key) for path in set(old)|set(new) for key in set(old.get(path,{}))|set(new.get(path,{})) if old.get(path,{}).get(key)!=new.get(path,{}).get(key)]
 assert sorted(diff)==[('/soc/ethernet@e8000000','compatible'),('/soc/ethernet@e8000000','qtn,f352-dual-direct')]
 assert new['/soc/ethernet@e8000000']['status']==b'okay\0'
 assert sha(out/'f362.config')==sha(INPUT/'f358.config')
 assert sha(out/'Module.symvers')==sha(INPUT/'Module.symvers')
 embedded,address=extract_embedded(out/'f362.vmlinux');assert embedded==dt.read_bytes()
 delta=json.loads((out/'object-delta.json').read_text());allowed={'vmlinux.o','arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb.o','.tmp_kallsyms1.o','.tmp_kallsyms2.o','.tmp_kallsyms3.o'}
 assert set(delta['changed'])<=allowed,delta
 with (out/'f362.vmlinux').open('rb') as f:
  elf=ELFFile(f);entry=int(elf.header['e_entry']);end=int(elf.get_section_by_name('.symtab').get_symbol_by_name('_end')[0]['st_value'])
 assert entry==0x8493e000 and end<0x88000000
 module=ROOT/'outputs/kernel-port/f352-qualified-20260921T163718Z/a/qtn-topaz-emac-f352.ko';assert sha(module)=='41c5cb625b22776d0075207760df59fd20d4a34bddb1c7568adfa83391cbc05e'
 imports={s.split()[-1] for s in (ROOT/'outputs/kernel-port/f352-dual-emac-20260921T162320Z/imports.txt').read_text().splitlines() if s.strip()};exports={s.split()[1] for s in (out/'Module.symvers').read_text().splitlines()};assert imports<=exports,imports-exports
 result={'schema':'openmitrastar.f362-dt-kernel/v1','status':'PASS_OFFLINE_DT_ONLY_KERNEL','kernel_build':'#358 @1790006400','build_directory':build+'/a','source':BASE+'/linux','dt_delta':diff,'c_objects':delta,'config_unchanged':True,'exports_unchanged':True,'kernel_reproducibility':'single DT relink; existing F358 C objects reused','entry':hex(entry),'load':'0x8493a000','end':hex(end),'embedded_dtb_address':hex(address),'module_imports_resolved':len(imports),'artifacts':{p.name:item(p) for p in [out/'f362.vmlinux',out/'f362.raw.bin',out/'f362.uncompressed.uImage',dt,out/'f362.config',out/'Module.symvers']},'hardware_actions':False}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':result['status']}),flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--qualify-existing',type=Path);a=ap.parse_args()
 if a.qualify_existing:
  out=a.qualify_existing.resolve();assert not (out/'result.json').exists()
  qualify(out,'/home/user/openmitrastar-build/f362-dual-ethernet-'+out.name.rsplit('-',1)[1])
 else:main()
