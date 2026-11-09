"""Run the exact kernel IPC C with a POSIX syscall shim and protocol vectors."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f341'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=ROOT/'outputs/preflight'/('f341-ipc-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 for sub in ('kernel','uapi','tests'):
  (out/sub).mkdir()
  for p in (SOURCE/sub).iterdir():
   if p.is_file():(out/sub/p.name).write_bytes(p.read_bytes())
 source=(SOURCE/'kernel/f338_ipc.c').read_text();projected=re.sub(r'^#include <linux/[^\n]+\n','',source,flags=re.M)
 (out/'tests/ipc-under-test.c').write_text('#include "ipc_kernel_shim.h"\n'+projected)
 (out/'tests/service-under-test.c').write_bytes((SOURCE/'userspace/f338_service.c').read_bytes())
 (out/'tests/f338_service_core.h').write_bytes((SOURCE/'userspace/f338_service_core.h').read_bytes())
 q=shlex.quote
 script=f'''set -eu
out={q(linux(out))}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -I"$out/kernel" -I"$out/uapi" "$out/kernel/f338_protocol.c" "$out/tests/test_protocol.c" -o "$out/protocol"
"$out/protocol" > "$out/protocol.txt"
cc -std=gnu11 -O1 -g -Wall -Wextra -Werror -Wno-sign-compare -pthread -I"$out/kernel" -I"$out/uapi" "$out/kernel/f338_protocol.c" "$out/tests/test_ipc_actual.c" -o "$out/ipc-actual"
timeout 15s "$out/ipc-actual" > "$out/ipc.txt" 2> "$out/ipc.stderr"
cc -std=c11 -O0 -Wall -Wextra -Werror -fanalyzer -I"$out/kernel" -I"$out/uapi" -c "$out/kernel/f338_protocol.c" -o "$out/protocol-analysis.o"
cc -std=c11 -O2 -Wall -Wextra -Werror -I"$out/uapi" "$out/tests/test_service_transport.c" -o "$out/service-transport"
"$out/service-transport" > "$out/service-transport.txt"
'''
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=45)
 (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
 result={'schema':'openmitrastar.f341-ipc-tests/v1','status':'PASS_ACTUAL_C_IPC_THREADS' if not p.returncode else 'FAIL','exit':p.returncode,'hardware':False,'source_sha256':sha(SOURCE/'kernel/f338_ipc.c'),'protocol_sha256':sha(SOURCE/'kernel/f338_protocol.c'),'service_sha256':sha(SOURCE/'userspace/f338_service.c'),'sanitizers':'UNAVAILABLE_IN_PINNED_HOST_ENVIRONMENT','evidence':{n:(out/n).read_text() for n in ('protocol.txt','ipc.txt','ipc.stderr','service-transport.txt') if (out/n).exists()}}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result,'stderr':p.stderr.decode(errors='replace')[-3000:]},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
