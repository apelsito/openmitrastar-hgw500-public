"""Versioned no-libc ARC signal probe, no host access to keys or device."""
from pathlib import Path
import subprocess,hashlib,re,json
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OUT=BASE/'dropbear73-signal-probe-qualified-v3-exitkill'
TC=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
SOURCE=Path('/workspace/user-home/Desktop/MitraStar/work/kernel-port/dropbear73-signal-probe-v1/probe.c')
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 OUT.mkdir(mode=0o700);binary=OUT/'probe'
 with (OUT/'build.log').open('xb') as log:subprocess.run([TC+'gcc','-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-nostdlib','-nostartfiles','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-Os','-Wall','-Wextra','-Werror','-Wl,-e,_start','-Wl,--build-id=none','-o',str(binary),str(SOURCE)],stdout=log,stderr=subprocess.STDOUT,check=True)
 asm=subprocess.check_output([TC+'objdump','-d',str(binary)],text=True)
 assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
 assert not subprocess.check_output([TC+'nm','-u',str(binary)],text=True).strip()
 result={'status':'PASS_FREESTANDING_SIGNAL_PROBE_OFFLINE','bytes':binary.stat().st_size,'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'physical':'UNRUN','key_access':False,'registers':'PC,return-PC,branch-target,status,EFA; no memory dump'}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
