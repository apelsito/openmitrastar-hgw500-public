"""Copy-ready conciseprivate R22/R23 reviewdoc binds immutable receipts."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);refs={'R22':'linux73-r22-independent-dma-table-review-20261023T044700Z-r3','R23':'linux73-r23-independent-loader-contract-20261023T045000Z-r1','unaligned':'linux73-r23-loader-unaligned-fixture-20261023T045300Z-r1'};receipts={k:ROOT/'outputs/rea'/v/'result.json'for k,v in refs.items()};r22=json.loads(receipts['R22'].read_text());r23=json.loads(receipts['R23'].read_text());u=json.loads(receipts['unaligned'].read_text());assert r22['table']['records']==610 and r22['exact_original_records']==44;assert r23['actual_fixture_bound_cases']==1321 and u['shifted_carrier_cases']==24
 doc='''# R22/R23: revisión privada del driver Linux7.3 para AELITA

R22 es una base offline reproducible. Su tabla ELF real contiene610 entradas
(14640bytes), con iw_handler_def/count/RELA correctos. Las44 tuplas OEM
cmd/set/get/nombre son exactas y únicas. Esto no aumenta operaciones funcionales
aceptadas: los adaptadores466/468 siguen sin proveedor real de grants/tramas.

La rama DMA SRAM utiliza el pool tipado: alinea la posición física y publica su
bus/map correctos. El key privado de cada asignación evita liberar el winner en
una carrera de preparación. Una negativa al free conserva pool/key en cuarentena;
no hay recuperación automática ni reintento mediante el descriptor público.
61casos de controlDMA32bits y362casos de proveedor con recursos/mapas falsos son
evidencia de código. La reserva real no está registrada y los defaults cierran
la admisión. Layout público20bytes; no prueba de bus/hardware.

R23 añade un preflight del formato empaquetado de los tres carriers seleccionados.
Valida header/phdr/payload, filesz<=memsz y direcciones antes del primer mapa,
y sólo publica el entry tras completar todos los segmentos. 1321casos con
mutaciones y24buffersdesalineados pasan con las funciones reales y helpers de
mapa/CCM falsos. El DSP contiene28bytes finales de etiqueta del linker válidos;
los offsets BSS pueden referirse a payloadanterior. No aplicar las reglas de
congruencia de ELFgenérico a estos carriers empaquetados.

El preflight R23 es estructural. Sus rangos generales DDR/SRAM/CCM no garantizan
autenticidad ni exclusión de escritores en el heap. Fijar hash/CPU/segmentos y
contrato de vida de los carriers es un gate distinto. Fallar el segundo mapa
puede dejar escritura del primero; F355 mantiene la vida parcial y el entry no
se publica. No hay atomicidad del bus ni rollback por esta comprobación.

El catálogo nuevo R22 contiene7165comentarios/724025bytes exactos/178ficheros.
Las fuentes se preservaron. La entrega privada incluye el ledger y la propuesta
SRAM deshabilitada; ningún permiso de hardware o dato privado se deriva de ellos.

Esta revisión no ejecutó MMIO, loader, reset, RF, TX, SSH ni firmware en la placa.
La viabilidad de carga normal, registro exclusivoSRAM, funcionamiento5GHz y
aceptación de release siguen pendientes de sus contratos y gates físicos.
''';(a.output/'R22_R23_REVIEW.md').write_text(doc);pins={str(p):sha(p)for p in[Path(__file__),*receipts.values()]};r={'status':'PASS_PRIVATE_R22_R23_COPY_READY_DOC_BOUND_TO_CURRENT_CODE_AND_RECEIPTS','hardware_accessed':False,'firmware_eligible':False,'pins':pins,'document_sha256':sha(a.output/'R22_R23_REVIEW.md'),'R22_WLAN_pair_sha256':r22['WLAN_pair'][0]['sha256'],'R23_source_sha256':r23['source_sha256'],'preflight_cases':1321,'shifted_buffers':24};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
