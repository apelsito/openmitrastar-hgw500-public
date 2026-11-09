"""Prepare the single R9 observation tree without touching sealed predecessors."""
from pathlib import Path
import hashlib,json,shutil
import f367r9_boundary_patch as boundary
import f367r9_hostlink_trace_patch_r2 as host
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/kernel-port/f367r7-clock-publication'
PEER=ROOT/'work/linux510-radio-port/quantenna/wlan'
DST=ROOT/'work/kernel-port/f367r9-transition-observation'
OVERLAY=ROOT/'versions/lyoko-foundation-6.11.8-f367r9-transition-observation/overlay'
HOST_TEST=ROOT/'outputs/preflight/f367r9-hostlink-trace-r2-20260922T224107Z/result.json'
CTRL=ROOT/'versions/lyoko-foundation-6.11.7-f367r8-mode-contract/overlay/usr/sbin/om-f367-control'
STATUS=ROOT/'versions/lyoko-foundation-6.11.2-f367r3-owned-lock-release/overlay/usr/sbin/om-f367-status'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):p=Path(p);return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)
def main():
 if DST.exists() or OVERLAY.exists():raise ValueError('immutable R9 source exists')
 proof=json.loads(HOST_TEST.read_text());assert proof['status']=='PASS_R2_SHARED_CALSTATE_OBSERVATION' and all(proof['checks'].values())
 for path,digest in proof['source_pins'].items():assert sha(path)==digest
 patches={
  'qdrv/qdrv/qdrv_hostlink.c':host.patch_hostlink((BASE/'qdrv/qdrv/qdrv_hostlink.c').read_text()),
  'qdrv/qdrv/qdrv_wlan.c':boundary.patch_driver((BASE/'qdrv/qdrv/qdrv_wlan.c').read_text()),
  'qdrv/qdrv/qdrv_radar.c':boundary.patch_radar((BASE/'qdrv/qdrv/qdrv_radar.c').read_text()),
  'qdrv/qdrv/qdrv_f367r9_trace.h':boundary.HEADER,
  'wlan/ieee80211_wireless.c':host.patch_peer_csa((PEER/'ieee80211_wireless.c').read_text())}
 control=boundary.patch_controller(CTRL.read_text());status=boundary.patch_status(STATUS.read_text())
 DST.mkdir(parents=True)
 for sub in ('kernel','uapi','qdrv'):shutil.copytree(BASE/sub,DST/sub)
 (DST/'wlan').mkdir()
 peer_files=[p for p in PEER.iterdir() if p.is_file() and (p.suffix in ('.c','.h') or p.name=='Makefile')]
 for p in peer_files:shutil.copyfile(p,DST/'wlan'/p.name)
 makefile=DST/'wlan/Makefile';text=makefile.read_text();text+='\n# R9: only the modified peer module is rebuilt. Other peer modules are reused.\nobj-m := wlan.o\n';makefile.write_bytes(text.encode())
 for name,text in patches.items():(DST/name).write_bytes(text.encode())
 for name,text in [('om-f367-control',control),('om-f367-status',status)]:
  target=OVERLAY/'usr/sbin'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(text.encode())
 pins={p.relative_to(DST).as_posix():sha(p) for p in DST.rglob('*') if p.is_file()}
 base_pins={p.relative_to(BASE).as_posix():sha(p) for p in BASE.rglob('*') if p.is_file() and p.parts[-2]!='userspace' and p.name!='source-manifest.json'}
 report=dict(schema='openmitrastar.f367r9-transition-source/v1',status='PREPARED_FOR_OBSERVATION_CHECKS',source_pins=pins,baseline_source_pins=base_pins,peer_baseline_pins={str(p):sha(p) for p in peer_files},changed_runtime_sources=list(patches),overlay_pins={str(p):sha(p) for p in OVERLAY.rglob('*') if p.is_file()},hostlink_trace_test=item(HOST_TEST),patch_sources={str(p):sha(p) for p in [ROOT/'tools/f367r9_boundary_patch.py',ROOT/'tools/f367r9_hostlink_trace_patch.py',Path(__file__)]},source_root=str(DST),peer_compat_root=str(ROOT/'work/linux510-radio-port/quantenna/qdrv/compat/include'),no_policy_or_timeout_change=True,no_new_cross_module_symbols=True,hardware_actions=False)
 (DST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(source=str(DST),overlay=str(OVERLAY),files=len(pins))))
if __name__=='__main__':main()
