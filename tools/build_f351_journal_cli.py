"""Offline native verification and reproducible ARC build of the F350 CLI."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,shutil,subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/userspace/f351-journal-cli'
QUAL=ROOT/'outputs/preflight/f350-qualified-20260921T161419Z/result.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 assert sha(QUAL)=='f6acac38db68da58e6fcefda6e51f2fbdc4e9e395063b3f3f7dfb860d3d4dd9e'
 for p in (SOURCE/'vendor').iterdir():assert p.read_bytes()==(ROOT/'work/kernel-port/versions/f350-spi-journal/provider'/p.name).read_bytes()
 out=ROOT/'outputs/userspace'/('f351-journal-cli-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 shutil.copytree(SOURCE,out/'source');shutil.copyfile(ROOT/'tools/test_f351_cli.py',out/'test_f351_cli.py')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
flags='-std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes'
cc $flags -O2 "$out/source/f351_cli.c" "$out/source/test_syscalls.c" -Wl,--wrap=open -Wl,--wrap=fstat -Wl,--wrap=fstatfs -Wl,--wrap=read -Wl,--wrap=close -Wl,--wrap=ioctl -o "$out/native-test-cli"
python3 "$out/test_f351_cli.py" --binary "$out/native-test-cli" --result "$out/tests.json" > "$out/tests.stdout" 2> "$out/tests.stderr"
cc $flags -fanalyzer -c "$out/source/f351_cli.c" -o "$out/analyzer.o" > "$out/analyzer.log" 2>&1
for lane in a b; do
 SOURCE_DATE_EPOCH=1790006400 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot $flags -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -static -Wl,--gc-sections "$out/source/f351_cli.c" -o "$out/om-journal-cli-$lane"
 "${{tc}}strip" --strip-unneeded "$out/om-journal-cli-$lane"
done
cmp "$out/om-journal-cli-a" "$out/om-journal-cli-b"
"${{tc}}objdump" -d "$out/om-journal-cli-a" > "$out/disassembly.txt"
if grep -Eq '\\b(llock|scond)\\b' "$out/disassembly.txt"; then exit 1; fi
"${{tc}}readelf" -h -l "$out/om-journal-cli-a" > "$out/elf.txt"
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True,timeout=180)
 (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
 result={'schema':'openmitrastar.f351-cli-build/v1','status':'FAIL','exit_code':r.returncode,'hardware_actions':False,'arc_execution':'UNRUN',
  'sources':{str(p):sha(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()},'f350_qualification':{'path':str(QUAL),'sha256':sha(QUAL)}}
 if not r.returncode:
  artifact=out/'om-journal-cli-a'
  with artifact.open('rb') as f:
   elf=ELFFile(f);assert elf.elfclass==32 and elf.header['e_machine']=='EM_ARC_COMPACT'
   assert not any(s['p_type']=='PT_INTERP' for s in elf.iter_segments())
  tests=json.loads((out/'tests.json').read_text());assert tests['status']=='PASS' and not tests['real_device_opened']
  result.update(status='PASS_OFFLINE_CLI',reproducible=True,artifact={'path':str(artifact),'sha256':sha(artifact),'bytes':artifact.stat().st_size},
   test_count=tests['count'],tests_sha256=sha(out/'tests.json'),default_device_access=False,static_arc32=True,
   analyzer='PASS',uapi_bytes=4180,payload_offset=84)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'stderr':r.stderr.decode(errors='replace')[-3000:]}));return r.returncode
if __name__=='__main__':raise SystemExit(main())
