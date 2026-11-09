"""Pure negative/positive evidence fixtures. Never operates a device."""
import argparse,copy,json,unittest
from pathlib import Path
from f336_wdt_ram_plan import evaluate,watchdog_inactive

def inactive():
    return dict(source='bootbase-owned-uart',map_value=0,controls=[0,0],counters=[0,0],same_target_and_lease=True,fresh=True)
def trace():
    return dict(baseline=dict(pinned_f321=True,boot_id='baseline',uts_version='#321 pinned'),
        ram=dict(dt_marker='F336_WDT_RAM_ONLY',uts_version='#336 RAM',uart_bound=True,boot_id='ram'),
        fallback_reset_requested=False,probe_events=[dict(event='armed'),dict(event='cease',fd_held=True,program_pets=25),
        dict(event='sample',control='00000001',counter='30000000',since_last_pet_ms=200,program_pets=25,unexplained_counter_increases=0),
        dict(event='sample',control='00000001',counter='20000000',since_last_pet_ms=400,program_pets=25,unexplained_counter_increases=0)],
        last_pet_host_send_ms=1000,last_pet_host_ack_ms=1020,uart_reset_host_ms=9000,uart_reset_observed=True,
        fatal_or_panic_marker=False,post_reset_watchdog=inactive(),
        **{'return':dict(pinned_f321=True,dt_marker_present=False,uts_version='#321 pinned',boot_id='return')})

class Checks(unittest.TestCase):
    def reject(self,t):self.assertEqual(evaluate(t)['status'],'NOT_ACCEPTED')
    def test_valid_synthetic_trace_is_only_evidence(self):
        r=evaluate(trace());self.assertEqual(r['status'],'CESSATION_RESET_AND_F321_RETURN_OBSERVED');self.assertEqual(r['reset_latency_bounds_ms'],[7980,8000])
        for k in ('flash_allowed_by_f336','hardware_reset_cause_verified','full_chip_reset_proven','watchdog_clock_measured','other_producers_excluded_between_samples'):self.assertFalse(r[k])
    def test_missing_fields_rejected(self):self.reject({})
    def test_en_refused(self):
        r=inactive();r['controls']=[0,1];self.assertFalse(watchdog_inactive(r)['watchdog_inactive_observed'])
    def test_map_and_binding_required(self):
        for key,value in [('map_value',None),('map_value','0'),('map_value',1<<29),('fresh',False),('same_target_and_lease',False),('source','unknown')]:
            r=inactive();r[key]=value;self.assertFalse(watchdog_inactive(r)['watchdog_inactive_observed'])
    def test_counter_movement_when_disabled_refused(self):
        r=inactive();r['counters']=[10,9];self.assertFalse(watchdog_inactive(r)['watchdog_inactive_observed'])
    def test_ram_identity_required(self):
        for key,value in [('dt_marker',''),('uts_version','#321'),('boot_id','baseline'),('uart_bound',False)]:
            t=trace();t['ram'][key]=value;self.reject(t)
    def test_software_reset_never_passes(self):
        t=trace();t['fallback_reset_requested']=True;self.reject(t)
    def test_failure_or_close_before_reset_refused(self):
        for event in ['verdict','close_after_verdict']:
            t=trace();t['probe_events'].append(dict(event=event));self.reject(t)
    def test_reload_even_without_reported_flag_refused(self):
        t=trace();t['probe_events'][-1]['counter']='40000000';self.reject(t)
    def test_stuck_counter_refused(self):
        t=trace();t['probe_events'][-1]['counter']='30000000';self.reject(t)
    def test_invalid_counter_or_control_refused(self):
        for key,value in [('counter','garbage'),('control','00000000'),('since_last_pet_ms',-1)]:
            t=trace();t['probe_events'][-1][key]=value;self.reject(t)
    def test_pet_after_cease_refused(self):
        t=trace();t['probe_events'].append(dict(event='pet',program_pets=26));self.reject(t)
    def test_fd_required(self):
        t=trace();t['probe_events'][1]['fd_held']=False;self.reject(t)
    def test_ordered_clock_and_window_required(self):
        for value in [None,float('nan'),500,50000]:
            t=trace();t['uart_reset_host_ms']=value;self.reject(t)
    def test_return_must_be_flash_kernel_new_boot(self):
        for key,value in [('dt_marker_present',True),('uts_version','#336'),('boot_id','ram'),('pinned_f321',False)]:
            t=trace();t['return'][key]=value;self.reject(t)
    def test_postreset_en_blocks(self):
        t=trace();t['post_reset_watchdog']['controls']=[1,1];self.reject(t)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);args=ap.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    args.result.write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),hardware_actions=False),indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
