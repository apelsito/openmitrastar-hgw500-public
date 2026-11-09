#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

from qtn_qdrv_abi_diff import build_report


ROOT = Path(__file__).resolve().parents[1]


class QdrvAbiDiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = build_report()

    def test_shared_memory_differences_are_exact(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        self.assertEqual((rows["sizeof(shared_params)"]["v62"], rows["sizeof(shared_params)"]["v89"]), (384, 400))
        self.assertEqual((rows["shared_params.auc"]["v62"], rows["shared_params.auc"]["v89"]), (276, 280))
        self.assertEqual(rows["shared_params.fw_no_mu"]["v89"], 76)
        self.assertEqual(rows["shared_params.nac_mon_info_lhost"]["v89"], 388)
        self.assertEqual(rows["shared_params.nac_mon_info_bus"]["v89"], 392)
        self.assertEqual((rows["sizeof(qtn_txbf_mbox)"]["v62"], rows["sizeof(qtn_txbf_mbox)"]["v89"]), (4512, 4528))
        self.assertEqual((rows["sizeof(qtn_muc_dsp_mbox)"]["v62"], rows["sizeof(qtn_muc_dsp_mbox)"]["v89"]), (2080, 2144))
        self.assertEqual((rows["sizeof(_shared_params_alloc)"]["v62"], rows["sizeof(_shared_params_alloc)"]["v89"]), (23552, 30624))

    def test_unchanged_auc_stats_contract(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        for key in (
            "shared_params_auc.node_stats",
            "shared_params_auc.vap_stats",
            "sizeof(qtn_shared_node_stats_t)",
            "sizeof(qtn_shared_vap_stats_t)",
            "sizeof(shared_params_auc)",
            "sizeof(host_ioctl)",
            "sizeof(qtn_vap_args)",
            "sizeof(qtn_node_args)",
        ):
            self.assertEqual(rows[key]["v62"], rows[key]["v89"])

    def test_oem_exports_are_preserved_additively(self) -> None:
        exports = self.report["exports"]
        self.assertEqual(exports["oem_only"], [])
        self.assertEqual(exports["port_only"], ["qtn_async_cca_read"])
        self.assertIn("qdrv_async_cca_read", exports["common"])

    def test_v89_sample_channel_contract_is_closed_fail_closed(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        self.assertEqual(rows["qtn_samp.control_flags"]["v89"], 16)
        self.assertEqual(rows["qtn_samp.result"]["v89"], 28)
        self.assertEqual(rows["qtn_samp.type"]["v89"], 56)
        header = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h").read_text(encoding="utf-8")
        self.assertIn("QDRV_V89_SAMP_RUNTIME_APPROVED\t0", header)
        self.assertIn("return -EOPNOTSUPP;", header)

    def test_v89_remain_channel_contract_is_closed_fail_closed(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        self.assertEqual(rows["qtn_remain.flags"]["v89"], 12)
        self.assertEqual(rows["qtn_remain.duration_usecs"]["v89"], 24)
        self.assertEqual(rows["qtn_remain.status"]["v89"], 28)
        self.assertEqual(rows["qtn_remain.peer_mac"]["v89"], 32)
        header = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h").read_text(encoding="utf-8")
        self.assertIn("qdrv_v89_remain_init", header)

    def test_v89_nac_contract_is_closed_with_opaque_tail(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        expected_offsets = {
            "qtn_nac_mon_info.config_value0": 0,
            "qtn_nac_mon_info.config_value1": 2,
            "qtn_nac_mon_info.enabled": 4,
            "qtn_nac_mon_info.entries": 8,
            "qtn_nac_mon_info.opaque_tail": 2568,
            "qtn_nac_mon_entry.valid": 0,
            "qtn_nac_mon_entry.rssi_db": 1,
            "qtn_nac_mon_entry.channel": 2,
            "qtn_nac_mon_entry.packet_type": 3,
            "qtn_nac_mon_entry.timestamp": 4,
            "qtn_nac_mon_entry.mac_addr": 12,
        }
        for key, offset in expected_offsets.items():
            with self.subTest(key=key):
                self.assertEqual(rows[key]["v89"], offset)
        contract = self.report["nac_contract"]
        self.assertEqual(contract["classification"], "PROVEN_LAYOUT_OPAQUE_TAIL")
        self.assertEqual(contract["allocation_size"], 2596)
        self.assertEqual(contract["entry_count"], 128)
        self.assertEqual(contract["entry_size"], 20)
        self.assertEqual(contract["opaque_tail_size"], 28)
        self.assertIn("Mac Address", contract["oem_strings"]["heading"])
        self.assertEqual(contract["oem_strings"]["control"], "Control")
        self.assertEqual(contract["oem_strings"]["data"], "Data")
        self.assertEqual(contract["oem_strings"]["management"], "Management")
        header = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h").read_text(encoding="utf-8")
        self.assertIn("QDRV_V89_NAC_RUNTIME_APPROVED\t0", header)
        self.assertIn("qdrv_v89_nac_info_init", header)
        self.assertIn("return -EOPNOTSUPP;", header)

    def test_v89_txbf_algorithm_tail_subblock_is_closed(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        expected = {
            "qtn_txbf.ranking_algorithm_to_use": 0x1190,
            "qtn_txbf.precoding_algorithm_to_use": 0x1194,
            "qtn_txbf.rank_criteria_to_use": 0x1198,
            "qtn_txbf.mu_prec_cache_max_time": 0x119C,
            "qtn_txbf.mu_rank_tolerance": 0x11A0,
            "qtn_txbf.opaque_extension": 0x11A4,
        }
        for key, offset in expected.items():
            with self.subTest(key=key):
                self.assertEqual(rows[key]["v89"], offset)
        contract = self.report["txbf_algo_tail_contract"]
        self.assertEqual(
            contract["classification"], "PROVEN_SUBBLOCK_OPAQUE_EXTENSION"
        )
        self.assertEqual(contract["tail_offset"], 0x1190)
        self.assertEqual(contract["tail_size"], 32)
        self.assertEqual(contract["opaque_extension_size"], 12)
        self.assertEqual(contract["rank_criteria_label"], "mu rank criteria")
        self.assertFalse(contract["full_mailbox_closed"])
        header = (
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h"
        ).read_text(encoding="utf-8")
        self.assertIn("QDRV_V89_TXBF_RUNTIME_APPROVED\t0", header)
        self.assertIn("qdrv_v89_txbf_tail_init", header)

    def test_v89_txbf_dsp_stats_insertion_is_bounded_but_opaque(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        self.assertEqual(rows["qtn_txbf.dsp_stats.opaque_word"]["v89"], 0x1074)
        self.assertEqual(rows["qtn_txbf.dsp_stats.dsp_sram_qmat_num"]["v89"], 0x1078)
        self.assertEqual(rows["qtn_txbf.dsp_stats.dsp_flag"]["v89"], 0x1080)
        contract = self.report["txbf_dsp_stats_contract"]
        self.assertEqual(contract["classification"], "PROVEN_ZERO_INITIALIZED_OPAQUE_BYTES")
        self.assertFalse(contract["full_stats_closed"])
        header = (
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h"
        ).read_text(encoding="utf-8")
        self.assertIn("opaque_after_dsp_qmat_invalid", header)
        self.assertIn("qdrv_v89_dsp_qmat_stats_init", header)

    def test_v89_full_txbf_wire_layout_is_closed_but_pair_remains_no_go(self) -> None:
        contract = self.report["txbf_full_contract"]
        self.assertEqual(contract["mailbox_size"], 0x11B0)
        self.assertEqual(contract["opaque_qmat_offset"], 0x1074)
        self.assertEqual(contract["opaque_tail_offset"], 0x11A4)
        self.assertTrue(contract["host_allocation_zeroed_before_uc_start"])
        self.assertFalse(contract["opaque_bytes_have_producer"])
        self.assertFalse(contract["opaque_bytes_have_consumer"])
        self.assertTrue(contract["layout_approved"])
        self.assertTrue(contract["runtime_publisher_integrated"])
        self.assertEqual(
            contract["w3_pair_decision"],
            "PAIR_SIGNED_HARDWARE_ACTIVE_NO_GO",
        )
        header = (
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h"
        ).read_text(encoding="utf-8")
        self.assertIn("QDRV_V89_TXBF_LAYOUT_APPROVED\t1", header)
        self.assertIn("struct qtn_txbf_mbox_v89", header)
        self.assertIn("qdrv_v89_txbf_mbox_init", header)

    def test_v89_shared_publisher_is_staged_and_fail_closed(self) -> None:
        contract = self.report["shared_publisher_contract"]
        self.assertEqual(contract["allocation_size"], 0x77A0)
        self.assertEqual(contract["txbf_offset"], 0x190)
        self.assertEqual(contract["nac_offset"], 0x6D7C)
        self.assertEqual(contract["gated_host_version"], 0x25040059)
        self.assertTrue(contract["production_qdrv_soc_init_integrated"])
        self.assertTrue(contract["w3_pair_approved"])

    def test_v89_muc_dsp_is_ring32_plus_special_slot_fail_closed(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        self.assertEqual(rows["qtn_muc_dsp_mbox.ring_count"]["v89"], 32)
        self.assertEqual(rows["qtn_muc_dsp_mbox.special_slot"]["v89"], 0x820)
        contract = self.report["muc_dsp_mbox_contract"]
        self.assertEqual(contract["classification"], "PROVEN_RING32_PLUS_SPECIAL_SLOT")
        self.assertEqual(contract["mailbox_size"], 0x860)
        self.assertEqual(contract["special_index"], 0xFF)
        header = (
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h"
        ).read_text(encoding="utf-8")
        self.assertIn("QDRV_V89_MUC_DSP_RUNTIME_APPROVED 0", header)
        self.assertIn("qdrv_v89_muc_dsp_mbox_init", header)

    def test_v89_scs_layout_is_closed(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        self.assertEqual(rows["qtn_scs.oc_info_count"]["v89"], 32)
        self.assertEqual(rows["sizeof(qtn_scs_oc_info)"]["v89"], 0x30)
        self.assertEqual(rows["qtn_scs.history_count"]["v89"], 43)
        self.assertEqual(rows["sizeof(qtn_scs_info)"]["v89"], 0x6C8)
        self.assertEqual(rows["sizeof(qtn_scs_scan_info)"]["v89"], 0x34)
        self.assertEqual(rows["qtn_scs_info_set.scan_info"]["v89"], 0xD94)
        self.assertEqual(rows["qtn_scs_info_set.stats_history"]["v89"], 0x4160)
        contract = self.report["scs_info_set_contract"]
        self.assertEqual(contract["classification"], "PROVEN_COMPLETE_LAYOUT")
        self.assertEqual(contract["container_size"], 0x4970)
        self.assertEqual(contract["scan_cca_pri_offset"], 0x18)
        self.assertEqual(contract["history_count"], 43)
        header = (
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h"
        ).read_text(encoding="utf-8")
        self.assertIn("QDRV_V89_SCS_RUNTIME_APPROVED\t0", header)
        self.assertIn("qdrv_v89_scs_info_set_init", header)

    def test_v89_scan_layout_is_closed_with_opaque_byte20_extension(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        self.assertEqual(rows["qtn_scan.opaque_at_0x14"]["v89"], 20)
        self.assertEqual(rows["qtn_scan.start_txdesc_host"]["v89"], 24)
        self.assertEqual(rows["qtn_scan.tsf"]["v89"], 60)
        contract = self.report["scan_chan_contract"]
        self.assertEqual(contract["classification"], "PROVEN_LAYOUT_OPAQUE_EXTENSION")
        self.assertEqual(contract["opaque_size"], 4)
        header = (
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h"
        ).read_text(encoding="utf-8")
        self.assertIn("QDRV_V89_SCAN_RUNTIME_APPROVED\t0", header)
        self.assertIn("qdrv_v89_scan_chan_init", header)

    def test_vap_transport_slack_is_not_an_abi_field(self) -> None:
        rows = {row["item"]: row for row in self.report["structures"]}
        self.assertEqual(rows["sizeof(qtn_vap_args)"]["v62"], 24)
        self.assertEqual(rows["sizeof(qtn_vap_args)"]["v89"], 24)
        header = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h").read_text(encoding="utf-8")
        self.assertIn("QDRV_V89_VAP_PAYLOAD_SIZE\t24", header)
        self.assertIn("QDRV_V89_VAP_TRANSFER_SIZE\t25", header)

    def test_private_ioctl_table_is_backward_compatible(self) -> None:
        ioctls = self.report["private_ioctls"]
        self.assertEqual(ioctls["oem_count"], 134)
        self.assertEqual(ioctls["port_count"], 135)
        self.assertEqual(ioctls["oem_only"], [])
        self.assertEqual(ioctls["port_only"], [{"cmd": 0x11, "set_args": 0x4801, "get_args": 0, "name": "maccmd"}])

    def test_module_parameter_and_runtime_gates(self) -> None:
        self.assertTrue(self.report["module_parameters"]["equal"])
        self.assertEqual(self.report["module_parameters"]["oem"], ["tqe_sem_en:int"])
        self.assertEqual(self.report["runtime_gate"]["W3_PAIR_APPROVED"], "1")
        self.assertEqual(self.report["runtime_gate"]["W3_HARDWARE_ACTIVE_APPROVED"], "0")
        self.assertEqual(self.report["versions"]["port_encoded"], 0x2504003E)
        self.assertEqual(self.report["versions"]["oem_encoded"], 0x25040059)

    def test_fw_no_mu_is_host_local_until_v89_layout_closes(self) -> None:
        control = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_control.c").read_text(encoding="utf-8")
        qcb = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_soc.h").read_text(encoding="utf-8")
        shared = (ROOT / "work/sources/Quantenna-GPL/include/qtn/shared_params.h").read_text(encoding="utf-8")
        publish = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_soc.c").read_text(encoding="utf-8")
        self.assertIn('"fw_no_mu", P_FL_TYPE_INT', control)
        self.assertIn("u32 fw_no_mu;", qcb)
        self.assertIn("#ifdef OPENMITRASTAR_QDRV_V89_PAIR", shared)
        self.assertIn("fw_no_mu", shared)
        self.assertIn("soc_shared_params->fw_no_mu = qcb->fw_no_mu", publish)


if __name__ == "__main__":
    unittest.main(verbosity=2)
