"""Prepare WLAN/QDRV read-only recovery with named existing CCA fields.

No raw OEM offset is used in candidate code. A separate ARC compiler witness
measures the port offsets. All setters, mode/DFS/radio policy remain unchanged.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
QDRV = ROOT / "work/linux510-radio-port/quantenna-f364-lifetime/qdrv"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_function(text, signature):
    start = text.index(signature)
    cursor = text.index("{", start) + 1
    level = 1
    while level:
        level += (text[cursor] == "{") - (text[cursor] == "}")
        cursor += 1
    return start, cursor, text[start:cursor]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wlan-source", type=Path, required=True)
    p.add_argument("--oem-getparam", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    assert sha(a.wlan_source) == "b5b601dadb7e681297d832aa10d4751fda0f9f92bf47c06c3255d6a49d91e117"
    evidence = json.loads(a.oem_getparam.read_text())
    assert evidence["ok"]
    pseudocode = evidence["data"]["raw_result"]["value"]["pseudocode"]
    assert "param_2 == 0x14b" in pseudocode and "(iVar7 + 0x5360)" in pseudocode
    assert "param_2 == 0x113" in pseudocode and "(iVar7 + 0x5361)" in pseudocode
    a.output.mkdir(parents=True, exist_ok=False)
    # Complete candidate qdrv tree for include topology, only one .c differs.
    destination = a.output / "source/qdrv"
    shutil.copytree(QDRV, destination)
    shutil.copytree(QDRV.parent / "wlan", a.output / "source/wlan")
    qpath = destination / "qdrv_wlan.c"
    original = qpath.read_text()
    start, end, body = extract_function(original, "static int qdrv_wlan_80211_getparam(")
    insertion = body.index("switch (param) {") + len("switch (param) {")
    qcases = """
\t/* OEM read-only getters331/275 use these existing named fields.
\t * The port compiler ABI witness is independent of OEM numeric offsets. */
\tcase IEEE80211_PARAM_CCA_FIXED:
\t\t*value = ic->cca_fix_disable;
\t\tbreak;
\tcase IEEE80211_PARAM_AUTO_CCA_ENABLE:
\t\t*value = ic->auto_cca_enable;
\t\tbreak;
"""
    assert "case IEEE80211_PARAM_CCA_FIXED:" not in body and "case IEEE80211_PARAM_AUTO_CCA_ENABLE:" not in body
    candidate_body = body[:insertion] + qcases + body[insertion:]
    candidate = original[:start] + candidate_body + original[end:]
    assert candidate.replace(qcases, "", 1) == original
    qpath.write_text(candidate, newline="\n")
    fixture = """#include <assert.h>
#include <stdint.h>
struct ieee80211com { uint8_t cca_fix_disable; uint8_t auto_cca_enable; };
static void actual_getter(struct ieee80211com *ic, int param, int *value)
{
 switch(param) {
""" + qcases.replace("IEEE80211_PARAM_CCA_FIXED", "331").replace("IEEE80211_PARAM_AUTO_CCA_ENABLE", "275") + """
 default: break;
 }
}
int main(void) {
 struct ieee80211com ic;
 unsigned a,b; int result; unsigned checks=0;
 for(a=0;a<256;a++) for(b=0;b<256;b++) {
  ic.cca_fix_disable=a;ic.auto_cca_enable=b;
  result=-1;actual_getter(&ic,331,&result);assert(result==(int)a);checks++;
  result=-1;actual_getter(&ic,275,&result);assert(result==(int)b);checks++;
  assert(ic.cca_fix_disable==a && ic.auto_cca_enable==b);checks++;
 }
 result=123456;actual_getter(&ic,999,&result);assert(result==123456);checks++;
 assert(checks==196609);return 0;
}
"""
    (a.output / "actual-cca-getters-fixture.c").write_text(fixture)
    wlan = a.wlan_source.read_text()
    signature = "ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,"
    start = wlan.index(signature)
    switch = wlan.index("switch (", start)
    brace = wlan.index("{", switch)
    wcases = """
\t/* Output handling lives in qualified QDRV and returns existing fields. */
\tcase IEEE80211_PARAM_CCA_FIXED:
\tcase IEEE80211_PARAM_AUTO_CCA_ENABLE:
\t\tieee80211_param_from_qdrv(vap, param[0] & 0xffff, &param[0], NULL, 0);
\t\tbreak;
"""
    wlan_candidate = wlan[:brace + 1] + wcases + wlan[brace + 1:]
    table = wlan_candidate.index("static const struct iw_priv_args ieee80211_priv_args[]")
    table_end = wlan_candidate.index("\n};", table)
    walias = '\n\t{ IEEE80211_PARAM_CCA_FIXED,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_cca_fixed" },\n\t{ IEEE80211_PARAM_AUTO_CCA_ENABLE,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_auto_cca_en" },'
    wlan_candidate = wlan_candidate[:table_end] + walias + wlan_candidate[table_end:]
    assert wlan_candidate.replace(wcases, "", 1).replace(walias, "", 1) == wlan
    wpath = a.output / "ieee80211_wireless.c"
    wpath.write_text(wlan_candidate, newline="\n")
    qdiff = "".join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),fromfile="a/src/qdrv/qdrv_wlan.c",tofile="b/src/qdrv/qdrv_wlan.c"))
    wdiff = "".join(difflib.unified_diff(wlan.splitlines(True),wlan_candidate.splitlines(True),fromfile="a/src/wlan/ieee80211_wireless.c",tofile="b/src/wlan/ieee80211_wireless.c"))
    (a.output / "named-cca-getters.patch").write_text(qdiff + wdiff, newline="\n")
    pins = {x.relative_to(a.output).as_posix():sha(x) for x in destination.rglob("*") if x.is_file()}
    result = dict(schema="openmitrastar.named-cca-getters/v1",status="SOURCE_ONLY_SEVEN_ENTRIES_PENDING_ABI_MODULE_GATES",
                  hardware_accessed=False,firmware_eligible=False,original_qdrv_source_sha256=sha(QDRV / "qdrv_wlan.c"),
                  qdrv_candidate_sha256=sha(qpath),wlan_parent_sha256=sha(a.wlan_source),wlan_candidate_sha256=sha(wpath),
                  oem_getparam_evidence_sha256=sha(a.oem_getparam),source_pins=pins,
                  new_getters=[dict(id=331,field="ic->cca_fix_disable"),dict(id=275,field="ic->auto_cca_enable")],
                  prior_recovered_entries=5,total_recovered_entries=7,remaining_table_gaps=37,
                  fixture_checks_expected=196609,
                  limits=["Must ship qualifiedQDRV/WLAN together; oldQDRV does not implement these getters.",
                          "Compiler witnesses must verify actual port field offsets and callback ABI.",
                          "Values report retained baseline-specific policy state; no universal retry or hardware claim.",
                          "All baseline setters, DFS and runtime activation remain unchanged."])
    (a.output / "result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k]for k in ("status","qdrv_candidate_sha256","wlan_candidate_sha256","total_recovered_entries")}))


if __name__ == "__main__":
    main()
