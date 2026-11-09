"""Record final local cleanup verification without changing retained artifacts."""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import hashlib,json,shutil,subprocess
from cleanup_openmitrastar_storage import ROOT
from plan_openmitrastar_cleanup import sha,FIRMWARE
from bootbase_contract_emulator import validate_bootbase_slot

PRIMARY=ROOT/'outputs/cleanup/executed-20261022T134114956984Z'
DUPLICATES=ROOT/'outputs/cleanup/duplicates-20261022T134632454589Z'
CURRENT=ROOT/'outputs/handoffs/hgw500-linux510-complete-20261022T125241562008Z'

def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 out=ROOT/'outputs/cleanup'/('final-'+stamp);out.mkdir(parents=True,exist_ok=False)
 primary=json.loads((PRIMARY/'result.json').read_text())
 duplicate=json.loads((DUPLICATES/'result.json').read_text())
 pins=json.loads((PRIMARY/'retained-pins.json').read_text());errors=[]
 for row in pins:
  p=Path(row['path'])
  if not p.is_file() or sha(p)!=row['sha256']:errors.append(row['path'])
 assert not errors,'retained source or artifact changed: '+str(errors)
 deleted=json.loads((PRIMARY/'deleted-manifest.json').read_text())
 assert all(not Path(row['path']).exists() for row in deleted),'primary deletion incomplete'
 plan=json.loads((DUPLICATES/'plan.json').read_text())
 duplicates_checked=0
 canonical_hashes={}
 for row in plan['delete']:
  if row['canonical'] not in canonical_hashes:canonical_hashes[row['canonical']]=sha(row['canonical'])
  assert not Path(row['path']).exists() and canonical_hashes[row['canonical']]==row['sha256'],'duplicate verification failure'
  duplicates_checked+=1
 assert primary['errors']==[] and duplicate['errors']==[]
 oem=ROOT/'Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin'
 assert sha(oem)=='f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f'
 archive=CURRENT/'OpenMitraStar-HGW500-Linux510-Handoff.zip'
 assert sha(archive)=='ca3685b195394ae88020757eefe4b5bedf8c690f113aaed975be22ecb0873381'
 images=[]
 for p in sorted(FIRMWARE.glob('*/*.webformat.bin')):
  data=p.read_bytes();contract=validate_bootbase_slot(p.parent.name,data,0x7a0000)
  assert contract.accepted_by_contract,'retained firmware Bootbase contract rejected'
  images.append(dict(version=p.parent.name,path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),bootbase='PASS_OFFLINE'))
 assert len(images)==8,'unexpected retained firmware inventory'
 f372plan=ROOT/'outputs/preflight/f372-install-20261021T195348642022Z/plan.json'
 check=subprocess.run(['python',str(ROOT/'tools/prepare_f372_install.py'),'--plan',str(f372plan),
  '--plan-sha256','a502abe660e7da3e3d561d3f8995ac0d43701cb683e3b03d919d5234e97c25c1'],capture_output=True,text=True,timeout=180)
 (out/'f372-revalidation.stdout').write_text(check.stdout,encoding='utf-8')
 (out/'f372-revalidation.stderr').write_text(check.stderr,encoding='utf-8')
 assert check.returncode==0,'F372 contract revalidation failed'
 totals=defaultdict(lambda:dict(files=0,bytes=0))
 for row in deleted+plan['delete']:
  d=Path(row['path']).drive.upper();totals[d]['files']+=1;totals[d]['bytes']+=row['bytes']
 status=dict(schema='openmitrastar.cleanup-final/v1',status='PASS_LOCAL_CLEANUP_VERIFIED',created_utc=stamp,
  hardware_actions=False,totals=dict(totals),deleted_files=sum(x['files'] for x in totals.values()),
  deleted_bytes=sum(x['bytes'] for x in totals.values()),retained_pins_verified=len(pins),retained_pins_unchanged=True,
  duplicates_canonical_verified=duplicates_checked,firmware_images=images,oem=dict(path=str(oem),sha256=sha(oem),bytes=oem.stat().st_size),
  current_handoff=dict(path=str(archive),sha256=sha(archive),bytes=archive.stat().st_size),
  f372_contract='PASS_OFFLINE_CONTRACT_PHYSICAL_NO_GO',
  primary_report=str(PRIMARY/'result.json'),duplicate_report=str(DUPLICATES/'result.json'),
  historical_objective_audit=str(PRIMARY/'objective-audit.json'),
  resolved_intermediate_failure='Audit helper temporarily gained an optional output argument, then was restored to its exact original hash. All retained pins now pass.',
  volumes={d:dict(shutil.disk_usage(d+'/')._asdict()) for d in ('C:','D:')})
 (out/'result.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
 lines=['# Limpieza local OpenMitraStar — 22 de octubre de 2026','',
  f"Eliminados **{status['deleted_bytes']/1e9:.2f} GB** de archivos históricos y duplicados ({status['deleted_files']:,} archivos).",
  '', '| Unidad | Archivos eliminados | GB de archivos |', '|---|---:|---:|']
 for d,v in totals.items():lines.append(f"| {d} | {v['files']:,} | {v['bytes']/1e9:.2f} |")
 lines+=['','Conservados: firmware OEM, volcados originales, identidad/calibración, fuentes, herramientas y toolchain, recuperación exacta F314/F365, firmware F367r9 registrado como instalado, candidatos F369/F371/F372 y sus dependencias F364r3/F367r8. Se conserva la entrega técnica actual.',
  '',f"Se han verificado {len(pins):,} archivos fijados sin cambios y {duplicates_checked:,} copias canónicas. Las 8 imágenes completas conservadas pasan su contrato Bootbase offline. El contrato F372 vuelve a pasar con NO_GO físico.",
  '', 'Los registros antiguos de resultados y manifiestos se conservan como evidencia histórica. Sus rutas pueden referirse a binarios eliminados; la existencia de un manifiesto no acredita que el firmware siga disponible.',
  '', 'No se ha accedido al router, abierto UART, reiniciado, flasheado ni cambiado su configuración. Tampoco se ha modificado el desarrollo activo ni los proyectos de otros routers.',
  '', 'El espacio físico recuperado puede diferir de los bytes de archivo por compresión, enlaces duros y compilaciones simultáneas. El borrado principal aumentó el espacio libre de C de 13,79 GB a 35,03 GB; D tuvo escrituras simultáneas del desarrollo.',
  '', '## Imágenes conservadas', '', '| Imagen | Bytes | Motivo |','|---|---:|---|']
 reasons={'f314':'Recuperación histórica exacta','f364r3':'Dependencia fijada de F365','f365':'Recuperación y driver activo en RAM según registros','f367r8':'Dependencia fijada de F367r9','f367r9':'Firmware vigente según evidencia local de hoy','f369':'Candidato de cuarentena','f371':'Donante exacto de F372','f372':'Candidato actual de observación'}
 for row in images:
  reason=next(v for k,v in sorted(reasons.items(),key=lambda x:-len(x[0])) if row['version'].startswith(k))
  lines.append(f"| {row['version']} | {row['bytes']:,} | {reason} |")
 lines+=['','## Evidencia','',f'- Resultado final: `{out / "result.json"}`',f'- Manifiesto de borrado: `{PRIMARY / "deleted-manifest.json"}`',f'- Duplicados y copias conservadas: `{DUPLICATES / "plan.json"}`',f'- Auditoría histórica F314–F319: `{PRIMARY / "objective-audit.json"}`','']
 (out/'LIMPIEZA.md').write_text('\n'.join(lines),encoding='utf-8')
 (ROOT/'docs/OPENMITRASTAR_CLEANUP_20261022.md').write_text('\n'.join(lines),encoding='utf-8')
 print(json.dumps(dict(output=str(out),status=status['status'],totals=dict(totals),deleted_bytes=status['deleted_bytes'],deleted_files=status['deleted_files'],pins=len(pins),firmware_images=len(images),hardware_actions=False)),flush=True)

if __name__=='__main__':main()
