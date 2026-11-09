"""Recover OEM NAC457 read format, with a source-only divide-by-zero guard.

Reads only the published ABI prefix. No NAC mode command, client identity,
entry list, raw calibration or opaque tail is exported. Snapshot consistency
across asynchronous MuC updates is not asserted.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

HELPER = '''/* Exact OEM457 getter prefix; no per-client NAC entries are exposed.
 * MuC can update the three fields asynchronously, so this is a sampled tuple.
 * Guard the zero-initialized/not-ready denominator; OEM itself had no guard. */
static int om_oem_get_nac_mode_sample(struct qtn_nac_mon_info_v89 *nac,
                                    int *value)
{
    u16 value0, value1;
    u8 enabled;
    u32 percent;

    if (!nac)
        return -EAGAIN;
    value0 = READ_ONCE(nac->config_value0);
    value1 = READ_ONCE(nac->config_value1);
    enabled = (u8)READ_ONCE(nac->enabled);
    if (!value1)
        return -EAGAIN;
    percent = ((u32)value0 * 100U) / value1;
    *value = ((u32)value1 << 16) | ((percent & 0xffU) << 8) | enabled;
    return 0;
}

'''


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--parent",type=Path,required=True);p.add_argument("--oem-get",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
 assert sha(a.parent)=="7a128781902eb6cc58f71e2b4a30ae005de7ebf168a10a9ae4139557b93a9be8"
 original=a.parent.read_text();rea=json.loads(a.oem_get.read_text());assert rea["ok"]
 pseudocode=rea["data"]["raw_result"]["value"]["pseudocode"]
 assert "case 0x1c9:" in pseudocode and "puVar7[1]" in pseudocode and "(uVar2 & 0xff) << 8" in pseudocode
 a.output.mkdir(parents=True,exist_ok=False)
 macro="#define OM_OEM_PARAM_NAC_MODE 457\n"
 candidate=original.replace("#define OM_OEM_PARAM_DEVICE_MODE 451",macro+"#define OM_OEM_PARAM_DEVICE_MODE 451",1)
 include='#include <qtn/shared_params.h>'
 header_include='\n#include "openmitrastar_nac_getter.h"'
 candidate=candidate.replace(include,include+header_include,1)
 helper_anchor='static const struct iw_priv_args ieee80211_priv_args[]'
 anchor=candidate.index('static int\nieee80211_ioctl_getparam(')
 candidate=candidate[:anchor]+HELPER+candidate[anchor:]
 start=candidate.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=candidate.index('{',candidate.index('switch (param[0] & 0xffff)',start))
 cases='''
\tcase OM_OEM_PARAM_NAC_MODE:
\t\treturn om_oem_get_nac_mode_sample(
\t\t    (struct qtn_nac_mon_info_v89 *)READ_ONCE(soc_shared_params->nac_mon_info_lhost),
\t\t    &param[0]);
'''
 candidate=candidate[:brace+1]+cases+candidate[brace+1:]
 start=candidate.index(helper_anchor);end=candidate.index('\n};',start)
 entry='\n\t{ OM_OEM_PARAM_NAC_MODE,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_nac_mode" },'
 candidate=candidate[:end]+entry+candidate[end:]
 assert candidate.replace(macro,'',1).replace(header_include,'',1).replace(HELPER,'',1).replace(cases,'',1).replace(entry,'',1)==original
 header='''#ifndef OPENMITRASTAR_NAC_GETTER_H
#define OPENMITRASTAR_NAC_GETTER_H
#include <linux/types.h>
#include <linux/build_bug.h>
/* Recovered shared prefix only. Entries and opaque tail are deliberately unused. */
struct qtn_nac_mon_info_v89 {u16 config_value0;u16 config_value1;u16 enabled;u16 reserved;};
static_assert(sizeof(struct qtn_nac_mon_info_v89)==8);
#endif
'''
 (a.output/'openmitrastar_nac_getter.h').write_text(header)
 source=a.output/'ieee80211_wireless.c';source.write_text(candidate,newline='\n')
 patch=''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile='a/src/wlan/ieee80211_wireless.c',tofile='b/src/wlan/ieee80211_wireless.c'))
 (a.output/'nac-prefix-getter.patch').write_text(patch,newline='\n')
 fixture='''#include <stdint.h>
#include <assert.h>
#include <stddef.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;
#define EAGAIN 11
#define READ_ONCE(x) (x)
struct qtn_nac_mon_info_v89 {u16 config_value0;u16 config_value1;u16 enabled;u16 reserved;};
'''+HELPER+'''int main(void){struct qtn_nac_mon_info_v89 n;unsigned a,b,e;int value;uint32_t expected;
value=123;assert(om_oem_get_nac_mode_sample(NULL,&value)==-11&&value==123);
n.config_value1=0;value=123;assert(om_oem_get_nac_mode_sample(&n,&value)==-11&&value==123);
for(a=0;a<65536;a++)for(b=1;b<65536;b+=257){n.config_value0=a;n.config_value1=b;n.enabled=(a^b);n.reserved=0xbeef;
expected=(b<<16)|(((a*100U/b)&255U)<<8)|((a^b)&255U);value=-1;assert(om_oem_get_nac_mode_sample(&n,&value)==0);assert((uint32_t)value==expected);assert(n.config_value0==a&&n.config_value1==b&&n.reserved==0xbeef);}
return 0;}
'''
 (a.output/'actual-nac-getter-fixture.c').write_text(fixture)
 result=dict(status='SOURCE_ONLY_NAC_READ_FORMAT_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,candidate_sha256=sha(source),header_sha256=sha(a.output/'openmitrastar_nac_getter.h'),parent_sha256=sha(a.parent),oem_get_sha256=sha(a.oem_get),functional_operations_added=9,total_added_entries=11,remaining_original_table_gaps=33,behavior_delta='Return-EAGAIN unchangedoutput for absentpointer or denominator0; OEMunguarded division couldfault',limits=['No mode setter or calibration/client records.','No cross-field coherent snapshot claim.','Current pointer publication/lifetime must be qualified before modulepromotion.','Header is exact8-byte prefix only, not a redefinition of complete2596-byte allocation.'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
