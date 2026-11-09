"""Compile actual named CCA getters and ARC field-offset witness offline.

Uses the retained F365 QDRV command/ABI context; no host compiler substitution
for ARC layout. GCC host fixture tests source case blocks with fake state only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

import build_f370_qdrv_module as build
from recover_hgw5g_driver_ops import Elf


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command,cwd,out):
    proc=subprocess.run(command,cwd=cwd,capture_output=True)
    out.with_suffix(".stdout").write_bytes(proc.stdout)
    out.with_suffix(".stderr").write_bytes(proc.stderr)
    out.with_suffix(".command.json").write_text(json.dumps(command,indent=2)+"\n")
    assert proc.returncode==0,proc.stderr.decode(errors="replace")[-3000:]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    manifest=json.loads((a.candidate/"result.json").read_text())
    for path,h in manifest["source_pins"].items():assert sha(a.candidate/path)==h,path
    a.output.mkdir(parents=True,exist_ok=False)
    result=dict(status="NO_GO_FIXTURE",hardware_accessed=False,firmware_eligible=False)
    try:
        src=a.candidate/"source/qdrv"
        witness=(src/"qdrv_wlan.c").read_text().split("/* Delay prior to enabling hang detection */",1)[0]
        witness+='''\nconst unsigned om_cca_layout[]={offsetof(struct ieee80211com,cca_fix_disable),offsetof(struct ieee80211com,auto_cca_enable),offsetof(struct ieee80211com,ic_getparam),sizeof(struct ieee80211com)};\n'''
        path=a.output/"witness.c";path.write_text(witness)
        cmd,_=build.command("qdrv_wlan",src,a.output)
        cmd[-1]=str(path);cmd[cmd.index("-o")+1]=str(a.output/"witness.o")
        cmd.insert(cmd.index("-c"),"-I"+str(src))
        run(cmd,build.context.CONTEXT,a.output/"compile-arc-witness")
        elf=Elf(a.output/"witness.o")
        symbol=next(s for s in elf.syms if s["name"]=="om_cca_layout")
        data=elf.sections[symbol["section"]]["data"][symbol["value"]:symbol["value"]+symbol["size"]]
        fields=dict(zip(("cca_fix_disable","auto_cca_enable","ic_getparam","sizeof_ieee80211com"),struct.unpack("<4I",data)))
        assert fields["cca_fix_disable"]+1==fields["auto_cca_enable"] and fields["ic_getparam"]>fields["auto_cca_enable"]
        # Compile the full actual changed ARC source unit as a source/header gate.
        cmd,_=build.command("qdrv_wlan",src,a.output)
        run(cmd,build.context.CONTEXT,a.output/"compile-arc-qdrv-wlan")
        fixture=a.candidate/"actual-cca-getters-fixture.c"
        run(["gcc","-std=c11","-O1","-g","-fsanitize=address,undefined",str(fixture),"-o",str(a.output/"fixture")],a.output,a.output/"compile-fake-fixture")
        run([str(a.output/"fixture")],a.output,a.output/"run-fake-fixture")
        wlan=(a.candidate/"ieee80211_wireless.c").read_text()
        signature="ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,"
        start=wlan.index(signature);switch=wlan.index("switch (param[0] & 0xffff)",start)
        body_start=wlan.index("case IEEE80211_PARAM_CCA_FIXED:",switch)
        body_end=wlan.index("\n\t/* OEM getparam450",body_start)
        actual=wlan[body_start:body_end].replace("IEEE80211_PARAM_CCA_FIXED","331").replace("IEEE80211_PARAM_AUTO_CCA_ENABLE","275")
        assert "param[0] & 0xffff" in actual
        forward='''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
static int observed;
static void ieee80211_param_from_qdrv(void *vap,int id,int *out,void *data,int len) {observed=id;*out=77;}
static void actual_wlan_getter(int *param) {void *vap=0;switch(param[0]&0xffff) {
'''+actual+'''\n default: break;}}
int main(void) {unsigned high;int result;for(high=0;high<65536;high++) {
result=(high<<16)|331;observed=-1;actual_wlan_getter(&result);assert(observed==331 && result==77);
result=(high<<16)|275;observed=-1;actual_wlan_getter(&result);assert(observed==275 && result==77);
}return 0;}
'''
        forward_path=a.output/"actual-wlan-forward-fixture.c";forward_path.write_text(forward)
        run(["gcc","-std=c11","-O1","-g","-fsanitize=address,undefined",str(forward_path),"-o",str(a.output/"forward-fixture")],a.output,a.output/"compile-forward-fixture")
        run([str(a.output/"forward-fixture")],a.output,a.output/"run-forward-fixture")
        result.update(status="PASS_OFFLINE_ARC_ABI_AND_ACTUAL_GETTER_FIXTURE",arc_port_fields=fields,
                      oem_fields={"cca_fix_disable":0x5360,"auto_cca_enable":0x5361,"ic_getparam":0x5424},
                      raw_oem_offsets_not_used_in_candidate=True,fixture_cases=65536,fixture_checks=196609,
                      actual_source_unit_compiled=True,source_candidate_sha256=sha(src/"qdrv_wlan.c"),
                      witness_sha256=sha(a.output/"witness.o"),source_unchanged=True,
                      wlan_high16_forward_cases=65536,wlan_high16_forward_checks=131072,
                      limitation="ARC object and exhaustive fake field reads only; full module pair qualification and physical gates remainUNRUN")
        for path,h in manifest["source_pins"].items():assert sha(a.candidate/path)==h,path
    except Exception as ex:result["error"]=str(ex)
    (a.output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result));return int(not result["status"].startswith("PASS_"))


if __name__=="__main__":raise SystemExit(main())
