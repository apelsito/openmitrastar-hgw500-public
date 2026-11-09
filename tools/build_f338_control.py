"""Build a bounded trivial ARC userspace control, without running on a router."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,shlex
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=Path.home()/('.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f338-control-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
 source=ROOT/'work/kernel-port/f338/userspace/f338_control.c';(out/'control.c').write_bytes(source.read_bytes())
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');q=shlex.quote
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
for lane in a b; do
 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=c11 -Os -g0 -mno-atomic -fno-stack-protector -static -Wl,--build-id=none "$out/control.c" -o "$out/f338-control-$lane"
 "${{tc}}objdump" -d "$out/f338-control-$lane" > "$out/disassembly-$lane.txt"
 ! grep -Eq '\\b(llock|scond|flag)\\b' "$out/disassembly-$lane.txt"
 "${{tc}}strip" --strip-unneeded "$out/f338-control-$lane"
done
cmp "$out/f338-control-a" "$out/f338-control-b"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True,timeout=60)
 (out/'stderr').write_bytes(p.stderr);binary=out/'f338-control-a'
 report={'status':'PASS_STATIC_BUILD_DEVICE_EXEC_UNRUN' if not p.returncode else 'FAIL','file':str(binary),'bytes':binary.stat().st_size if binary.exists() else None,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest() if binary.exists() else None,'arguments':[],'wall_limit_seconds':3,'cpu_hard_limit_seconds':2,'device_execution':False,'hardware':False}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**report},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
