"""Link the unchanged R5 helper with the already qualified ARC noatomic sysroot."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,shutil,subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f367r5-regulatory-profile/userspace'
DST=ROOT/'work/kernel-port/f367r6-static-profile/userspace'
QUAL=ROOT/'outputs/kernel-port/f367r5-qualified-20260922T174654Z/result.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 if DST.exists():raise ValueError('immutable R6 source already exists')
 previous=json.loads(QUAL.read_text());assert previous['status']=='PASS_F367R5_REGULATORY_BUILD_LINK_AND_REPRODUCTION'
 for path,digest in previous['userspace_pins'].items():assert sha(path)==digest
 shutil.copytree(SOURCE,DST)
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 out=ROOT/'outputs/kernel-port'/('f367r6-static-profile-'+stamp);out.mkdir(parents=True,exist_ok=False)
 shutil.copytree(DST,out/'source')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
for lane in a b; do
 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=gnu11 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -Wall -Wextra -Werror -static -Wl,--gc-sections -Wl,--build-id=none "$out/source/om-f367-dfs-profile.c" -o "$out/om-f367-dfs-profile-$lane"
 "${{tc}}strip" --strip-unneeded "$out/om-f367-dfs-profile-$lane"
done
cmp "$out/om-f367-dfs-profile-a" "$out/om-f367-dfs-profile-b"
"${{tc}}objdump" -d "$out/om-f367-dfs-profile-a" > "$out/disassembly.txt"
"${{tc}}readelf" -h -l -d "$out/om-f367-dfs-profile-a" > "$out/elf.txt"
sha256sum /home/user/openmitrastar-uclibc-noatomic-sysroot/lib/libc.a > "$out/libc-static.sha256"
'''
 (out/'build.sh').write_bytes(script.encode())
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True,timeout=120)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr)
 if run.returncode:raise ValueError('static build failed: '+str(out))
 binary=out/'om-f367-dfs-profile-a';assert sha(binary)==sha(out/'om-f367-dfs-profile-b')
 with binary.open('rb') as stream:
  elf=ELFFile(stream);assert elf.header.e_machine=='EM_ARC_COMPACT' and elf.elfclass==32 and elf.little_endian
  assert elf.header.e_flags==0x403
  assert not any(p.header.p_type in ('PT_INTERP','PT_DYNAMIC') for p in elf.iter_segments())
  assert elf.get_section_by_name('.dynamic') is None and elf.get_section_by_name('.interp') is None
 disassembly=(out/'disassembly.txt').read_text();assert not re.search(r'\b(?:llock|scond)\b',disassembly)
 source=(DST/'om-f367-dfs-profile.c').read_text();arg=source.index('if(argc!=2||');assert arg<source.index('if(geteuid()!=0)')<source.index('if(state(json')<source.index('fd=socket(')
 probe='''#!/bin/ash
set +x
set -u
[ "$#" = 1 ] || exit 64
binary=$1
[ -f "$binary" ] || exit 65
actual=$(sha256sum "$binary" 2>/dev/null | awk '{print $1}')
[ "$actual" = "'''+sha(binary)+'''" ] || exit 66
# This argument is rejected by the first executable branch of main.
# No publish/check command, target state access or socket path is entered.
answer=$("$binary" __F367R6_INVALID_ARGUMENT_PROBE__ 2>&1)
rc=$?
if [ "$rc" != 1 ] || [ "$answer" != 'OMF367_PROFILE_REJECT reason=arguments errno=22' ]; then
 printf 'F367R6_STATIC_EXEC_FAIL exit_code=%s\n' "$rc"
 printf '%s\n' "$answer"
 exit 1
fi
printf 'F367R6_STATIC_EXEC_PASS invalid_argument_exit=1\n'
'''
 (out/'probe-invalid-argument.sh').write_bytes(probe.encode())
 report=dict(schema='openmitrastar.f367r6-static-profile/v1',status='PASS_OFFLINE_F367R6_STATIC_PROFILE',artifact=item(binary),runtime_path='/usr/sbin/om-f367-dfs-profile',reproducible=True,source_logic_unchanged=True,reused_r5_components=item(QUAL),reused_regulatory_tests=previous['regulatory_test'],source_pins={str(p):sha(p) for p in DST.iterdir()},builder=item(__file__),static_link=True,pt_interp=False,pt_dynamic=False,dt_needed=[],machine='EM_ARC_COMPACT',elf_class=32,little_endian=True,elf_flags='0x403 ARC700 v4 ABI',atomic_policy=dict(compiler_flag='-mno-atomic',sysroot='/home/user/openmitrastar-uclibc-noatomic-sysroot',llock_instructions=0,scond_instructions=0,static_libc=(out/'libc-static.sha256').read_text().strip()),probe=item(out/'probe-invalid-argument.sh'),probe_argument='__F367R6_INVALID_ARGUMENT_PROBE__',probe_expected_exit=0,probe_expected_stdout='F367R6_STATIC_EXEC_PASS invalid_argument_exit=1',invalid_argument_before_state_and_socket=True,hardware_actions=False,physical_probe='PENDING_ROOT_AFTER_F365_RETURN')
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(result=str(out/'result.json'),**report),indent=2))
if __name__=='__main__':main()
