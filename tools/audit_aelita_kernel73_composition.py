"""Read preparedv6source against pristinearchive; copy only publicboard deltas."""
import argparse,hashlib,json,tarfile
from pathlib import Path
def digest(raw):return hashlib.sha256(raw).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--context',type=Path,required=True);p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 assert digest(a.archive.read_bytes())=='87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953'
 driver=a.repo/'src/linux-7.3-r18';dr=json.loads((driver/'result.json').read_text());qoverlay={k.replace('\\','/').removeprefix('kernel-overlay/'):v for k,v in dr['files'].items()if k.replace('\\','/').startswith('kernel-overlay/')}
 realtek=Path('/workspace/user-home/Desktop/MitraStar/outputs/rea/movistar-port-20261022T1327175411798Z/realtek-repo/kernel/radio2g-linux-7.3-v1');basic=Path('/workspace/user-home/Desktop/MitraStar/work/kernel-port/linux-7.3-basic');baseoverlay={p.relative_to(basic/'overlay').as_posix():digest(p.read_bytes())for p in(basic/'overlay').rglob('*')if p.is_file()and p.suffix not in('.dts','.dtb')};rtoverlay={p.relative_to(realtek/'overlay').as_posix():digest(p.read_bytes())for p in(realtek/'overlay').rglob('*')if p.is_file()and p.suffix not in('.dts','.dtb')};emac=a.repo/'components/ethernet-linux73';ethoverlay={p.relative_to(emac/'board-overlay').as_posix():digest(p.read_bytes())for p in(emac/'board-overlay').rglob('*')if p.is_file()};expected=baseoverlay|rtoverlay|ethoverlay|qoverlay
 checked=0;matches=0;changed=[];excluded=[];known_upstream=set();public={}
 def safe(rel):
  if Path(rel).suffix in('.dts','.dtb','.pem','.key','.crt','.bin','.ko','.o'):return False
  return not any(x in rel.lower()for x in('initramfs','hostapd','authorized_keys','calibration','/firmware/'))
 with tarfile.open(a.archive)as tar:
  for member in tar:
   rel=member.name.split('/',1)[1]if '/'in member.name else''
   if not rel or not member.isfile():continue
   known_upstream.add(rel)
   if not safe(rel):excluded.append(rel);continue
   path=a.prepared/rel
   if not path.is_file():continue
   raw=tar.extractfile(member).read();old=digest(raw);current=digest(path.read_bytes());checked+=1
   if old==current:matches+=1;continue
   row={'path':rel,'upstream_sha256':old,'prepared_sha256':current,'expected_overlay_sha256':expected.get(rel),'matches_selected_overlay':expected.get(rel)==current};changed.append(row)
   if rel not in qoverlay and not rel.startswith('drivers/net/wireless/realtek/'):
    data=path.read_bytes();assert b'-----BEGIN PRIVATE KEY'not in data;public[rel]=data
 extras=[]
 scopes=('arch/arc','drivers/irqchip','drivers/pci/controller','include/linux/soc/qtn')
 for scope in scopes:
  for path in(a.prepared/scope).rglob('*'):
   if not path.is_file():continue
   rel=path.relative_to(a.prepared).as_posix()
   if rel in known_upstream or not safe(rel):continue
   raw=path.read_bytes();extras.append({'path':rel,'prepared_sha256':digest(raw),'expected_overlay_sha256':expected.get(rel),'matches_selected_overlay':expected.get(rel)==digest(raw)});public[rel]=raw
 for rel,raw in public.items():dst=a.output/'board-overlay'/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
 cfg=(a.context/'.config').read_text();private_removed=[]
 for key in('CONFIG_INITRAMFS_SOURCE','CONFIG_SYSTEM_TRUSTED_KEYS','CONFIG_SYSTEM_REVOCATION_KEYS','CONFIG_MODULE_SIG_KEY'):
  import re
  match=re.search(r'^'+key+r'=(.*)$',cfg,re.M)
  if match:cfg=re.sub(r'^'+key+r'=.*$',key+'=""',cfg,flags=re.M);private_removed.append(key)
 cfg=cfg.replace('CONFIG_LOCALVERSION="-openmitrastar-radio73-v1"','CONFIG_LOCALVERSION="-openmitrastar-aelita73"')
 assert 'CONFIG_QTN_TOPAZ_ETH73=y'in cfg and 'CONFIG_INITRAMFS_SOURCE=""'in cfg
 assert not any(x in cfg for x in('/home/','/mnt/','C:\\','192.168.'))
 (a.output/'config.sanitized').write_text(cfg)
 report={'schema':'openmitrastar.aelita-kernel73-preparation-audit/v1','status':'PREPARED_V6_PUBLIC_SOURCE_DELTAS_CAPTURED_NO_BUILD','hardware_accessed':False,'prepared_kernel_source':str(a.prepared),'context_config_sha256':digest((a.context/'.config').read_bytes()),'upstream_commit':'c03c1a14507dfaf8b856c2608f9ac216021fc222','upstream_archive_sha256':'87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953','upstream_regular_source_files_checked':checked,'upstream_regular_files_unchanged':matches,'changed':changed,'additional_board_files':extras,'copied_public_board_files':{rel:digest(raw)for rel,raw in public.items()},'selected_overlays_missing_expected_match':[row for row in changed+extras if not row['matches_selected_overlay']],'config_sanitized_sha256':digest(cfg.encode()),'config_private_path_options_cleared':private_removed,'excluded_DT_private_or_binary_paths_count':len(excluded),'full_regular_source_equivalence_except_declared':checked==matches+len(changed),'private_files_copied':False,'kernel_compiled_modified':False};(a.output/'AUDIT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in('changed','additional_board_files','copied_public_board_files','selected_overlays_missing_expected_match')}));print(json.dumps({'changed':len(changed),'new_board':len(extras),'copied_board':len(public),'unmatched_overlay_paths':[r['path']for r in report['selected_overlays_missing_expected_match']]}))
if __name__=='__main__':main()
