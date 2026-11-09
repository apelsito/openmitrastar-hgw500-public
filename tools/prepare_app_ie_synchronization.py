"""Create R11 complete APP pointer/length synchronization source, offline only.

No old candidate mutation. Allocations happen outside ic_comlock; every direct
APP reader either already holds that lock or uses bounded copy while locked.
Wire ABI and APP limit unchanged; output reserves the existing1024byte maximum.
"""
import argparse
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from catalog_hgw_firmware_comments import scan_comments
from prepare_hgw5g_beacon_descriptor_lifetime import function

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

COPY=r'''
/* Copy APP bytes while holding the same lock as pointer/length replacement.
 * The caller owns the destination and reserves IEEE80211_APPIE_MAX bytes. */
static unsigned int om_app_ie_copy(struct ieee80211vap *vap,
        unsigned int frame_type, uint8_t *destination)
{
    struct ieee80211com *ic = vap->iv_ic;
    unsigned int length = 0;
    IEEE80211_LOCK_BH(ic);
    if (vap->app_ie[frame_type].ie &&
        vap->app_ie[frame_type].length <= IEEE80211_APPIE_MAX) {
        length = vap->app_ie[frame_type].length;
        memcpy(destination, vap->app_ie[frame_type].ie, length);
    }
    IEEE80211_UNLOCK_BH(ic);
    return length;
}
'''

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--parent',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
 touched={}
 wireless=a.output/'source/wlan/ieee80211_wireless.c';old=wireless.read_text();touched[wireless]=old;new=old
 oldswap='\tif (vap->app_ie[frame_type_index].ie != NULL)\n\t\tFREE(vap->app_ie[frame_type_index].ie, M_DEVBUF);\n\tvap->app_ie[frame_type_index].ie = ie;\n\tvap->app_ie[frame_type_index].length = iebuf->app_buflen;'
 newswap='''\t{
\t\tstruct ieee80211_ie *old_ie;
\t\tstruct ieee80211com *ic = vap->iv_ic;
\t\tIEEE80211_LOCK_BH(ic);
\t\told_ie = vap->app_ie[frame_type_index].ie;
\t\tvap->app_ie[frame_type_index].ie = ie;
\t\tvap->app_ie[frame_type_index].length = iebuf->app_buflen;
\t\tIEEE80211_UNLOCK_BH(ic);
\t\tif (old_ie)
\t\t\tFREE(old_ie, M_DEVBUF);
\t}'''
 assert new.count(oldswap)==1;new=new.replace(oldswap,newswap,1)
 s,e,body=function(new,'static int\nremove_app_ie(');original=body
 start=body.index('\tif (app_ie->ie != NULL)');body=body[:start]+'''\tstruct ieee80211_ie *old_ie;
\tstruct ieee80211com *ic = vap->iv_ic;
\tIEEE80211_LOCK_BH(ic);
\told_ie = app_ie->ie;
\tapp_ie->ie = NULL;
\tapp_ie->length = 0;
\tIEEE80211_UNLOCK_BH(ic);
\tif (old_ie)
\t\tFREE(old_ie, M_DEVBUF);
\treturn 0;
}''';new=new[:s]+body+new[e:]
 s,e,body=function(new,'static int\nget_app_ie(');original=body
 body=body.replace('\tif (iebuf->app_buflen < app_ie->length)\n\t\treturn -EINVAL;', '\tstruct ieee80211com *ic = vap->iv_ic;\n\tIEEE80211_LOCK_BH(ic);\n\tif (iebuf->app_buflen < app_ie->length) {\n\t\tIEEE80211_UNLOCK_BH(ic);\n\t\treturn -EINVAL;\n\t}',1)
 body=body.replace('\tmemcpy(iebuf->app_buf, app_ie->ie, app_ie->length);','\tif (app_ie->length)\n\t\tmemcpy(iebuf->app_buf, app_ie->ie, app_ie->length);\n\tIEEE80211_UNLOCK_BH(ic);',1);new=new[:s]+body+new[e:];wireless.write_text(new,newline='\n')
 output=a.output/'source/wlan/ieee80211_output.c';old=output.read_text();touched[output]=old;new=old
 anchor='struct sk_buff *\nieee80211_get_probereq(';assert anchor in new;new=new.replace(anchor,COPY+'\n'+anchor,1)
 for frame in ('PROBE_REQ','PROBE_RESP','ASSOC_REQ','ASSOC_RESP'):
  new=new.replace('vap->app_ie[IEEE80211_APPIE_FRAME_'+frame+'].length +','IEEE80211_APPIE_MAX +',1)
  marker='\tif (vap->app_ie[IEEE80211_APPIE_FRAME_'+frame+'].ie) {' if frame in('PROBE_REQ','ASSOC_REQ')else '\t\tif (vap->app_ie[IEEE80211_APPIE_FRAME_'+frame+'].ie) {'
  s,e,body=function(new,marker)
  indent='\t' if frame in('PROBE_REQ','ASSOC_REQ')else '\t\t'
  replacement=indent+'''{
'''+indent+'\tunsigned int app_len = om_app_ie_copy(vap, IEEE80211_APPIE_FRAME_'+frame+''', frm);
'''
  if frame in('PROBE_RESP','ASSOC_RESP'):
   replacement+=indent+'\t(void)om_bss_tm_update_ie(frm, app_len, ic->om_bss_tm_flags);\n'
  replacement+=indent+'\tfrm += app_len;\n'+indent+'}'
  new=new[:s]+replacement+new[e:]
 output.write_text(new,newline='\n')
 setup=a.output/'source/wlan/ieee80211.c';old=setup.read_text();touched[setup]=old;new=old
 original='''\tfor (i = 0; i < IEEE80211_APPIE_NUM_OF_FRAME; i++) {
\t\tif (vap->app_ie[i].ie != NULL) {
\t\t\tFREE(vap->app_ie[i].ie, M_DEVBUF);
\t\t\tvap->app_ie[i].ie = NULL;
\t\t\tvap->app_ie[i].length = 0;
\t\t}
\t}'''
 replacement='''\tfor (i = 0; i < IEEE80211_APPIE_NUM_OF_FRAME; i++) {
\t\tstruct ieee80211_ie *old_ie;
\t\tIEEE80211_LOCK_BH(vap->iv_ic);
\t\told_ie = vap->app_ie[i].ie;
\t\tvap->app_ie[i].ie = NULL;
\t\tvap->app_ie[i].length = 0;
\t\tIEEE80211_UNLOCK_BH(vap->iv_ic);
\t\tif (old_ie)
\t\t\tFREE(old_ie, M_DEVBUF);
\t}''';assert new.count(original)==1;new=new.replace(original,replacement,1);setup.write_text(new,newline='\n')
 beacon=a.output/'source/wlan/ieee80211_beacon.c';old=beacon.read_text();touched[beacon]=old
 start,end,body=function(old,'void\nieee80211_beacon_update(')
 assert body.count('IEEE80211_LOCK(ic);')==1 and body.count('IEEE80211_UNLOCK(ic);')==1
 body=body.replace('IEEE80211_LOCK(ic);','IEEE80211_LOCK_BH(ic);',1).replace('IEEE80211_UNLOCK(ic);','IEEE80211_UNLOCK_BH(ic);',1)
 beacon.write_text(old[:start]+body+old[end:],newline='\n')
 patches=[];counts={}
 for path,old in touched.items():
  rel=path.relative_to(a.output).as_posix();after=path.read_bytes();before=old.encode();comments=lambda raw:Counter(raw[x['offset']:x['end_offset']]for x in scan_comments(raw))
  assert not comments(before)-comments(after),'original comments lost '+rel;counts[rel]=sum(comments(before).values());patches.append(''.join(difflib.unified_diff(old.splitlines(True),path.read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel)))
 (a.output/'app-ie-synchronization.patch').write_text(''.join(patches),encoding='utf-8')
 v={'status':'SOURCE_ONLY_R11_ALL_APP_READERS_SYNCHRONIZATION_PENDING_FIXTURES_BUILD','hardware_accessed':False,'firmware_eligible':False,'parent_result_sha256':sha(a.parent/'result.json'),'changed_sources':{p.relative_to(a.output).as_posix():sha(p)for p in touched},'wire_header_changes':False,'source_buffer_limit':1024,'existing_comments_preserved':counts,'scope':'Allocationoutsideiclock;lockedpointerlengthswap;readerslockcopyintoownedframe;freeoldafterunlock','limits':['Callcontext/reentrancy/lockorder andfullsourcefixture require verification','No genericVAPobject lifetime orthirdpartyAPPreadersafetyclaim','CompletechangedWLANunits andwholemoduledelta pending, nohardware']};(a.output/'result.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v,indent=2))
if __name__=='__main__':main()
