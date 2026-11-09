from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=ROOT/'tools/test_f344_gate.py';s=p.read_text()
 s=s.replace('#include "f344_mode_gate.h"','#include "f344_mode_gate.h"\n#include "f344_csa_state.h"')
 s=s.replace('struct ieee80211vap{int iv_opmode;bool extender;};','struct ieee80211vap{int iv_opmode;bool extender;unsigned iv_flags_ext;};')
 s=s.replace('struct ieee80211com{bool repeater;unsigned ic_phytype;};','''struct ieee80211com{bool repeater;unsigned ic_phytype,ic_csa_count,ic_flags,ic_f344_hardware_generation;int ic_timer_csa;};
#define IEEE80211_FEXT_WDS 1
#define IEEE80211_F_CHANSWITCH 2
#define QTN_CSA_STATUS_LHOST_ACTIVE 32
#define QTN_CSA_STATUS_MUC_COMPLETE 64
#define BW_HT20 20
#define BW_HT40 40
#define BW_HT80 80
#define READ_ONCE(x) (x)
#define spin_lock_irqsave(lock,flags) do{(void)(lock);(flags)=0;}while(0)
#define spin_unlock_irqrestore(lock,flags) do{(void)(lock);(void)(flags);}while(0)
static unsigned f344_policy_lock;
static struct f344_csa_state f344_policy={.generation=1,.hold=true,.drained=true};
struct csa{unsigned lhost_status,muc_status;};struct shared_params{struct csa*csa_lhost;};
static struct csa csa;static struct shared_params shared={&csa};
static struct shared_params*qtn_mproc_sync_shared_params_get(void){return &shared;}
static bool timer_pending(int*t){return !!*t;}
static unsigned ieee80211_f344_policy_abi_v1(void){return sizeof(struct ieee80211com);}
static unsigned ieee80211_get_bw(struct ieee80211com*ic){(void)ic;return 80;}
''')
 s=s.replace('struct qdrv_wlan{struct ieee80211com ic;unsigned flags_ext;};','struct qdrv_wlan{struct ieee80211com ic;unsigned flags_ext,csa_lock;};')
 s=s.replace("for name in ('f344_mode_gate.c','f344_mode_gate.h')","for name in ('f344_mode_gate.c','f344_mode_gate.h','f344_csa_state.h')")
 p.write_bytes(s.encode())
 (ROOT/'work/linux510-radio-port/quantenna-f344-modes/qdrv/f344_mode_gate.c').write_bytes((ROOT/'work/kernel-port/f344/f344_mode_gate.c').read_bytes())
if __name__=='__main__':main()
