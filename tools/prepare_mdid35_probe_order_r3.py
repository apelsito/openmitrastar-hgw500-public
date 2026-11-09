"""New MDID35 revision: preserve exact OEM PROBE_RESP RRM/MDIE/Ath order."""
import argparse,difflib,hashlib,json,shutil
from collections import Counter
from pathlib import Path
from catalog_hgw_firmware_comments import scan_comments

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--prior',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--oem',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 evidence=(a.oem/'ieee80211_send_mgmt.objdump.txt').read_text()
 offsets={name:evidence.index(off+': R_ARC_32_ME\t'+name)for off,name in [('10d8a','ieee80211_add_rrm_enabled'),('10dae','ieee80211_add_mdie'),('10dd6','ieee80211_add_athAdvCap')]}
 assert offsets['ieee80211_add_rrm_enabled']<offsets['ieee80211_add_mdie']<offsets['ieee80211_add_athAdvCap']
 a.output.mkdir(parents=True);shutil.copytree(a.prior/'source',a.output/'source');shutil.copytree(a.prior/'headers',a.output/'headers')
 out=a.output/'source/wlan/ieee80211_output.c';text=out.read_text();start=text.index('case IEEE80211_FC0_SUBTYPE_PROBE_RESP:');end=text.index('case IEEE80211_FC0_SUBTYPE_AUTH:',start);part=text[start:end]
 rrm='\t\tif(ic->om_neighbor_report_flags & 1U)\n\t\t\tfrm = om_neighbor_rrm_ie(frm,ic->om_neighbor_report_flags);\n\n'
 md='\t\tif(READ_ONCE(vap->om_mdid))'
 assert part.count(rrm)==1 and part.index(md)<part.index('/* AthAdvCaps */')<part.index(rrm)
 part=part.replace(rrm,'',1).replace(md,rrm+md,1)
 assert part.index('om_neighbor_rrm_ie')<part.index('om_mdie_write')<part.index('ieee80211_add_athAdvCap')
 out.write_text(text[:start]+part+text[end:],newline='\n')
 for tree in ['source','headers']:
  for before in (a.prior/tree).rglob('*'):
   if before.is_file():
    after=a.output/before.relative_to(a.prior)
    if before.name!='ieee80211_output.c':assert before.read_bytes()==after.read_bytes()
    c=lambda raw:Counter(raw[x['offset']:x['end_offset']]for x in scan_comments(raw));assert not c(before.read_bytes())-c(after.read_bytes())
 changes={};patch=[]
 for tree in ['source','headers']:
  for before in(a.parent/tree).rglob('*'):
   if before.is_file():
    after=a.output/before.relative_to(a.parent)
    if before.read_bytes()!=after.read_bytes():
     rel=str(before.relative_to(a.parent));changes[rel]=sha(after);patch.extend(difflib.unified_diff(before.read_text().splitlines(True),after.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 (a.output/'mdid-ft-recovery.patch').write_text(''.join(patch))
 r=json.loads((a.prior/'result.json').read_text());r.update(revision='r3',prior=str(a.prior),changed_sources=changes,files={str(x.relative_to(a.output)):sha(x)for tree in['source','headers']for x in(a.output/tree).rglob('*')if x.is_file()},oem_probe_order=['RRM','MDIE','AthAdvCaps'],prior_probe_order_rejected=True)
 r['limits'].append('r2probeorderingnotOEM; r3onlymovespreviousRRMblockbeforeMDIE. Oldr2buildretainedandnotqualified35.')
 r['revision_pins']={str(x):sha(x)for x in[Path(__file__),a.prior/'result.json',a.oem/'ieee80211_send_mgmt.objdump.txt']}
 (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'result_sha256':sha(a.output/'result.json'),'output_sha256':sha(out)},indent=2))
if __name__=='__main__':main()
