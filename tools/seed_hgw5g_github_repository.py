"""Seed an owner-requested independent private repository without editing sources.

Preserve original Git blobs, current port sources, exact comments and selected
static evidence. Device images and modules stay in ignored local-only/. No
hardware/network/configuration operations. A new seed manifest seals copies.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tarfile
import io

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
UPSTREAM = ROOT / 'work/sources/Quantenna-GPL'
ROWS = []

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def copy_file(src, rel, origin=None):
    src = Path(src); dst = REPO / rel
    if dst.exists():
        raise FileExistsError(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes(); dst.write_bytes(raw)
    assert src.read_bytes() == raw and dst.read_bytes() == raw
    ROWS.append({'path':str(rel).replace('\\','/'),'source':origin or str(src.relative_to(ROOT)) if src.is_relative_to(ROOT) else str(src),
                 'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'copy':'EXACT_BYTES'})

def source_tree(src, rel, suffixes=None):
    src = Path(src)
    for p in sorted(src.rglob('*')):
        if p.is_file() and (p.suffix in ('.c','.h','.S','.s','.mk','.inc') or p.name in ('Makefile','Kconfig','COPYING','LICENSE','README','README.md') or suffixes and p.suffix in suffixes):
            copy_file(p, Path(rel)/p.relative_to(src))

def main():
    assert (REPO/'.git').is_dir()
    assert not (REPO/'manifests/seed-provenance.json').exists(), 'seed already sealed'
    head = subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip()
    archive = subprocess.check_output(['git','-C',str(UPSTREAM),'archive',head,'drivers','include','common','README.md','Makefile','Make.toolchain','Kconfig'])
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as tar:
        for member in tar.getmembers():
            if not member.isfile(): continue
            assert '..' not in Path(member.name).parts and not member.name.startswith('/')
            raw = tar.extractfile(member).read()
            dest = REPO/'vendor/legacy-gpl'/member.name
            dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(raw)
            ROWS.append({'path':dest.relative_to(REPO).as_posix(),'source':'git:christianheyl/Quantenna-GPL@'+head+':'+member.name,
                         'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'copy':'EXACT_GIT_BLOB'})
    copy_file(UPSTREAM/'linux_2.6.35.12/COPYING','LICENSES/Linux-GPL-2.0.txt')
    source_tree(ROOT/'work/linux510-radio-port/quantenna-f364-lifetime/qdrv','src/qdrv')
    source_tree(ROOT/'work/linux510-radio-port/quantenna/wlan','src/wlan')
    source_tree(ROOT/'work/linux510-radio-port/quantenna-f344-peers/platform/topaz','src/platform/topaz')
    source_tree(ROOT/'work/linux510-radio-port/quantenna/platform/ruby','src/platform/ruby')
    source_tree(ROOT/'work/linux510-radio-port/quantenna/qdrv/compat','src/compat')
    source_tree(ROOT/'work/kernel-port/f370-tqe-observation/source/qdrv','candidates/f370-qdrv')
    # Preserve current modified shared headers separately from original Git blobs.
    source_tree(UPSTREAM/'drivers/include','vendor/port-context/drivers/include')
    source_tree(UPSTREAM/'include','vendor/port-context/include')
    copy_file(ROOT/'outputs/rea/ioctl-alias-candidate-20261022T132600Z-r1/ieee80211_wireless.c','candidates/tx-maxmpdu-aliases/ieee80211_wireless.c')
    copy_file(ROOT/'outputs/rea/ioctl-alias-candidate-20261022T132600Z-r1/tx-maxmpdu-aliases.patch','patches/0001-recover-oem-tx-maxmpdu-aliases.patch')
    modules={
      'oem-qdrv':ROOT/'work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/qdrv/qdrv.ko',
      'oem-wlan':ROOT/'work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/wlan/wlan.ko',
      'oem-switch-tqe':ROOT/'work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/topaz/switch_tqe.ko',
      'f365-qdrv':ROOT/'outputs/rea/arc700-20261021-r2/f365-ram-activation/r3/payload/modules/qdrv.ko',
      'f365-wlan':ROOT/'outputs/rea/arc700-20261021-r2/f365-ram-activation/r3/payload/modules/wlan.ko',
      'f365-switch-tqe':ROOT/'outputs/rea/arc700-20261021-r2/tqe-current/switch_tqe.ko',
      'f370-qdrv':ROOT/'outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/a/qdrv.ko',
      'aliases-wlan':ROOT/'outputs/rea/driver5g-ops-20261022-wlan-alias-module-r2/a/wlan.ko'}
    for name,p in modules.items():copy_file(p,Path('local-only/modules')/(name+'.ko'))
    image=ROOT/'Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin'
    copy_file(image,'local-only/original-firmware/'+image.name)
    for p in sorted((ROOT/'tools').glob('*.py')):
        if p.name in {'recover_hgw5g_driver_ops.py','catalog_hgw_firmware_comments.py','test_catalog_hgw_firmware_comments.py',
                      'prepare_hgw5g_ioctl_alias_candidate.py','rebuild_switch_tqe_baseline_gate.py','rebuild_wlan_baseline_gate.py',
                      'build_wlan_txmaxmpdu_alias_module.py','qualify_wlan_txmaxmpdu_alias_module.py',
                      'build_f370_qdrv_module.py','qualify_f370_qdrv_module.py','compile_f368_changed_objects.py',
                      'link_arc700_analysis_image.py','run_rea_arc700_lab.py','prepare_rea_arc700_lab.py',
                      'prepare_rea_arc700_oem_abi3_lane.py','recover_oem_wlan_missing_case_map.py',
                      'summarize_oem_wlan_case_evidence.py','label_oem_qdrv_analysis_callbacks.py',
                      'seed_hgw5g_github_repository.py'}:
            copy_file(p,'tools/integration/'+p.name)
    # Portable tools have no integration imports.
    for name in ('recover_hgw5g_driver_ops.py','catalog_hgw_firmware_comments.py','test_catalog_hgw_firmware_comments.py'):
        copy_file(ROOT/'tools'/name,'tools/'+name)
    evidence={
      'ops-original-20261022':ROOT/'outputs/rea/ops-inventory-20261022T132200Z-r7',
      'tqe-baseline-20261022':ROOT/'outputs/rea/driver5g-ops-20261022-tqe-baseline-r5',
      'wlan-baseline-20261022':ROOT/'outputs/rea/driver5g-ops-20261022-wlan-baseline-r2',
      'wlan-aliases-build-20261022':ROOT/'outputs/rea/driver5g-ops-20261022-wlan-alias-module-r2',
      'wlan-aliases-qualification-20261022':ROOT/'outputs/rea/driver5g-ops-20261022-wlan-alias-qualification-r2',
      'wlan-aliases-verifier-faults-20261022':ROOT/'outputs/rea/driver5g-ops-20261022-alias-qualifier-fault-tests-r1',
      'qdrv-f370-qualification-20261021':ROOT/'outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/qualification-20261021T222300Z',
      'alias-source-20261022':ROOT/'outputs/rea/ioctl-alias-candidate-20261022T132600Z-r1',
      'rea-topaz-tqe-xmit-20261022':ROOT/'outputs/rea/driver5g-ops-20261022-rea-topaz-tqe-xmit-r1',
      'rea-qdrv-wlan-init-20261022':ROOT/'outputs/rea/driver5g-ops-20261022-rea-qdrv-wlan-init-r2',
      'review-20261022':ROOT/'outputs/rea/review-20261022-independent-r1'}
    for label,folder in evidence.items():
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix in ('.json','.md'):
                copy_file(p,Path('evidence')/label/p.name)
    (REPO/'manifests').mkdir(exist_ok=True)
    manifest={'schema':'openmitrastar.repository-seed/v1','upstream_commit':head,
              'upstream_source':'https://github.com/christianheyl/Quantenna-GPL',
              'hardware_accessed':False,'comments_deleted':False,'files':ROWS,
              'limits':['Legacy GPL upstream is v37.4.0.62.1, not complete OEM v37.4.0.89 source.',
                        'Only available radio/related GPL sources are imported; binary-only firmware remains binary-only.',
                        'local-only contains owner-local original image/modules and is never committed.',
                        'No claim of full OEM semantics or Linux5.10 release acceptance.']}
    (REPO/'manifests/seed-provenance.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    assert all(sha(REPO/r['path'])==r['sha256'] for r in ROWS)
    print(json.dumps({'files':len(ROWS),'bytes':sum(r['bytes'] for r in ROWS),'repo':str(REPO),'all_copies_exact':True}))

if __name__=='__main__':main()
