"""Only F367 state-machine invariants using explicit synthetic snapshots."""
import copy,unittest
import f367_campaign as gate

def row():
 value={key:0 for key in gate.COMMON}
 value.update(schema='openmitrastar.f367-state/v1',monotonic_ms=1000,channel=36,filter_bw=80,configured=1,region_eu=1,region_es=1,doth=1,tpc=1,provider_present=1,started=1,hardware_ready=1,jobs_completed=1,quarantine_remaining_ms=1800000)
 return value
class CampaignTests(unittest.TestCase):
 def test_quarantine_ready_zero_is_valid_but_dfs_is_not(self):
  state=row();gate.validate(state);state['channel']=52
  with self.assertRaisesRegex(gate.CampaignError,'dfs_during_boot_quarantine'):gate.validate(state)
 def test_cac_requires_ready_continuity_and_no_tx(self):
  state=row();state.update(channel=52,filter_bw=20,quarantine_remaining_ms=0,ready=1,cac_active=1,cac_valid_continuity=1)
  gate.validate(state)
  for key,value in [('ready',0),('cac_valid_continuity',0),('tx_admission',1)]:
   invalid=copy.deepcopy(state);invalid[key]=value
   with self.assertRaises(gate.CampaignError):gate.validate(invalid)
 def test_cac_and_nop_minimum_clocks_are_not_shortened(self):
  for name,minimum in [('cac',70000),('nop',1800000)]:
   state={name+'_started_ms':100,name+'_deadline_ms':minimum+100};gate.timer(state,name,minimum)
   state[name+'_deadline_ms']-=1
   with self.assertRaises(gate.CampaignError):gate.timer(state,name,minimum)
 def test_stale_acquisition_or_native_radar_stops_gate(self):
  previous=row();current=row();current['monotonic_ms']+=5000
  with self.assertRaisesRegex(gate.CampaignError,'acquisition_stalled'):gate.validate(current,previous)
  current['jobs_completed']+=100;current['native_callbacks']=1
  with self.assertRaisesRegex(gate.CampaignError,'unexpected_native_radar_event'):gate.validate(current,previous)
 def test_full_sequence_preserves_simulated_cac_and_nop_deadlines(self):
  class Clock:
   now=0.0
   def read(self):return self.now
   def sleep(self,seconds):self.now+=seconds
  clock=Clock()
  class Host:
   channel=36;bw=80;generation=1;jobs=0;injections=0;cac_start=0;cac_end=0;nop_start=0;nop_end=0;rejections=0
   def activate(self,token):return dict(activated=True)
   def control(self,action,expected_rejection=None):
    if expected_rejection:
     assert action=='enter-dfs' and clock.now*1000<self.nop_end
     self.rejections+=1;return dict(rejected=True,reason=expected_rejection)
    if action=='enter-dfs':
     self.channel=52;self.bw=20;self.generation+=1;self.cac_start=int(clock.now*1000);self.cac_end=self.cac_start+70000
    elif action=='software-radar':
     self.channel=36;self.injections=1;self.nop_start=int(clock.now*1000);self.nop_end=self.nop_start+1800000
    return dict(action=action)
   def snapshot(self):
    clock.sleep(.001);now=int(clock.now*1000);self.jobs+=20
    value=row();value.update(monotonic_ms=now,channel=self.channel,filter_bw=self.bw,generation=self.generation,jobs_completed=self.jobs,
     quarantine_remaining_ms=max(0,1800000-now),ready=int(self.channel==52),cac_active=int(self.channel==52 and now<self.cac_end),
     cac_valid_continuity=int(self.channel==52),cac_done=int(self.channel==52 and now>=self.cac_end),cac_remaining_ms=max(0,self.cac_end-now) if self.channel==52 else 0,
     nop_active=int(now<self.nop_end),nop_remaining_ms=max(0,self.nop_end-now),software_injections=self.injections,
     tx_admission=int(self.channel==52 and now>=self.cac_end),cac_started_ms=self.cac_start,cac_deadline_ms=self.cac_end,
     nop_started_ms=self.nop_start,nop_deadline_ms=self.nop_end)
    return value
  host=Host()
  def client(label,ready):clock.sleep(30);return dict(status='SYNTHETIC_CLIENT',label=label)
  result=gate.Campaign(host,lambda label,data:None,client,clock.read,clock.sleep).run('a'*32)
  self.assertEqual(result['status'],'PASS_F367_DFS_SOFTWARE_CONTROL_AND_CLIENT_TRAFFIC')
  self.assertEqual(host.rejections,2)
  self.assertEqual(result['nop']['duration_ms'],1800000)
  self.assertGreaterEqual(result['second_cac']['timer']['started_ms'],result['nop']['deadline_ms'])
  self.assertEqual(len(result['clients']),2)
  self.assertFalse(result['calibrated_radar_detection_pass'])
if __name__=='__main__':unittest.main()
