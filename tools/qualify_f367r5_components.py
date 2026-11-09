"""Qualify completed R5 bytes without rerunning compilation or prior banks."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):p=Path(p);return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--completed',type=Path,required=True);a=ap.parse_args()
 result=json.loads(a.completed.read_text())
 assert result['schema'] in ('openmitrastar.f367r5-profile-component/v1','openmitrastar.f367r5-regulatory-component/v1')
 assert result['status'] in ('PASS_F367R4_ACK_BUILD_LINK_AND_REPRODUCTION','PASS_F367R5_REGULATORY_BUILD_LINK_AND_REPRODUCTION')
 assert result['reproducible'] and result['kernel_recompiled'] is False and result['f355_lifetime_preserved']
 assert len(result['modules'])==41
 for name,record in result['artifacts'].items():assert sha(record['path'])==record['sha256']
 for label in ('qdrv.ko','qtn_radar_f367.ko','om-f367-dfs-profile'):assert sha(a.completed.parent/'a'/label)==sha(a.completed.parent/'b'/label)
 source=Path(result['source_manifest']['path']).parent
 for name,digest in result['source_pins'].items():assert sha(source/name)==digest
 for path,digest in {**result['userspace_pins'],**result['producer_and_layout_pins']}.items():assert sha(path)==digest
 binary=Path(result['artifacts']['profile']['path'])
 with binary.open('rb') as stream:
  elf=ELFFile(stream);interpreter=[s.get_interp_name() for s in elf.iter_segments() if s.header.p_type=='PT_INTERP'];needed=[t.needed for t in elf.get_section_by_name('.dynamic').iter_tags() if t.entry.d_tag=='DT_NEEDED']
  assert elf.elfclass==32 and elf.little_endian and interpreter==['/lib/ld-uClibc.so.0'] and needed==['libc.so.0']
  machine=elf.header.e_machine
 route=Path(result['regulatory_test']['path']);proof=json.loads(route.read_text());assert sha(route)==result['regulatory_test']['sha256'] and proof['status']=='PASS_ACTUAL_OEM_REGULATORY_SYSFS_ROUTE'
 assert len(proof['helper_route'])==3 and all(x['passed'] for x in proof['helper_route'])
 result.update(schema='openmitrastar.f367r5-regulatory-component/v1',status='PASS_F367R5_REGULATORY_BUILD_LINK_AND_REPRODUCTION',completed_build_evidence=item(a.completed),qualification_source=item(__file__),qualification_without_rebuild=True,profile_abi=dict(machine=machine,elf_class=32,little_endian=True,interpreter=interpreter[0],needed=needed,channel_entry_bytes=7,channel_table_bytes=1792,arc_iwreq_bytes=32,arc_iw_point_length_offset=20,arc_iw_point_flags_offset=22))
 out=ROOT/'outputs/kernel-port'/('f367r5-qualified-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(result=str(out/'result.json'),status=result['status'],artifacts=result['artifacts'],profile_abi=result['profile_abi']),indent=2))
if __name__=='__main__':main()
