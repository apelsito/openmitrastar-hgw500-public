"""Revise SOURCE neighbor prototype to refuse missing20B descriptor admission.

The fixed1000-byte MuC descriptor arena is never enlarged. RRM insertion is
admitted before any write only when one exactdescriptor fits; on refusal the
frame/arena/pointer remain unchanged and caller explicitly records noRRM pointer.
Fullfeatureentrypromotion stillrequires worst-case/integration modulechecks.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();proof=json.loads((a.parent/'result.json').read_text());assert proof['total_original_entries_added']==19
 a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
 src=a.output/'source/wlan';desc=src/'ieee80211_beacon_desc.c';text=desc.read_text();marker='\tcase 70:\n\t\tfrm = om_neighbor_rrm_ie(frm,ic->om_neighbor_report_flags);\n\t\tbreak;'
 assert text.count(marker)==1
 replacement='''\tcase 70:
\t\t/* Exactone20Bdescriptor admission before writingRRM7B payload.
\t\t * NevergrowtheMuCfixedarena orpublishuntrackedpayload bytes. */
\t\tif (param->curr < (u32)(unsigned long)param->buf ||
\t\t    param->curr - (u32)(unsigned long)param->buf > param->size ||
\t\t    param->size - (param->curr - (u32)(unsigned long)param->buf) <
\t\t        sizeof(struct beacon_shared_ie_t))
\t\t\treturn pre_frm;
\t\tfrm = om_neighbor_rrm_ie(frm,ic->om_neighbor_report_flags);
\t\tbreak;'''
 desc.write_text(text.replace(marker,replacement,1),newline='\n')
 beacon=src/'ieee80211_beacon.c';text=beacon.read_text();marker='\tbo->bo_om_rrm = frm;\n\tfrm = ieee80211_add_beacon_desc_ie(ni, 70, frm);';assert text.count(marker)==1
 replacement='''\tbo->bo_om_rrm = frm;
\tfrm = ieee80211_add_beacon_desc_ie(ni, 70, frm);
\tif (frm == bo->bo_om_rrm)
\t\tbo->bo_om_rrm = NULL; /* admissionrefused:noadvertisementpointer */'''
 beacon.write_text(text.replace(marker,replacement,1),newline='\n')
 patches=[]
 # Complete patch includes previous493->current492 Cdelta and all newly
 # addedhostheaders/helper, so a standalone patch doesnot omit its ABIcontext.
 root=Path(__file__).resolve().parents[1]
 for name in proof['changed_sources']:
  baseline=root/'work/linux510-radio-port/quantenna/wlan'/name
  old=baseline.read_text() if baseline.exists() else ''
  new=(src/name).read_text()
  patches.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/src/wlan/'+name,tofile='b/src/wlan/'+name)))
 for header in(a.output/'headers/net80211').iterdir():
  baseline=root/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211'/header.name
  old=baseline.read_text();new=header.read_text()
  patches.append(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/vendor/port-context/drivers/include/kernel/net80211/'+header.name,tofile='b/vendor/port-context/drivers/include/kernel/net80211/'+header.name)))
 helper=src/'openmitrastar_bss_tm.h';patches.append(''.join(difflib.unified_diff([],helper.read_text().splitlines(True),fromfile='/dev/null',tofile='b/src/wlan/openmitrastar_bss_tm.h')))
 (a.output/'complete-neighbor-capability.patch').write_text(''.join(patches),newline='\n')
 result={**proof,'status':'SOURCE_ONLY_NEIGHBOR_DESCRIPTOR_ADMISSION_NO_GO_MODULE','parent_manifest_sha256':sha(a.parent/'result.json'),'changed_sources':{p.name:sha(p)for p in src.iterdir()if p.is_file()and p.name in proof['changed_sources']},'descriptor_arena_capacity_unchanged':True,'complete_patch_sha256':sha(a.output/'complete-neighbor-capability.patch'),'descriptor_failure_behavior':'NoRRMIEdescriptor/payload/pointer onrefusal; noframe/RF/featureacceptanceclaim','limits':proof['limits']+['Descriptoradmissionrefusalmustpropagatetoofflineandruntimeacceptance; rawtableentryaloneisnotcapabilityPASS.']}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
