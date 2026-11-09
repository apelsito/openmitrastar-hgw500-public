"""Narrow platform provider header dependency without changing tables or IO arithmetic."""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--prior',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);before=a.prior/'providers/qtn_platform_support.c';t=before.read_text();anchor='#include <qtn/qdrv_sch.h>';assert t.count(anchor)==1;replace='''/* Shared scheduler table ABI only; avoid importing packet/MMIO inline helpers. */
#include <qtn/qtn_wmm_ac.h>
#include <qtn/qtn_uc_comm.h>
#define QDRV_BAND_AC_BE WMM_AC_BE
#define QDRV_BAND_AC_BK WMM_AC_BK
#define QDRV_BAND_AC_VI WMM_AC_VI
#define QDRV_BAND_AC_VO WMM_AC_VO
#define IP_DSCP_MAPPING_SIZE 32
#define VLANID_INDEX_INITVAL 4096
''';t=t.replace(anchor,replace,1);f=a.output/'providers/qtn_platform_support.c';f.parent.mkdir();f.write_text(t,newline='\n');pinned=[Path(__file__),before,ROOT/'work/sources/Quantenna-GPL/include/qtn/qdrv_sch.h',ROOT/'work/sources/Quantenna-GPL/include/qtn/qtn_uc_comm.h',ROOT/'work/sources/Quantenna-GPL/include/qtn/qtn_wmm_ac.h',ROOT/'work/sources/Quantenna-GPL/drivers/include/shared/net80211/ieee80211.h',ROOT/'work/sources/Quantenna-GPL/drivers/include/shared/qdrv_sch_const.h'];texts=[p.read_text()for p in pinned[2:]];assert '#define IP_DSCP_NUM\t\t\t\t64'in texts[3]and '#define QTN_MAX_BSS_VAPS\t\t8'in texts[1];assert all('#define WMM_AC_'+name+'\t'+str(i)in texts[2]for i,name in enumerate(['BE','BK','VI','VO']));assert '#define VLANID_INDEX_INITVAL\t4096'in texts[0];(a.output/'narrow-platform.patch').write_text(''.join(difflib.unified_diff(before.read_text().splitlines(True),t.splitlines(True),fromfile='a/providers/qtn_platform_support.c',tofile='b/providers/qtn_platform_support.c')));r={'status':'SOURCE_ONLY_LINUX73_NARROW_PLATFORM_HEADER_PENDING_ARC_COMPILE','hardware_accessed':False,'firmware_eligible':False,'file_sha256':sha(f),'pins':{str(p):sha(p)for p in pinned},'table_bytes_and_values_unchanged':True,'limits':'Headerdependencyonly; qdrv_schMMIOinlinesexcluded. Alltableexports/DTDMA/bodyunchanged, nohardwareexecution.'};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
