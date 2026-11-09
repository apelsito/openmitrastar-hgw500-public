"""Build the inactive F350 kernel module twice against its own staged kernel."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shlex,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/versions/f350-spi-journal/provider'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--kernel-build',type=Path,required=True);args=ap.parse_args()
 kernel=args.kernel_build.resolve();report=json.loads((kernel/'result.json').read_text())
 assert report['status']=='PASS_OFFLINE_READER_ARBITRATION_KERNEL' and report['kernel_build_identity']==350
 assert report['reproducible'] and not report['hardware_actions']
 for item in report['artifacts'].values():assert sha(item['path'])==item['sha256']
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/kernel-port'/('f350-provider-'+stamp);out.mkdir(parents=True,exist_ok=False)
 for lane in ['a','b']:shutil.copytree(SOURCE,out/lane)
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');q=shlex.quote
 script=f'''set -eu
out={q(linux(out))}
src={q(report['isolated_source'])}
kout={q(report['build_directories'][0])}
tc={q(tc)}
make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" modules_prepare > "$out/modules-prepare.log" 2>&1
cp {q(linux(kernel/'a/Module.symvers'))} "$kout/Module.symvers"
for lane in a b; do
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f350-journal KBUILD_BUILD_VERSION=350 make -s -C "$src" O="$kout" M="$out/$lane" ARCH=arc CROSS_COMPILE="$tc" KCFLAGS="-ffile-prefix-map=$out/$lane=/f350-provider" -j2 modules > "$out/build-$lane.log" 2>&1
 "${{tc}}nm" -u "$out/$lane/qtn_f350_journal.ko" > "$out/$lane/imports.txt"
 "${{tc}}readelf" -h "$out/$lane/qtn_f350_journal.ko" > "$out/$lane/elf.txt"
 "${{tc}}objdump" -d "$out/$lane/qtn_f350_journal.ko" > "$out/$lane/disassembly.txt"
done
cmp "$out/a/qtn_f350_journal.ko" "$out/b/qtn_f350_journal.ko"
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
 (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
 result={'schema':'openmitrastar.f350-spi-journal-module/v1','status':'FAIL_BUILD','exit_code':r.returncode,
  'hardware_actions':False,'default_mmio':False,'default_program':False,'flash_eligible':False,
  'physical_spi_control_observed':False,'physical_id_protection_observed':False,
  'kernel_manifest':{'path':str(kernel/'result.json'),'sha256':sha(kernel/'result.json')},
  'sources':{str(p):sha(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()}}
 if not r.returncode:
  module=out/'a/qtn_f350_journal.ko';imports=[line.split()[-1] for line in (out/'a/imports.txt').read_text().splitlines() if line.strip()]
  exports={line.split()[1] for line in (kernel/'a/Module.symvers').read_text().splitlines()}
  unresolved=sorted(set(imports)-exports);assert not unresolved,unresolved
  assert sha(module)==sha(out/'b/qtn_f350_journal.ko')
  result.update(status='PASS_OFFLINE_KERNEL_MODULE',reproducible=True,imports=imports,
   artifact={'path':str(module),'sha256':sha(module),'bytes':module.stat().st_size},
   limitations=['MMIO access completion and legacy control have not been physically qualified','common BP0 only; no individual/global protection writes','new kernel identity requires future supervisor/firmware binding'])
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json')}));return r.returncode
if __name__=='__main__':raise SystemExit(main())
