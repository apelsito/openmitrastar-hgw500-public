"""New immutable WLAN candidate recovering three exact OEM constant getters.

This extends the separate two-alias TX_MAXMPDU source candidate. No radio state
is enabled or modified: MIN_CAC id450 returns70, retry ids496/497 return8.
The values are observed OEM compatibility behavior, not physical capabilities.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alias-source", type=Path, required=True)
    p.add_argument("--wlan-getparam", type=Path, required=True)
    p.add_argument("--qdrv-getparam", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    original = a.alias_source.read_text()
    assert sha(a.alias_source) == "3bed348b48ae1da8a671a5ff1bb4f919fd773bf06c3d53fd130b5a4247433d96"
    wlan = json.loads(a.wlan_getparam.read_text())
    qdrv = json.loads(a.qdrv_getparam.read_text())
    assert wlan["ok"] and qdrv["ok"]
    wp = wlan["data"]["raw_result"]["value"]["pseudocode"]
    qp = qdrv["data"]["raw_result"]["value"]["pseudocode"]
    assert "case 0x1c2:" in wp and "*param_4 = 0x46;" in wp
    assert "else if (param_2 < 0x1f0)" in qp and "else if (param_2 < 0x1f2)" in qp and "*param_3 = 8;" in qp
    assert "#define MIN_CAC_PERIOD" in original and re.search(r"#define MIN_CAC_PERIOD\s+70", original)
    constants = """/* Recovered OEM read-only compatibility parameter numbers. These do not
 * enable DFS, change radio state, or assert measured retry behavior. */
#define OM_OEM_PARAM_MIN_CAC 450
#define OM_OEM_PARAM_SHORT_RETRY_LIMIT 496
#define OM_OEM_PARAM_LONG_RETRY_LIMIT 497

"""
    anchor = "static const struct iw_priv_args ieee80211_priv_args[]"
    assert original.count(anchor) == 1
    # Macros must precede getparam; place after includes before existing macro.
    insertion = original.index("#define MIN_CAC_PERIOD")
    candidate = original[:insertion] + constants + original[insertion:]
    table_start = candidate.index(anchor)
    table_end = candidate.index("\n};", table_start)
    table_addition = '\n\t{ OM_OEM_PARAM_MIN_CAC,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_min_cac" },\n\t{ OM_OEM_PARAM_SHORT_RETRY_LIMIT,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_sretry_lmt" },\n\t{ OM_OEM_PARAM_LONG_RETRY_LIMIT,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_lretry_lmt" },'
    candidate = candidate[:table_end] + table_addition + candidate[table_end:]
    signature = "ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,"
    start = candidate.index(signature)
    switch = candidate.index("switch (", start)
    brace = candidate.index("{", switch)
    cases = """
\t/* OEM getparam450 returns the existing70-second minimum. */
\tcase OM_OEM_PARAM_MIN_CAC:
\t\tparam[0] = MIN_CAC_PERIOD;
\t\tbreak;
\t/* Exact OEM QDRV returns8 for both496 and497. These are compatibility
\t * constants; no MuC/firmware command or runtime retry change occurs. */
\tcase OM_OEM_PARAM_SHORT_RETRY_LIMIT:
\tcase OM_OEM_PARAM_LONG_RETRY_LIMIT:
\t\tparam[0] = 8;
\t\tbreak;
"""
    candidate = candidate[:brace + 1] + cases + candidate[brace + 1:]
    check = candidate.replace(constants, "", 1).replace(table_addition, "", 1).replace(cases, "", 1)
    assert check == original
    a.output.mkdir(parents=True, exist_ok=False)
    path = a.output / "ieee80211_wireless.c"
    path.write_text(candidate, newline="\n")
    patch = "".join(difflib.unified_diff(original.splitlines(True), candidate.splitlines(True),
                                     fromfile="a/src/wlan/ieee80211_wireless.c", tofile="b/src/wlan/ieee80211_wireless.c"))
    (a.output / "readonly-oem-constants.patch").write_text(patch, newline="\n")
    result = dict(schema="openmitrastar.oem-wlan-constant-candidate/v1", status="SOURCE_ONLY_FIVE_RECOVERED_ENTRIES_NO_GO_MODULE",
                  hardware_accessed=False, firmware_eligible=False, aliases_source_sha256=sha(a.alias_source),
                  candidate_sha256=sha(path), baseline_unchanged=sha(a.alias_source) == "3bed348b48ae1da8a671a5ff1bb4f919fd773bf06c3d53fd130b5a4247433d96",
                  wlan_getparam_sha256=sha(a.wlan_getparam), qdrv_getparam_sha256=sha(a.qdrv_getparam),
                  recovered=[dict(cmd=450, name="get_min_cac", value=70),dict(cmd=496,name="get_sretry_lmt",value=8),dict(cmd=497,name="get_lretry_lmt",value=8)],
                  total_with_prior_aliases=5, remaining_original_table_gaps=39,
                  gate="Need completeWLAN module compile/delta audit and exact source fixture before module promotion",
                  output_mode="Source only; no device/flash/firmware action")
    (a.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
