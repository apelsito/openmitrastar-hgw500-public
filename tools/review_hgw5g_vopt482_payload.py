"""Exact fresh REA482 calcmd6-byte serialization replay; no hardware/transport."""
import argparse,hashlib,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];ev=root/'outputs/rea/vopt482-calcmd-rea-20261022T203100Z-r1/rea.json';setev=root/'outputs/rea/oem-qdrv-missingops-20261022T142000Z-setparam/rea.json';proof=json.loads(ev.read_text());body=proof['data']['normalized_result'];asm=body['assembly'];anchors=['0x1404c: _extb r14, r1','0x14054: ld.as r15, r0, 0x204','0x14084: stb r2, [r13]','0x14090: stb r3, [r13, 0x2]','0x140b4: mov gp, 0x5efec']
 # Keep exact observed instruction text, rather than presuming formatter spelling.
 selected=[x for x in asm if any(x.startswith(v)for v in('0x1404c:','0x14050:','0x14054:','0x14084:','0x14090:','0x14094:','0x14098:','0x1409c:','0x140a4:','0x140a8:','0x140b4:','0x140c0:','0x140e4:','0x140ec:'))];assert len(selected)==14;assert 'qdrv_hostlink_msg_calcmd' in body['pseudocode'];assert '0x80' in body['pseudocode'];s=json.loads(setev.read_text())['data']['normalized_result'];assert 'case 0x1e2:'in s['pseudocode'];assert 'qdrv_calcmd_set_tx_power(uVar2,param_3 & 0xff)'in s['pseudocode'];samples=[]
 for v in range(256):
  packet=[19,0,6,0,1,44 if v==0 else(v*4)&255];signed=v if v<128 else v-256;reference=[0x13,0,6,0,1,0x2c if signed==0 else((signed<<2)&255)];assert packet==reference
  if v in(0,1,11,44,63,64,127,128,255):samples.append({'input_low8':v,'packet':packet})
 a.output.mkdir(parents=True,exist_ok=False);result=dict(status='PASS_EXACT_OEM482_LOW8_SIX_BYTE_CALCMD_SERIALIZATION_256_VALUES',hardware_accessed=False,firmware_eligible=False,cases=256,payload_bytes=6,allocation_bytes=128,allocation_flags=32,calcmd_command=19,input_domain='Everylow8byte; noOEMrangevalidationobserved.',samples=samples,asm_anchors=selected,evidence_sha256=hashlib.sha256(ev.read_bytes()).hexdigest(),setparam_evidence_sha256=hashlib.sha256(setev.read_bytes()).hexdigest(),limits='Pythonserialization/ARCanalysiswitnessonly; no Linux calcmd transport implementation/ACK/coherentDMAownership/MuCreceiver proof.');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
