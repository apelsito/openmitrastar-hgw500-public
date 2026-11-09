"""Fix the missing one-shot native radar startup without changing F366 inputs."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/f366';DST=ROOT/'work/kernel-port/f366r2'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def once(s,a,b):require(s.count(a)==1,'ambiguous anchor '+a[:80]);return s.replace(a,b,1)
def main():
 require(not (DST/'source-manifest.json').exists(),'immutable F366r2 source exists');DST.mkdir(parents=True,exist_ok=True)
 for sub in ('kernel','uapi','qdrv'):shutil.copytree(SRC/sub,DST/sub,dirs_exist_ok=True)
 p=DST/'qdrv/qdrv/qdrv_control.c';s=p.read_text()
 s=once(s,'static int openmitrastar_sequential_started;','''/* F366r2 is a separately loaded diagnostic profile, never a generic bypass. */
static int openmitrastar_native_radar_diagnostic;
module_param(openmitrastar_native_radar_diagnostic,int,0400);
MODULE_PARM_DESC(openmitrastar_native_radar_diagnostic,"Permit one exact EU native-radar start after the single AP VAP");
static bool f366_native_radar_attempted;
static int openmitrastar_sequential_started;''')
 s=once(s,'\tif (openmitrastar_sequential_started) {','''\tif (openmitrastar_sequential_started) {
  if(openmitrastar_native_radar_diagnostic&&openmitrastar_sequential_vap_created&&
     !f366_native_radar_attempted&&argc==3&&!strcmp(argv[0],"radar")&&
     !strcmp(argv[1],"enable")&&!strcmp(argv[2],"eu"))
   return 0;''')
 s=once(s,'static int qdrv_command_radar(struct device *dev, int argc, char *argv[])\n{','''static int qdrv_command_radar(struct device *dev, int argc, char *argv[])
{
 if(openmitrastar_native_radar_diagnostic&&openmitrastar_sequential_bringup){
  struct qdrv_mac *native_mac=qdrv_control_mac_get(dev,"0");
  struct qdrv_wlan *native_wlan=native_mac?qdrv_control_wlan_get(native_mac):NULL;
  if(!openmitrastar_sequential_started||!openmitrastar_sequential_vap_created||
     f366_native_radar_attempted||argc!=3||strcmp(argv[0],"radar")||
     strcmp(argv[1],"enable")||strcmp(argv[2],"eu"))return -EPERM;
  if(!native_wlan||native_wlan->ic.ic_opmode!=IEEE80211_M_HOSTAP||
     !native_wlan->ic.ic_curchan||native_wlan->ic.ic_curchan==IEEE80211_CHAN_ANYC||
     native_wlan->ic.ic_curchan->ic_ieee!=36||native_wlan->ic.ic_radar_bw!=80)return -EPERM;
  /* Consume before entering the void OEM API, including any startup failure. */
  f366_native_radar_attempted=true;
  pr_info("OMF366_NATIVE_START attempt=1 region=eu authority=diagnostic-profile\\n");
 }''')
 p.write_bytes(s.encode())
 baseline={p.relative_to(SRC).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (SRC/sub).rglob('*') if p.is_file()}
 pins={p.relative_to(DST).as_posix():sha(p) for sub in ('kernel','uapi','qdrv') for p in (DST/sub).rglob('*') if p.is_file()}
 changed=[n for n in pins if baseline.get(n)!=pins[n]];require(changed==['qdrv/qdrv/qdrv_control.c'],'unrelated F366r2 source change')
 report={'schema':'openmitrastar.f366r2-native-start-source/v1','status':'PREPARED_ONE_SHOT_NATIVE_START','source_pins':pins,'baseline_pins':baseline,'changed_files':changed,'hardware_actions':False,'provider_engine_lifetime_unchanged':True,'new_module_parameter':{'name':'openmitrastar_native_radar_diagnostic','default':0,'permissions':'0400'},'command':'radar enable eu','admission':'single core and single AP VAP created; exact command; once per loaded module, even failure'}
 (DST/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source':str(DST),'manifest_sha256':sha(DST/'source-manifest.json')}))
if __name__=='__main__':main()
