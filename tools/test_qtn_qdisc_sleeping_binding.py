#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/sources/Quantenna-GPL/include/qtn/qdrv_sch.h"


class QtnQdiscSleepingBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")

    def test_linux510_nodes_bind_to_installed_qdisc(self) -> None:
        start = self.text.index("qdrv_tx_sch_vap_get_qdisc")
        end = self.text.index("static inline int qdrv_sch_tclass_to_ac", start)
        body = self.text[start:end]
        self.assertIn("LINUX_VERSION_CODE >= KERNEL_VERSION(4, 20, 0)", body)
        self.assertIn("->qdisc_sleeping", body)
        self.assertIn("->qdisc;", body)

    def test_qdrv_logs_the_selected_binding_policy(self) -> None:
        tx = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_tx.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("OMQDRVSCH stage=bind source=qdisc-sleeping", tx)


if __name__ == "__main__":
    unittest.main(verbosity=2)
