"""Inspect completed static bytes and emit the invalid-argument target probe."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess
from elftools.elf.elffile import ELFFile
from build_f367r6_static_profile import ROOT,DST,QUAL,sha,item,linux
def main():
 p=argparse.ArgumentParser();p.add_argument('--completed',type=Path,required=True);a=p.parse_args()
 completed=a.completed.resolve();binary=completed/'om-f367-dfs-profile-a'
 assert sha(binary)==sha(completed/'om-f367-dfs-profile-b')
 previous=json.loads(QUAL.read_text())
 for path,digest in previous['userspace_pins'].items():
  assert sha(path)==digest and sha(DST/Path(path).name)==digest and sha(completed/'source'/Path(path).name)==digest
 with binary.open('rb') as stream:
  elf=ELFFile(stream);assert elf.header.e_machine=='EM_ARC_COMPACT' and elf.elfclass==32 and elf.little_endian and elf.header.e_flags==0x403
  assert not any(p.header.p_type in ('PT_INTERP','PT_DYNAMIC') for p in elf.iter_segments())
  assert elf.get_section_by_name('.dynamic') is None and elf.get_section_by_name('.interp') is None
 assert not re.search(r'\b(?:llock|scond)\b',(completed/'disassembly.txt').read_text())
 source=(DST/'om-f367-dfs-profile.c').read_text();assert source.index('if(argc!=2||')<source.index('if(geteuid()!=0)')<source.index('if(state(json')<source.index('fd=socket(')
 compiler=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-gcc')
 cmd=['wsl.exe','-d','podman-mem9-tidb','-u','root','-e']
 archive=subprocess.run(cmd+[compiler,'--sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot','-static','-print-file-name=libc.a'],capture_output=True,text=True,check=True).stdout.strip()
 assert archive.startswith('/home/user/openmitrastar-uclibc-noatomic-sysroot/')
 libc=subprocess.run(cmd+['sha256sum',archive],capture_output=True,text=True,check=True).stdout.strip()
 out=ROOT/'outputs/kernel-port'/('f367r6-static-qualified-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 probe='''#!/bin/ash
set +x
set -u
[ "$#" = 1 ] || exit 64
binary=$1
[ -f "$binary" ] || exit 65
actual=$(sha256sum "$binary" 2>/dev/null | awk '{print $1}')
[ "$actual" = "'''+sha(binary)+'''" ] || exit 66
# Rejected by the first branch of main, before state/geteuid/socket paths.
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
 report=dict(schema='openmitrastar.f367r6-static-profile/v1',status='PASS_OFFLINE_F367R6_STATIC_PROFILE',artifact=item(binary),runtime_path='/usr/sbin/om-f367-dfs-profile',reproducible=True,source_logic_unchanged=True,reused_r5_components=item(QUAL),reused_regulatory_tests=previous['regulatory_test'],source_pins={str(p):sha(p) for p in DST.iterdir()},builder=item(ROOT/'tools/build_f367r6_static_profile.py'),qualification=item(__file__),static_link=True,pt_interp=False,pt_dynamic=False,dt_needed=[],machine='EM_ARC_COMPACT',elf_class=32,little_endian=True,elf_flags='0x403 ARC700 v4 ABI',atomic_policy=dict(compiler_flag='-mno-atomic',sysroot='/home/user/openmitrastar-uclibc-noatomic-sysroot',llock_instructions=0,scond_instructions=0,static_libc=libc),probe=item(out/'probe-invalid-argument.sh'),probe_argument='__F367R6_INVALID_ARGUMENT_PROBE__',probe_expected_exit=0,probe_expected_stdout='F367R6_STATIC_EXEC_PASS invalid_argument_exit=1',invalid_argument_before_state_and_socket=True,completed_build_directory=str(completed),completed_build_script=item(completed/'build.sh'),hardware_actions=False,physical_probe='PENDING_ROOT_AFTER_F365_RETURN',qualification_note='Compiler/link/cmp completed; build script final libc hash used wrong lib path. This qualification resolves libc through the compiler without rebuilding any bytes.')
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),**report),indent=2))
if __name__=='__main__':main()
