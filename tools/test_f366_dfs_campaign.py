"""Offline adversarial evidence-parser checks; no physical/RF claim."""
import json
import unittest

import f366_dfs_campaign as campaign


def fixture():
    rows = []
    for index in range(20):
        status = {key: 0 for key in campaign.NUMERIC_FIELDS}
        status.update(schema="openmitrastar.f366-status/v1", provider_present=True,
                      hardware_enabled=1, hardware_ready=1, hardware_dirty=1,
                      started=1, postfilter_applied=1, channel=36,
                      jobs_completed=index+1, polls=index+1, ipc_sequence=index+1,
                      ipc_session=1, ipc_generation=1)
        rows.append("OMF366_STATUS index=" + str(index) + " json=" + json.dumps(status))
    rows.append("OMF366_DIAGNOSTIC_COMPLETE observations=20 jobs_delta=20 authority=0 hardware_quiesced=0 reboot_required=1")
    return "\n".join(rows)


class CampaignTests(unittest.TestCase):
    def test_synthetic_diagnostic_is_never_rf_pass(self):
        result = campaign.review_transcript(fixture())
        self.assertEqual(result["failures"], [])
        for key in ("hardware_execution", "physical_evidence_authenticated", "dfs_authority", "rf_detection_pass", "client_pass", "traffic_pass", "release_pass"):
            self.assertIs(result[key], False)

    def test_duplicate_index_and_json_rejected(self):
        self.assertTrue(campaign.review_transcript(fixture().replace("index=1 ", "index=0 "))["failures"])
        text = fixture().replace('"callbacks": 0', '"callbacks": 0, "callbacks": 0', 1)
        self.assertIn("invalid_or_duplicate_status_json", campaign.review_transcript(text)["failures"])

    def test_missing_truncated_and_repeated_completion_rejected(self):
        text = fixture()
        for invalid in ("", text.rsplit("\n", 1)[0], text + "\n" + text.splitlines()[-1], text.replace("json={", "json=", 1)):
            self.assertTrue(campaign.review_transcript(invalid)["failures"])

    def test_faults_callback_or_channel_change_rejected(self):
        for before, after in (("\"callbacks\": 0", "\"callbacks\": 1"), ("\"job_timeouts\": 0", "\"job_timeouts\": 1"), ("\"channel\": 36", "\"channel\": 100")):
            self.assertTrue(campaign.review_transcript(fixture().replace(before, after, 1))["failures"])

    def test_boolean_counter_or_counter_regression_rejected(self):
        for invalid in (fixture().replace('"jobs_completed": 10', '"jobs_completed": true'), fixture().replace('"jobs_completed": 10', '"jobs_completed": 0')):
            self.assertTrue(campaign.review_transcript(invalid)["failures"])

    def test_plan_preserves_timers_and_authority_boundary(self):
        plan = campaign.plan()
        self.assertIsNone(plan["artifact_binding"])
        self.assertEqual(plan["first_gate"]["authority"], 0)
        cases = plan["later_dfs_steps"][2]["cases"]
        self.assertEqual([case["cac_seconds_minimum"] for case in cases], [70, 70, 600, 70, 70])
        self.assertTrue(all(case["non_occupancy_seconds"] == 1800 for case in cases))
        self.assertEqual(cases[2]["occupied_20mhz_channels"], [116, 120, 124, 128])
        self.assertFalse(campaign.classify_channel(140, 80)["valid"])


if __name__ == "__main__":
    unittest.main()
