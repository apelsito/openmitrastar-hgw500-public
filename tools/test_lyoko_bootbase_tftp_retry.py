#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1"
ONESHOT = ROOT / "tools/run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"


class LyokoBootbaseTftpRetryTests(unittest.TestCase):
    def test_network_probe_precedes_tftp_without_blocking_it(self) -> None:
        text = BACKEND.read_text(encoding="utf-8")
        self.assertIn("function Wait-BootbaseNetwork", text)
        self.assertIn("function Receive-CandidateTftp", text)
        network = text.index("[void](Wait-BootbaseNetwork $ServerIp)\n")
        transfer = text.index("Receive-CandidateTftp\n", network)
        erase = text.index("spi_flash erase", transfer)
        self.assertLess(network, transfer)
        self.assertLess(transfer, erase)
        self.assertIn("OMLYOKO_TFTP_RETRY", text)
        self.assertIn("OMLYOKO_BOOTBASE_NETWORK_UNCONFIRMED", text)
        self.assertIn("proceeding=tftpboot", text)
        self.assertNotIn('throw "Bootbase cannot reach TFTP server', text)

    def test_tftp_log_is_written_from_finally(self) -> None:
        text = ONESHOT.read_text(encoding="utf-8")
        finally_block = text[text.index("    finally:"):]
        self.assertIn('tftp_log.write_text(tftp_output, encoding="utf-8")', finally_block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
