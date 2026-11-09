"""Offline build of F352; clones module context and never contacts HGW."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,shutil,subprocess
import prepare_f352_dual_emac as overlay
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def linux(path):p=Path(path).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def require(ok,code):
 if not ok:raise ValueError(code)
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/kernel-port'/('f352-dual-emac-'+stamp);out.mkdir(exist_ok=False)
 source=overlay.DEST;require(sha(overlay.SOURCE)==overlay.BASE_SHA,'base_source_drift');require((source/'qtn-topaz-emac-f352.c').read_text(encoding='utf-8')==overlay.render(overlay.SOURCE.read_text(encoding='utf-8')),'generated_source_drift')
 handoff=ROOT/'outputs/preflight/f340-qualified-20260921T134752Z/handoff.json';require(sha(handoff)=='63214c4adaed55f42a04e51b6499c1d3797a1b1b034557a3605f44fb35d8e626','handoff_drift');h=json.loads(handoff.read_text(encoding='ascii'))
 context=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f341-closure-20260921T134402Z/manifest.json';require(sha(context)=='14b8ff7b809937f08e07b6213c7c2b6be5b3a5d653f78205575935c4ee980315','module_context_drift');m=json.loads(context.read_text(encoding='ascii'))
 prefix=str(h['image']['path']).removesuffix('.webformat.bin');config=Path(prefix+'.config');kernel=Path(prefix+'.vmlinux');dtb=Path(prefix+'.dtb');symvers=Path(h['kernel_module_symvers'])
 require(sha(config)==m['kernel_config_sha256'] and sha(kernel)==m['kernel_vmlinux_sha256'] and sha(symvers)==h['kernel_module_symvers_sha256'],'abi_drift')
 sourcefiles=list(source.iterdir());sources={str(p):sha(p) for p in sourcefiles+[overlay.SOURCE,Path(overlay.__file__),Path(__file__),handoff,context,config,kernel,dtb,symvers] if p.is_file()}
 shutil.copytree(source,out/'source');shutil.copyfile(symvers,out/'f340.Module.symvers');shutil.copyfile(dtb,out/'f340-baseline.dtb')
 q=shlex.quote;build='/home/user/openmitrastar-build/f352-module-context-'+stamp
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
 script=f'''set -eu
out={q(linux(out))}
src={q(h['kernel_source'])}
context={q(build)}
tc={q(tc)}
test ! -e "$context"
cp -a --reflink=auto {q(m['isolated_module_context'])} "$context"
test "$(sha256sum "$context/.config" | cut -d ' ' -f1)" = {sha(config)}
test "$(sha256sum "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c" | cut -d ' ' -f1)" = {overlay.BASE_SHA}
cp "$out/f340.Module.symvers" "$context/Module.symvers"
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -fanalyzer "$out/source/test_f352_contract.c" -o "$out/host-test"
"$out/host-test" > "$out/tests.log"
for lane in a b; do
 mkdir "$out/$lane"
 cp "$out/source/qtn-topaz-emac-f352.c" "$out/source/f352_contract.h" "$out/source/f352_pair.inc" "$out/source/Makefile" "$out/$lane/"
 make -s -C "$src" O="$context" M="$out/$lane" ARCH=arc CROSS_COMPILE="$tc" modules > "$out/build-$lane.log" 2>&1
done
cmp "$out/a/qtn-topaz-emac-f352.ko" "$out/b/qtn-topaz-emac-f352.ko"
"${{tc}}nm" -u "$out/a/qtn-topaz-emac-f352.ko" > "$out/imports.txt"
"${{tc}}nm" {q(linux(kernel))} > "$out/kernel-symbols.txt"
"${{tc}}readelf" -h "$out/a/qtn-topaz-emac-f352.ko" > "$out/elf.txt"
"${{tc}}objdump" -dr "$out/a/qtn-topaz-emac-f352.ko" > "$out/disassembly.txt"
dtc -I dtb -O dts "$out/f340-baseline.dtb" > "$out/f340-baseline.dts" 2> "$out/dtc.log"
test "$(sha256sum "$context/.config" | cut -d ' ' -f1)" = {sha(config)}
'''
 (out/'build.sh').write_bytes(script.encode('ascii'));run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True,timeout=180)
 (out/'build.stdout').write_bytes(run.stdout);(out/'build.stderr').write_bytes(run.stderr);errors=[]
 if run.returncode:errors.append('build_failed')
 else:
  kernel_symbols=(out/'kernel-symbols.txt').read_text(encoding='ascii')
  for line in (out/'imports.txt').read_text(encoding='ascii').splitlines():
   symbol=line.split()[-1]
   if not re.search(r'\b__ksymtab_'+re.escape(symbol)+r'$',kernel_symbols,re.M):errors.append('unexported:'+symbol)
  require('ARC700, v4 ABI' in (out/'elf.txt').read_text(encoding='ascii'),'wrong_abi')
 for path,digest in sources.items():require(sha(path)==digest,'source_changed_during_build')
 artifact=out/'a/qtn-topaz-emac-f352.ko'
 result=dict(schema='openmitrastar.f352-dual-emac/v1',status='FAIL_OFFLINE_BUILD' if errors else 'PASS_OFFLINE_DUAL_PORT_DRIVER',errors=errors,hardware_actions=False,firmware_created=False,default_dt_status='disabled',config_unchanged=True,isolated_module_context=build,reproducible=not errors,
  tests=(out/'tests.log').read_text(encoding='ascii').strip() if (out/'tests.log').exists() else '',artifact=dict(path=str(artifact),sha256=sha(artifact),bytes=artifact.stat().st_size) if artifact.exists() else None,sources=sources,
  limits=['No physical port, link, throughput or simultaneous connector test','No TQE accelerated switching','PHYLIB remains disabled; explicit bounded standard-MII link monitor','Bootbase must already release both MACs and clear DMA soft reset; no global reset here','Runtime bridge attachment requires separate F352 overlay and validation'])
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii');print(json.dumps(dict(status=result['status'],result=str(out/'result.json'),artifact=result['artifact'],errors=errors),indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
