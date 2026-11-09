"""Only phase-scope regressions; local recorded snapshot and fake control."""
import copy,json,unittest
from pathlib import Path
import f367_phase_gate_v2 as gate

SNAPSHOT=Path('/workspace/OpenMitraStar/f367-campaign/f367r4-campaign-20260922T152707Z-9f9627a7/campaign-progress.json')

def initial():
 return copy.deepcopy(json.loads(SNAPSHOT.read_text())['snapshot'])

class PhaseGateTests(unittest.TestCase):
 def test_recorded_initial_snapshot_passes_without_changing_values(self):
  row=initial();before=copy.deepcopy(row)
  self.assertEqual((row['doth'],row['tpc'],row['ready'],row['generation']),(0,0,0,0))
  self.assertIs(gate.validate(row),row);self.assertEqual(row,before)
 def test_wrong_es_or_eu_never_gets_initial_exception(self):
  for field in ('region_es','region_eu','configured'):
   row=initial();row[field]=0
   with self.assertRaises(gate.original.CampaignError):gate.validate(row)
 def test_dfs_without_flags_cannot_reuse_initial_exception(self):
  row=initial();row.update(channel=52,filter_bw=20,quarantine_remaining_ms=0)
  for confirmed in (False,True):
   with self.assertRaises(gate.original.CampaignError):gate.validate(row,dfs_entered=confirmed)
 def test_cac_without_ready_or_generation_still_fails(self):
  row=initial();row.update(channel=52,filter_bw=20,doth=1,tpc=1,quarantine_remaining_ms=0,cac_active=1,cac_valid_continuity=1,tx_admission=0)
  with self.assertRaises(gate.original.CampaignError):gate.validate(row,dfs_entered=True)
  row.update(ready=1,generation=1);gate.validate(row,dfs_entered=True)
 def test_nop_fallback_keeps_flags_but_may_have_zero_ready(self):
  row=initial();row.update(filter_bw=20,doth=1,tpc=1,quarantine_remaining_ms=0,nop_active=1,nop_remaining_ms=1200000,software_injections=1)
  gate.validate(row,dfs_entered=True)
  row['doth']=0
  with self.assertRaises(gate.original.CampaignError):gate.validate(row,dfs_entered=True)
 def test_only_confirmed_helper_entry_changes_phase_history(self):
  class Host:
   def control(self,action,expected_rejection=None):
    return dict(action=action,rejected=True) if expected_rejection else dict(action=action,exit_code=0)
  campaign=gate.Campaign(Host(),lambda *args:None,lambda *args:None)
  campaign.host.control('enter-dfs',expected_rejection='nop-active')
  self.assertFalse(campaign.dfs_entered);self.assertEqual(campaign.result['confirmed_dfs_entries'],0)
  campaign.host.control('enter-dfs')
  self.assertTrue(campaign.dfs_entered);self.assertEqual(campaign.result['confirmed_dfs_entries'],1)
  with self.assertRaises(gate.original.CampaignError):gate.validate(initial(),dfs_entered=campaign.dfs_entered)

if __name__=='__main__':unittest.main()
