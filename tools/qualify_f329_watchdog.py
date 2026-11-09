"""Bind F329 offline sources, ARC build and behavioral tests without hardware."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"work/kernel-port/versions/f329-watchdog"


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build",required=True,type=Path)
    ap.add_argument("--tests",required=True,type=Path)
    ap.add_argument("--replay",required=True,type=Path)
    args=ap.parse_args()
    paths=[p.resolve() for p in (args.build,args.tests,args.replay)]
    if not all(p.is_relative_to(ROOT/"outputs") for p in paths):
        raise SystemExit("only local outputs evidence accepted")
    build,tests,replay=[json.loads(p.read_text()) for p in paths]
    failures=[]
    if build.get("status")!="PASS_OFFLINE_BUILD_PHYSICAL_GATES_UNRUN":failures.append("ARC build not PASS")
    if tests.get("status")!="PASS_OFFLINE_BEHAVIOR":failures.append("C behavior not PASS")
    if tests.get("c_behavior_cases")!=25 or tests.get("restart_fallback_cases")!=2:failures.append("test suite incomplete")
    if len(tests.get("static_contracts",{}))!=9 or not all(tests.get("static_contracts",{}).values()):failures.append("static contracts incomplete")
    if replay.get("status")!="PASS" or replay.get("compared_files")!=10:failures.append("source generator replay failed")
    current={p.relative_to(SOURCE).as_posix():sha(p) for p in SOURCE.rglob("*") if p.is_file()}
    if current!=build.get("input_sources"):failures.append("source/build drift")
    for rel,digest in current.items():
        p=paths[2].parent/rel
        if not p.is_file() or sha(p)!=digest:failures.append("source/replay drift: "+rel)
    if tests.get("driver_sha256")!=current["drivers/watchdog/dw_wdt.c"]:failures.append("tests/driver drift")
    evidence=[]
    for p in paths:
        evidence.append({"path":p.relative_to(ROOT).as_posix(),"sha256":sha(p),"bytes":p.stat().st_size})
    for name,metadata in build.get("artifacts",{}).items():
        p=(paths[0].parent/name).resolve()
        if not p.is_relative_to(paths[0].parent):raise SystemExit("artifact path escaped build output")
        if sha(p)!=metadata["sha256"] or p.stat().st_size!=metadata["bytes"]:failures.append("artifact drift: "+name)
        evidence.append({"path":p.relative_to(ROOT).as_posix(),**metadata})
    dts=(paths[0].parent/"f329.decompiled.dts").read_text()
    match=re.search(r'watchdog@f4000000\s*\{([^}]+)\}',dts,re.S)
    if not match or 'status = "disabled";' not in match[1] or "quantenna,watchdog-experiment" in match[1]:failures.append("built DT enables experiment")
    cfg=(paths[0].parent/"f329.config").read_text().splitlines()
    for flag in ("CONFIG_DW_WATCHDOG=y","CONFIG_WATCHDOG_CORE=y","CONFIG_WATCHDOG_NOWAYOUT=y","# CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY is not set","# CONFIG_QTN_TOPAZ_HEAD_WDT_CANARY is not set"):
        if flag not in cfg:failures.append("compiled config drift: "+flag)
    for rel in ("work/sources/Quantenna-GPL/common/topaz_config.h","work/sources/Quantenna-GPL/common/ruby_platform.h","work/sources/Quantenna-GPL/drivers/ruby/soc.h","work/sources/Quantenna-GPL/drivers/ruby/machine.c","tools/prepare_f329_watchdog_sources.py","tools/build_f329_watchdog_offline.py","tools/test_f329_watchdog.py","tools/qualify_f329_watchdog.py","docs/OPENMITRASTAR_F329_WATCHDOG_PORT.md"):
        p=ROOT/rel;evidence.append({"path":rel,"sha256":sha(p),"bytes":p.stat().st_size})
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out=ROOT/f"outputs/preflight/f329-watchdog-qualified-{stamp}"
    out.mkdir(parents=True)
    result={"schema":"openmitrastar.f329-watchdog-qualification/v1","created_utc":stamp,"status":"PASS_OFFLINE_PORT_PHYSICAL_GATES_UNRUN" if not failures else "FAIL","failures":failures,"source_sha256":current,"evidence":evidence,"native_c_behavior_cases":25,"native_restart_cases":2,"static_contracts":9,"source_generator_replay":"10 files byte-identical","hardware_touched":False,"watchdog_armed":False,"measured_clock_hz":None,"measured_reset_latency_seconds":None,"hardware_reset_proven":False,"physical_acceptance":"UNRUN","flash_go_no_go":"NO_GO_NOT_A_COMPOSED_FIRMWARE_IMAGE","slot_fit":"NOT_EVALUATED_NO_COMPOSED_IMAGE","bootbase_contract":"NOT_APPLICABLE_KERNEL_OVERLAY_ONLY","release_eligible":False}
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"output":str(out),"status":result["status"],"failures":failures}))
    return int(bool(failures))


if __name__=="__main__":raise SystemExit(main())
