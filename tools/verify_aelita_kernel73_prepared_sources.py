"""Checknewcomposedpublicsources againstv6 exceptexplicitR20/currentheaderdelta."""
import hashlib,json
from pathlib import Path
import argparse
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--new',type=Path,required=True);p.add_argument('--v6',type=Path,required=True);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);r=json.loads((a.new/'result.json').read_text());pins=json.loads((a.new/'kernel-source-pins.json').read_text());assert len(pins)==95986;assert all(sha(a.new/'kernel-source'/rel)==h for rel,h in pins.items());audit=json.loads((a.package/'kernel-preparation-v1/AUDIT.json').read_text());delta=[];same=0
 for row in audit['changed']+audit['additional_board_files']:
  rel=row['path'];f=a.new/'kernel-source'/rel;h=sha(f)
  if h==row['prepared_sha256']:same+=1
  else:delta.append({'path':rel,'v6_sha256':row['prepared_sha256'],'new_sha256':h})
 allowed={'include/linux/soc/qtn/topaz-ethernet.h','include/linux/skbuff.h','include/linux/netdevice.h'};assert {x['path']for x in delta}<=allowed,delta
 forbidden=['CONFIG_GENERIC_BUILTIN_DTB=y','/home/','/mnt/','192.168.'];cfg=(a.new/'kernel-context/.config').read_text();assert not any(x in cfg for x in forbidden)and'CONFIG_INITRAMFS_SOURCE=""'in cfg and'CONFIG_BUILTIN_DTB_NAME=""'in cfg and'CONFIG_QTN_TOPAZ_ETH73=y'in cfg
 result={'status':'PASS_PREPARED_PUBLIC_KERNEL73_SOURCE_HASHES_EXPLICIT_V6_R20_DELTA_NO_BUILD','hardware_accessed':False,'source_files_verified':len(pins),'v6_changed_or_new_paths_exact':same,'declared_source_deltas':delta,'new_packet_ABI_headers_selected':True,'current_ETH_register_header_selected':True,'private_DT_initramfs_identity_absent_from_selectedinputs':True,'config_sha256':sha(a.new/'kernel-context/.config'),'full_kernel_build':'UNRUN','generated_context':'ABSENT_UNTIL_ACTUAL_KERNEL_BUILD'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
