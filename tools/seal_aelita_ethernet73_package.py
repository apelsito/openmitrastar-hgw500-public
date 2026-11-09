"""SealonlynewEMACpackage/docmetadata; neverGitmutate/privatebinarycopy."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver/components/ethernet-linux73'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
src=json.loads((P/'SOURCE_MANIFEST.json').read_text())
for rel,h in src['files'].items():assert sha(P/rel)==h
fixture=ROOT/'outputs/rea/aelita-ethernet73-plan-fixture-20261022T224000Z-r1/result.json';r=json.loads(fixture.read_text());assert r['status']=='PASS_EXTERNAL_EMAC_PLAN_AND_THREE_NEGATIVE_CONTROLS_FAKE_INPUTS'and r['tool_sha256']==sha(P/'build.py')
files={p.relative_to(P).as_posix():sha(p)for p in P.rglob('*')if p.is_file()and '__pycache__'not in p.parts and p.name!='PACKAGE_MANIFEST.json'};assert not any(Path(p).suffix in('.ko','.o','.elf','.bin','.pem','.key','.dts','.dtb')for p in files)
out={'schema':'openmitrastar.aelita-ethernet73-package/v1','status':'PASS_SOURCE_PACKAGE_HASH_COMMENT_PRESERVATION_MOCK_PLAN_CONTROLS_NEW_ABI_BUILD_UNRUN','private':True,'hardware_accessed':False,'Git_mutations':False,'files':files,'source_files':len(src['files']),'mock_plan_cases':4,'mock_plan_receipt_sha256':sha(fixture),'build_on_new_Quantenna_ABI':'UNRUN','reset_overlay':'notincluded;owner-sourceacquisitionpending','DT_and_unit_identity':'excluded','toolchain_binaries':'excluded;TOOLCHAIN_EXTERNAL.json metadataonly','next_action':'Reviewandinclude newpackageinthe privatebranch, prepareexactboard+QuantennaABI kernel thenbuildEMACexternalx2'};(P/'PACKAGE_MANIFEST.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':out['status'],'files':len(files),'manifest_sha256':sha(P/'PACKAGE_MANIFEST.json')}))
