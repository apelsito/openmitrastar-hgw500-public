"""Inventory physical and logical HGW storage; never reads protected payloads."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
KNOWN=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f367r9-f365-transition-observation-device-bound/known_hosts.f367'
SCRIPT=r'''set -eu
echo STORAGE_BEGIN
printf 'boot=';cat /proc/sys/kernel/random/boot_id
printf 'version=';sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'kernel=';uname -r
printf 'build=';uname -v
echo MTD_BEGIN
cat /proc/mtd
for p in /sys/class/mtd/mtd[0-9];do
 [ -d "$p" ] || continue
 printf '%s.name=' "${p##*/}";cat "$p/name"
 for key in size erasesize flags type offset;do
  [ -r "$p/$key" ] || continue
  printf '%s.%s=' "${p##*/}" "$key";cat "$p/$key"
 done
done
echo MTD_END
echo MEMORY_BEGIN
awk '/MemTotal|MemFree|MemAvailable|Buffers|Cached|Shmem|SwapTotal|SwapFree/ {print}' /proc/meminfo
echo MEMORY_END
echo MOUNTS_BEGIN
cat /proc/mounts | awk '$2=="/"||$2=="/run"||$2=="/tmp"||$2=="/persist"||$2=="/www"||$2=="/usr/sbin/om-ledctl"||$2=="/run/openmitrastar/doom-20261022-r1/files"{print}'
echo MOUNTS_END
echo BLOCK_BEGIN
cat /proc/partitions
for p in /sys/block/*;do
 [ -d "$p" ] || continue
 case "${p##*/}" in loop*|ram*|mtdblock*) continue;;esac
 printf 'block=%s sectors=' "${p##*/}";cat "$p/size"
done
echo BLOCK_END
echo DT_FLASH_BEGIN
for p in /proc/device-tree/soc/flash@* /proc/device-tree/soc/nand@* /proc/device-tree/soc/mmc@*;do
 [ -d "$p" ] || continue
 printf 'node=%s\n' "${p##*/}"
 [ ! -r "$p/reg" ] || { printf 'reg_sha256=';sha256sum "$p/reg" | awk '{print $1}'; }
done
echo DT_FLASH_END
echo STORAGE_END
'''
def main():
    out=ROOT/'outputs/storage'/('hgw-readonly-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(parents=True,exist_ok=False)
    args=[str(Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'),'-i',str(Path.home()/'.ssh/id_ed25519'),'-b','192.168.1.49',
      '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',
      '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(KNOWN),'-o','LogLevel=ERROR','root@192.168.1.90','sh -s']
    known=hashlib.sha256(KNOWN.read_bytes()).hexdigest()
    proc=subprocess.run(args,input=SCRIPT.encode('ascii'),capture_output=True,timeout=25)
    (out/'stdout.txt').write_bytes(proc.stdout);(out/'stderr.txt').write_bytes(proc.stderr)
    result={'status':'READONLY_COMPLETE' if proc.returncode==0 else 'READONLY_FAILED','exit_code':proc.returncode,'protected_payload_read':False,'hardware_mutated':False,'known_hosts_unchanged':hashlib.sha256(KNOWN.read_bytes()).hexdigest()==known}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps({'directory':str(out),**result}));print(proc.stdout.decode('utf-8','replace'));print(proc.stderr.decode('utf-8','replace'))
    return proc.returncode
if __name__=='__main__':raise SystemExit(main())
