"""Only new R5 receipt/readback predicates; synthetic inputs are not RF proof."""
import copy,unittest
import f367r5_campaign_worker as w

class Binding(unittest.TestCase):
    def receipt(self):
        return dict(action='activate',exit_code=0,timed_out=False,streams={'stdout':{'lines':[{'text':line} for line in ('OMF367_NATIVE_START_ATTEMPT command=radar-enable-eu authority=1',w.FILTER,w.PUBLICATION,w.STARTED)]}})
    def row(self):
        return dict(target52_present=1,target52_active=1,target52_dfs=1,target52_radar=0,profile_publish_allowed=0,channel=36,filter_bw=80,software_injections=0,nop_active=0,cac_active=0,cac_done=0)
    def test_order_matches_program_not_general_attempt_marker(self):
        self.assertEqual(w.publication_receipt(self.receipt())['publication_count'],1)
        for marker in (w.FILTER,w.PUBLICATION,w.STARTED):
            self.assertEqual(w.capture.redacted_event(marker.encode())['text'],marker)
    def test_missing_duplicate_late_publication_rejected(self):
        for lines in ((w.FILTER,w.STARTED),(w.FILTER,w.PUBLICATION,w.PUBLICATION,w.STARTED),(w.FILTER,w.STARTED,w.PUBLICATION)):
            r=self.receipt();r['streams']['stdout']['lines']=[dict(text=line) for line in lines]
            with self.assertRaises(w.core.Failure):w.publication_receipt(r)
    def test_exact_initial_readback(self):
        self.assertEqual(w.initial_readback(self.row())['status'],'PASS_INITIAL_TARGET52_READBACK')
        for key,value in [('target52_present',0),('target52_active',0),('target52_dfs',0),('target52_radar',1),('target52_dfs',True),('channel',52),('nop_active',1),('cac_active',1)]:
            row=self.row();row[key]=value
            with self.assertRaises(w.core.Failure):w.initial_readback(row)
        row=self.row();row.pop('target52_dfs')
        with self.assertRaises(w.core.Failure):w.initial_readback(row)

if __name__=='__main__':unittest.main()
