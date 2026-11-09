"""Extract established Topaz setup into a NEW F332 backend, no device calls."""
from pathlib import Path
import re,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f327_radar_event_lifecycle/qtn_radar_native_f327_main.c'
DEST=ROOT/'work/kernel-port/modules/f332_dfs_provider/provider/f332_setup.inc'
def function(s,name):
 m=re.search(r'^static [^;{}]+\b'+name+r'\([^;]*?\)\n\{',s,re.M)
 if not m:raise ValueError(name)
 pos=m.end();level=1
 while level:level+=(s[pos]=='{')-(s[pos]=='}');pos+=1
 return s[m.start():pos]
def main():
 if DEST.exists():raise SystemExit('preserve F332 setup snapshot')
 s=SOURCE.read_text();a=s.index('#define F315_MMIO_WINDOW_SIZE');b=s.index('struct f315_batch')
 c=s.index('static struct f315_mmio_window f315_windows');d=s.index('static struct detect_drv_sample_t')
 names=('f315_maps_ready','f315_bb_ready','f315_reg_ptr','f315_read_reg','f315_value_allowed','f315_write_reg','f315_clear_capture_word','f315_apply_iir','f315_clear_capture','f315_configure_hardware','f315_capture_word','f315_map_windows','f315_unmap_windows')
 result='/* F332 setup derived from F327. Used only for explicit initial setup;\n * iterative consume uses the exact separate clear_pt sequence below. */\n'+s[a:b]+s[c:d]+'\n'.join(function(s,n) for n in names)+'\n'
 DEST.write_text(result,newline='\n')
 (DEST.parent/'f332-setup-origin.json').write_text(json.dumps({'source':str(SOURCE),'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'functions':names,'iterative_clear_capture_forbidden':True},indent=2)+'\n')
 print(DEST)
if __name__=='__main__':main()
