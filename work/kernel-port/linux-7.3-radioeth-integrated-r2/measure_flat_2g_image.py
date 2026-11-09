"""Offline whole-image compression estimate from a pinned kernel and exact root."""
from pathlib import Path
import gzip,json,lzma,struct,subprocess,hashlib,os
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
R2=BASE/'radioeth73-integrated-r2-revision3-20261022T2251Z'
OUT=BASE/'radio73-flat-2g-size-v1'
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 os.umask(0o077);OUT.mkdir(mode=0o700)
 root=BASE/'radio73-2g-doom-fit-v1/root'
 import importlib.util
 helperpath=Path('/workspace/user-home/Desktop/MitraStar/work/kernel-port/linux-7.3-radioeth-integrated-r2/build_integrated_r2.py')
 spec=importlib.util.spec_from_file_location('builder',helperpath);b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
 b.normalize_times(root);b.write_cpio_list(root,OUT/'list')
 subprocess.run([str(R2/'a/usr/gen_init_cpio'),'-t','1792365298',str(OUT/'list')],stdout=(OUT/'root.cpio').open('xb'),check=True)
 elf=(R2/'a/vmlinux').read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',elf)
 sections=[struct.unpack_from('<10I',elf,h[6]+i*40) for i in range(h[12])]
 ns=sections[h[13]];names=elf[ns[4]:ns[4]+ns[5]]
 flat=bytearray((R2/'kernel-a.raw').read_bytes())
 ramfs=next(s for s in sections if names[s[0]:names.find(b'\0',s[0])]==b'.init.ramfs')
 offset=ramfs[3]-0x8493a000
 cpio=(OUT/'root.cpio').read_bytes()
 synthetic=bytes(flat[:offset])+cpio+bytes(flat[offset+ramfs[5]:])
 # Entry addresses are now wrong in this byte estimate. Never emit it as firmware.
 rows=[]
 for name,data in [('flat-none-cpio',synthetic),('gzip-cpio',bytes(flat[:offset])+gzip.compress(cpio,mtime=1792365298)+bytes(flat[offset+ramfs[5]:]))]:
  compressed=lzma.compress(data,format=lzma.FORMAT_ALONE,preset=9|lzma.PRESET_EXTREME)
  rows.append({'mode':name,'synthetic_raw_bytes':len(data),'whole_LZMA_RAS_estimate_bytes':8192+len(compressed),'fits_prefix':8192+len(compressed)<=0x5e0000,'overflow':max(0,8192+len(compressed)-0x5e0000)})
 result={'status':'CAPACITY_ONLY_SYNTHETIC_BYTES_NEVER_BOOTABLE','rows':rows,'cpio_bytes':len(cpio),'hardware_accessed':False}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
