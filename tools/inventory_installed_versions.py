"""Offline pinned F367r9 versions/file inventory. No router/network operations."""
import argparse,csv,hashlib,json,re,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--rootfs',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 expected='465c413d5f08c8a422e09dc1a942e4a7b89042fb684c80281ca776c4b419852e'
 assert sha(a.rootfs)==expected
 reference=json.loads(a.inventory.read_text())['after']; rows=[];versions=[]
 pattern=re.compile(rb'BusyBox v[^\x00\r\n]{1,95}|Dropbear[^\x00\r\n]{1,95}|SSH-2\.0-dropbear[^\x00\r\n]{1,95}|hostapd v[^\x00\r\n]{1,95}|hostapd_cli v[^\x00\r\n]{1,95}|mini_httpd/[^\x00\r\n]{1,95}|OpenSSL [0-9][^\x00\r\n]{1,95}|uClibc [0-9][^\x00\r\n]{1,60}|iw version[^\x00\r\n]{1,60}|version=[^\x00\r\n]{1,80}|vermagic=[^\x00\r\n]{1,100}|srcversion=[^\x00\r\n]{1,100}|qdrv version[^\x00\r\n]{1,100}|Quantenna[^\x00\r\n]{1,100}|QTN_VERSION[^\x00\r\n]{1,100}')
 with tempfile.TemporaryDirectory(prefix='openmitrastar-versions-') as td:
  root=Path(td)/'root';subprocess.run(['unsquashfs','-no-progress','-d',str(root),str(a.rootfs)],check=True,stdout=subprocess.DEVNULL)
  for name,entry in sorted(reference.items()):
   if entry['type'] not in ('file','symlink'):continue
   secret=name.startswith('etc/') or name.startswith('root/')
   row={'path':name,'type':entry['type'],'raw_bytes':entry.get('bytes',''),'sha256':None if secret else entry.get('sha256'),'symlink_target':entry.get('target',''),'storage':'F367r9 SquashFS / flash','included_in_flash_since':'2026-09-22 (campaign date; exact per-file first installation unknown)','version_strings':[]}
   if entry['type']=='file':
    data=(root/name).read_bytes();assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],name
    if data.startswith(b'\x7fELF') and not secret:
     row['version_strings']=sorted(set(v.decode('ascii','replace') for v in pattern.findall(data)))[:24]
     if name in ('usr/sbin/hostapd','usr/sbin/iw') or name.startswith('lib/firmware/'):
      strings=re.findall(rb'[ -~]{4,}',data)
      extra=[s.decode('ascii','replace') for s in strings if re.fullmatch(rb'[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:-devel)?',s) or re.search(rb'(?i)(?:build|firmware|release|version)[ _:]+.{0,20}[0-9]+[.][0-9]+|20[0-9][0-9][-_/][01][0-9][-_/][0-3][0-9]',s)]
      row['version_strings']+=sorted(set(extra))[:30]
     versions.append(row.copy())
   rows.append(row)
  release=(root/'etc/openmitrastar/release').read_text().strip()
 a.out.mkdir(parents=True,exist_ok=False)
 report={'schema':'openmitrastar.installed-reference-versions/v1','created_utc':datetime.now(timezone.utc).isoformat(),'hardware_actions':False,'source_rootfs_sha256':sha(a.rootfs),'source_inventory_sha256':sha(a.inventory),'script_sha256':sha(Path(__file__)),'release':release,'limitations':['Sealed F367r9 files verified against hash inventory; live RAM overlays are separate.','Embedded upstream dates are source/binary labels, not physical installation dates.','2026-09-22 denotes F367r9 campaign date; exact installation second and original first installation of unchanged individual files not established.','Protected configuration contents and hashes withheld.','Raw file bytes are not SquashFS physical allocation; do not sum compressed estimates.'],'files':rows,'elf_version_inventory':versions}
 (a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 with (a.out/'files.csv').open('w',newline='') as s:
  w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader()
  for row in rows:w.writerow({**row,'version_strings':' | '.join(row['version_strings'])})
 print(json.dumps({'out':str(a.out),'release':release,'files':len(rows),'elf_files':len(versions),'versioned':{x['path']:x['version_strings'] for x in versions if x['version_strings']}}))
if __name__=='__main__':main()
