"""Exactpayloadmappedpaddr-firstMuCderivative withdeclaredvirtualaliases, noHW."""
import argparse,hashlib,json,struct
from pathlib import Path
from qdrv_fw_inspect import inspect_firmware
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);raw=a.source.read_bytes();assert sha(a.source)=='71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4';r=inspect_firmware(raw,source='pinned-ownerMuC',cpu='muc');regions=[]
 for s in r.segments:
  if not s.payload_size:continue
  data=raw[s.payload_offset:s.payload_offset+s.payload_size];regions.append({'name':'.seg'+str(s.index),'index':s.index,'address':s.load_address,'data':data,'flags':6 if s.flags&1 else 2,'authority':'exactpayloadpaddr-firstloaderaddress'})
  if s.virtual_address!=s.load_address and s.index==5:regions.append({'name':'.alias5','index':s.index,'address':s.virtual_address,'data':data,'flags':2,'authority':'DECLAREDvirtualaliasforcrossrefsnotindependenthardwareproof'})
 payload=bytearray(0x1000);strings=b'\0';sections=[(0,)*10];records=[]
 for reg in regions:
  payload.extend(b'\0'*((-len(payload))%4));off=len(payload);payload.extend(reg['data']);nameoff=len(strings);strings+=reg['name'].encode()+b'\0';sections.append((nameoff,1,reg['flags'],reg['address'],off,len(reg['data']),0,0,4,0));records.append({k:v for k,v in reg.items()if k!='data'}|{'offset':off,'bytes':len(reg['data']),'sha256':hashlib.sha256(reg['data']).hexdigest()})
 nameoff=len(strings);strings+=b'.shstrtab\0';stroff=len(payload);payload.extend(strings);sections.append((nameoff,3,0,0,stroff,len(strings),0,0,1,0));payload.extend(b'\0'*((-len(payload))%4));sh=len(payload);payload.extend(b''.join(struct.pack('<10I',*s)for s in sections));payload[:52]=struct.pack('<16sHHIIIIIHHHHHH',raw[:16],2,93,1,r.entry_point,0,sh,0,52,32,0,40,len(sections),len(sections)-1);out=a.output/'muc-LOADED-SEGMENTS-ANALYSIS_ONLY.elf';out.write_bytes(payload);assert sha(a.source)=='71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4';result={'status':'PASS_EXACT_MUC_PAYLOAD_PHYSICAL_LOAD_MAP_ANALYSIS_ONLY','hardware_accessed':False,'firmware_eligible':False,'source_sha256':sha(a.source),'derived_sha256':sha(out),'regions':records,'missing':['LargecodeBSSinitialization notrepresented','Relocationofsegment3virtual80020000 tophysical46e004 notguessed; physicalmaponly','Virtual6003a3c0aliasdeclaredfromELF5header, independentcachealiasproofnotclaimed'],'limits':['Onlyoriginalpayloadbytes unchanged inanalysissections; neverinstall/load','No calibration/device/sharedruntime state accessed','Physicalpaddrprecedence comesfromowningloader; firmwarevirtualcrossreferences mayneedadditionalaliasanalysis']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='regions'}))
if __name__=='__main__':main()
