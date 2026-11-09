#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/post_flash_f65_radio_gate.ps1"


class PostFlashF65LowEvidenceTests(unittest.TestCase):
    def test_low_throughput_result_includes_realtek_evidence(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Get-RealtekLowThroughputEvidence", text)
        self.assertIn("Invoke-2gLowThroughputEvidence", text)
        self.assertIn("openmitrastar.realtek-low-throughput-evidence/v1", text)
        self.assertIn("two_g_low_evidence = $twoGLowEvidence", text)
        self.assertIn("PASS_TOPOLOGY_2G_THROUGHPUT_LOW", text)
        self.assertIn("LOW_2G_EVIDENCE_OK", text)
        self.assertIn("Diag2gMbps = 20.0", text)
        self.assertIn("meets_diagnostic", text)
        self.assertIn("diagnostic_Mbps", text)

    def test_realtek_evidence_covers_guard_be_and_rate_markers(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for marker in ("OMRTLQGUARD stage=stop", "OMRTLQGUARD stage=wake", "OMRTLQGUARD stage=reclaim-poll", "OMRTLBE", "OMRTLRA"):
            self.assertIn(marker, text)
        for field in ("queue_status", "rate_status", "rp_progress_observed", "next_action"):
            self.assertIn(field, text)

    def test_low_evidence_is_collected_after_probe_not_only_from_boot_snapshot(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        low_branch = text[text.index('$terminal = "PASS_TOPOLOGY_2G_THROUGHPUT_LOW"') :]
        low_branch = low_branch[: low_branch.index('} else {')]
        self.assertIn("Invoke-2gLowThroughputEvidence", low_branch)
        self.assertNotIn("Get-RealtekLowThroughputEvidence $text", low_branch)

    def test_low_evidence_is_collected_for_subdiagnostic_passes(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        passing_branch = text[text.index('$terminal = "PASS_TOPOLOGY_AND_2G_SPEED"') - 140 :]
        passing_branch = passing_branch[: passing_branch.index('}', passing_branch.index('$terminal = "PASS_TOPOLOGY_AND_2G_SPEED"')) + 1]
        self.assertIn("meets_diagnostic", passing_branch)
        self.assertIn("Invoke-2gLowThroughputEvidence", passing_branch)

    def test_quantenna_5g_result_includes_read_only_evidence(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Get-Quantenna5gEvidence", text)
        self.assertIn("openmitrastar.quantenna-5g-evidence/v1", text)
        self.assertIn("five_g_evidence = $fiveGEvidence", text)
        self.assertIn("SECTION_QTN_NATIVE_CONTROL", text)
        self.assertIn("OMQTN_NATIVE_PRESENT", text)
        self.assertIn("OMQTN_NATIVE_OK", text)
        self.assertIn("iwconfig-qtn wifi0", text)
        self.assertIn("iwpriv-qtn wifi0 get_mode", text)
        self.assertIn("hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping", text)
        self.assertNotIn("call_qcsapi get_status wifi0", text)

    def test_quantenna_5g_classifies_oem_topology_and_failures(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for state in (
            "drivers_not_loaded",
            "drivers_loaded_no_wifi0",
            "wifi0_bridged_not_isolated",
            "native_ap_ready_isolated",
            "native_hostapd_ready_isolated_rf_or_carrier_unproven",
            "wifi0_isolated_native_control_no_hostapd",
            "control_plane_ready_isolated",
            "wifi0_isolated_native_control_unproven",
            "wifi0_present_l3_missing",
            "fatal_marker",
        ):
            self.assertIn(state, text)
        for field in (
            "qdrv_loaded",
            "wlan_loaded",
            "wifi0_present",
            "wifi0_isolated_l3",
            "wifi0_in_br0",
            "qcsapi_ok",
            "native_control_ok",
            "hostapd_qtn_pong",
            "rf_open",
            "wifi0_running",
            "hostapd_wifi0_seen",
            "native_samples",
            "next_action",
        ):
            self.assertIn(field, text)

    def test_quantenna_5g_probe_is_gated_by_2g_speed_pass(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("[switch]$Run5gProbe", text)
        self.assertIn("Invoke-5gAelitaProbe", text)
        self.assertIn("OPENMITRASTAR_QTN_5G_AELITA_ONE_SHOT_RAM_ONLY", text)
        self.assertIn("OPENMITRASTAR_2G_STABLE_FOR_QTN5G", text)
        self.assertIn('$terminal -eq "PASS_TOPOLOGY_AND_2G_SPEED"', text)
        self.assertIn('classification -eq "FIVE_G_AELITA_PASS"', text)
        self.assertIn("requires_2g_speed_pass", text)
        self.assertIn("PASS_TOPOLOGY_2G_SPEED_AND_5G", text)
        self.assertIn("PASS_TOPOLOGY_2G_SPEED_5G_PROBE_FAIL", text)
        self.assertIn("five_g_probe = $fiveGProbe", text)
        for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "saveenv"):
            self.assertNotIn(forbidden, text)

    def test_quantenna_5g_pass_requires_result_marker(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('$pass = ($exitCode -eq 0) -and [bool]$resultFile', text)
        self.assertIn('classification = if ($pass) { "FIVE_G_AELITA_PASS" } else { "FIVE_G_AELITA_FAIL" }', text)

    def test_ssh_keyscan_banner_does_not_fail_gate(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('$previousErrorActionPreference = $ErrorActionPreference', text)
        self.assertIn('$ErrorActionPreference = "Continue"', text)
        self.assertIn('$scanText = & $sshKeyscan -T 5 -t ed25519,rsa $HostAddress 2>&1', text)
        self.assertIn('$ErrorActionPreference = $previousErrorActionPreference', text)
        self.assertIn('Where-Object { $_ -and -not $_.StartsWith("#") }', text)

    def test_complete_ssh_transcript_allows_nonzero_remote_exit(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('$sshTranscriptComplete = $text.Contains("OMF65_GATE_BEGIN") -and $text.Contains("OMF65_GATE_END")', text)
        self.assertIn('$sshExitCode = $proc.ExitCode', text)
        self.assertIn('$sshOk = $sshTranscriptComplete', text)
        self.assertIn('ssh_transport_ok = $sshTranscriptComplete', text)
        self.assertIn('ssh_exit_code = $sshExitCode', text)


if __name__ == "__main__":
    unittest.main()
