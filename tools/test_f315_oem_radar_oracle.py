#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(__file__).with_name("f315_oem_radar_oracle.py")
SPEC = importlib.util.spec_from_file_location("f315_oem_radar_oracle", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

RADAR = (
    ROOT
    / "work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/radar/radar.ko"
)
F303 = ROOT / "outputs/kernel-port/f303-oem-radar-re-20260904"


class F315OemRadarOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.elf = MODULE.parse_elf(RADAR)
        cls.functions = MODULE.parse_function_map(F303 / "function-map.tsv")
        cls.instructions = MODULE.parse_disassembly(F303 / "objdump-dr.txt")

    def test_private_oem_input_has_exact_provenance(self):
        result = MODULE.verify_oem_input(RADAR)
        self.assertEqual(result["bytes"], 109112)
        self.assertEqual(result["sha256"], MODULE.EXPECTED_RADAR_SHA256)

    def test_elf_contract_is_arc700_relocatable_without_entrypoint(self):
        self.assertEqual(self.elf["header"]["class"], "ELFCLASS32")
        self.assertEqual(self.elf["header"]["endianness"], "ELFDATA2LSB")
        self.assertEqual(self.elf["header"]["type"], "ET_REL")
        self.assertEqual(self.elf["header"]["machine"], "EM_ARC_COMPACT")
        self.assertEqual(self.elf["header"]["entry"], 0)
        self.assertEqual(self.elf["header"]["flags"], 3)

    def test_section_map_contains_text_data_bss_and_never_embeds_bytes(self):
        sections = {item["name"]: item for item in self.elf["sections"]}
        self.assertEqual(sections[".text"]["size"], 0xCE94)
        self.assertEqual(sections[".bss"]["size"], 0x9458)
        self.assertEqual(sections[".bss"]["initialization"], "zero-fill")
        self.assertNotIn("content", sections[".text"])
        allocated = [item for item in self.elf["sections"] if item["alloc"]]
        for previous, current in zip(allocated, allocated[1:]):
            self.assertLessEqual(previous["proposed_end"], current["proposed_address"])

    def test_relocations_and_imports_are_fully_enumerated(self):
        self.assertEqual(len(self.elf["relocations"]), 2870)
        self.assertEqual(len(self.elf["imports"]), 29)
        self.assertIn("schedule_delayed_work", self.elf["imports"])
        self.assertIn("soc_shared_params", self.elf["imports"])
        self.assertIn("create_proc_entry", self.elf["imports"])

    def test_import_stubs_are_planned_but_not_implemented(self):
        stubs = MODULE.build_import_stubs(self.elf["imports"])
        self.assertFalse(stubs["all_stubs_implemented"])
        self.assertEqual(stubs["relocation_application"], "NOT_IMPLEMENTED")
        categories = {item["symbol"]: item["category"] for item in stubs["stubs"]}
        self.assertEqual(categories["memcpy"], "deterministic-library")
        self.assertEqual(categories["schedule_delayed_work"], "virtual-time")
        self.assertEqual(categories["soc_shared_params"], "fixture-required")

    def test_cfg_is_structural_and_contains_expected_classifier_references(self):
        cfg = MODULE.build_cfg_skeleton(
            self.functions, self.instructions, self.elf["relocations"]
        )
        self.assertEqual(cfg["semantics"], "structural-only")
        functions = {item["name"]: item for item in cfg["functions"]}
        detect = functions["detect_radar"]
        self.assertGreater(detect["instruction_count"], 100)
        self.assertGreater(detect["direct_branch_count"], 10)
        refs = {item["symbol"] for item in detect["relocation_references"]}
        self.assertIn("isit_itlv", refs)
        self.assertIn("lsr_detect", refs)

    def test_known_mmio_constants_are_derived_from_disassembly(self):
        constants = MODULE.extract_constants(
            F303 / "objdump-dr.txt", F303 / "strings-offsets.txt"
        )
        mmio = {item["name"]: item for item in constants["mmio"]}
        self.assertGreater(mmio["QT4_RADAR_CNT_L"]["disassembly_occurrences"], 0)
        self.assertGreater(mmio["QT4_RADAR_MEM_H"]["disassembly_occurrences"], 0)
        self.assertEqual(constants["classifier_threshold_semantics"], "NOT_RECOVERED")

    def test_emulation_audit_fails_closed_without_claiming_equivalence(self):
        stubs = MODULE.build_import_stubs(self.elf["imports"])
        audit = MODULE.audit_emulation(ROOT, self.elf, stubs)
        self.assertEqual(audit["full_oem_execution"], "NOT_VIABLE")
        self.assertEqual(audit["classifier_equivalence"], "NOT_PROVEN")
        self.assertEqual(audit["mode_selected"], "STATIC_ORACLE_FAIL_CLOSED")
        self.assertGreaterEqual(len(audit["blockers"]), 5)

    def test_vector_corpus_contains_only_derived_synthetic_metadata(self):
        corpus = MODULE.build_vector_corpus(F303)
        self.assertGreaterEqual(corpus["vector_count"], 2)
        self.assertFalse(corpus["contains_oem_binary"])
        self.assertFalse(corpus["contains_physical_capture"])
        self.assertEqual(corpus["classification_algorithm"], "NOT_IMPLEMENTED")
        self.assertTrue(all(item["source"] == "synthetic" for item in corpus["vectors"]))

    def test_generated_artifacts_are_reproducible_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_dir = Path(first)
            second_dir = Path(second)
            one = MODULE.generate(ROOT, RADAR, F303, first_dir)
            two = MODULE.generate(ROOT, RADAR, F303, second_dir)
            self.assertEqual(one, two)
            first_files = {p.name: p.read_bytes() for p in first_dir.iterdir() if p.is_file()}
            second_files = {p.name: p.read_bytes() for p in second_dir.iterdir() if p.is_file()}
            self.assertEqual(first_files, second_files)
            provenance = json.loads(first_files["provenance.json"])
            self.assertFalse(provenance["oem_binary_embedded"])
            self.assertFalse(provenance["oem_runtime_retained"])
            self.assertFalse(provenance["inputs"]["radar_ko"]["copied_to_output"])
            audit = json.loads(first_files["oracle-audit.json"])
            self.assertEqual(audit["status"], "PASS_STATIC_ORACLE_FAIL_CLOSED")
            self.assertFalse(audit["claims"]["oem_classifier_executed"])
            self.assertFalse(audit["claims"]["source_equivalence"])
            self.assertFalse(any(path.suffix == ".ko" for path in first_dir.iterdir()))

    def test_cli_require_execution_returns_fail_closed_status(self):
        with tempfile.TemporaryDirectory() as output:
            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--root",
                    str(ROOT),
                    "--output-dir",
                    output,
                    "--require-execution",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 3, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["execution"], "NOT_VIABLE")


if __name__ == "__main__":
    unittest.main()
