"""Build the ROM-only F342 consumer; no hardware or controller commands."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/versions/f361-config-integration/source'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 out=ROOT/'outputs/userspace'/('f361-journal-reader-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);shutil.copytree(SOURCE,out/'source')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
flags='-std=c11 -Os -g0 -Wall -Wextra -Werror -ffunction-sections -fdata-sections'
cc $flags -DF361_TEST -I"$out/source" "$out/source/f361_journal_ro.c" "$out/source/f342_journal.c" -Wl,--gc-sections -o "$out/reader-native"
for lane in a b; do
 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot $flags -mno-atomic -fno-stack-protector -static -I"$out/source" "$out/source/f361_journal_ro.c" "$out/source/f342_journal.c" -Wl,--gc-sections -o "$out/om-journal-ro-$lane"
 "${{tc}}strip" --strip-unneeded "$out/om-journal-ro-$lane"
done
cmp "$out/om-journal-ro-a" "$out/om-journal-ro-b"
"${{tc}}readelf" -h -l "$out/om-journal-ro-a" > "$out/elf.txt"
'''
 (out/'build.sh').write_bytes(script.encode());r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True);(out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
 result={'schema':'openmitrastar.f361-rom-reader-build/v1','status':'PASS_OFFLINE_ROM_READER_BUILD' if not r.returncode else 'FAIL','hardware_actions':False,'controller_commands':False,'mtd_access':'read-only snapshot of lyoko_store, MEMGETINFO metadata only','core_sha256':sha(SOURCE/'f342_journal.c'),'sources':{str(p):sha(p) for p in SOURCE.rglob('*') if p.is_file()}}
 if not r.returncode:
  binary=out/'om-journal-ro-a';result.update(artifact={'path':str(binary),'bytes':binary.stat().st_size,'sha256':sha(binary)},reproducible=True,native_test_binary=str(out/'reader-native'))
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'artifact':result.get('artifact'),'error':r.stderr.decode(errors='replace')[-1500:]}));return r.returncode
if __name__=='__main__':raise SystemExit(main())
