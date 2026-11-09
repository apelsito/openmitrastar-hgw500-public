"""Create the F341 telemetry/diagnostic copy without changing sealed F338."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f338';DST=ROOT/'work/kernel-port/f341'
def main():
 if DST.exists():raise SystemExit('F341 source already exists; do not reseed')
 rows={}
 for sub in ('kernel','userspace','uapi'):
  (DST/sub).mkdir(parents=True)
  for p in (SRC/sub).iterdir():
   if not p.is_file():continue
   data=p.read_bytes();rows[str(p.relative_to(SRC))]=hashlib.sha256(data).hexdigest()
   text=data.decode()
   if sub=='kernel':
    text=text.replace('qtn_radar_f338','qtn_radar_f341').replace('openmitrastar_radar_f338','openmitrastar_radar_f341').replace('OMF338','OMF341')
   (DST/sub/p.name).write_bytes(text.encode())
 (DST/'F338-source-binding.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':main()
