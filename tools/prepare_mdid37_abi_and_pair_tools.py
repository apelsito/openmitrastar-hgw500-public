"""Version immutable weather478 tools for qualified MDID35 parent only."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);abi=ROOT/'tools/witness_hgw5g_weather478_full_abi.py';pair=ROOT/'tools/build_hgw5g_weather478_pair.py';text=abi.read_text();(a.output/'witness-weather37.py').write_text(text);text=pair.read_text();assert "PASS_OFFLINE_CONSOLIDATED32_SCANNER_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT"in text;text=text.replace('PASS_OFFLINE_CONSOLIDATED32_SCANNER_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT','PASS_OFFLINE_CONSOLIDATED35_R3_MDID_FT_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT').replace("a.parent_checkpoint/'input-pins.json'","a.parent_checkpoint/'qualification-input-pins.json'").replace('PASS_WEATHER478_SOURCE34_THREE_UNITS_PAIRED_SEVEN_MODULES_PENDING_GLOBAL','PASS_WEATHER478_SOURCE37_THREE_UNITS_PAIRED_SEVEN_MODULES_PENDING_GLOBAL').replace('exact_parent32_objects_reused','exact_parent35_objects_reused')
 # CurrentbaselinecandidatehasVAP+4, alloldmembers ofcurrent35 unchanged.
 text=text.replace('THREE_FRESH_AND55_QUALIFIED32','THREE_FRESH_AND55_QUALIFIED35')
 (a.output/'build-weather37-pair.py').write_text(text);r={'status':'TOOLS_ONLY_MDID35_WEATHER37_PENDING_ABI_AND_PARENT35_GATE','hardware_accessed':False,'firmware_eligible':False,'pins':{str(x):sha(x)for x in[Path(__file__),abi,pair,a.output/'witness-weather37.py',a.output/'build-weather37-pair.py']}};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
