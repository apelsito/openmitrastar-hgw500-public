import importlib.util
import pathlib
import struct
import unittest
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "verify_topaz_recovery_env.py"
SPEC = importlib.util.spec_from_file_location("recovery_env", MODULE_PATH)
assert SPEC and SPEC.loader
recovery_env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery_env)


def make_env(selector="0", command="bootselect", extra=""):
    suffix = f"{extra}\0" if extra else ""
    entries = f"bootcmd={command}\0bootselect={selector}\0{suffix}\0".encode()
    data = entries.ljust(recovery_env.ENV_DATA_SIZE - 4, b"\xff")
    return struct.pack("<I", zlib.crc32(data) & 0xFFFFFFFF) + data


class RecoveryEnvironmentTests(unittest.TestCase):
    def test_valid_redundant_live_fallback(self):
        blob = make_env()
        parsed = recovery_env.verify_contract(blob, blob)
        self.assertEqual(parsed["bootselect"], "0")

    def test_rejects_safety_loop(self):
        blob = make_env(selector="1")
        with self.assertRaisesRegex(ValueError, "live slot"):
            recovery_env.verify_contract(blob, blob)

    def test_rejects_crc_corruption(self):
        blob = bytearray(make_env())
        blob[20] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            recovery_env.verify_contract(bytes(blob), bytes(blob))

    def test_rejects_unsafe_backup(self):
        with self.assertRaisesRegex(ValueError, "backup bootcmd"):
            recovery_env.verify_contract(make_env(), make_env(command="false"))

    def test_allows_harmless_one_shot_variable_only_in_primary(self):
        primary = make_env(extra="trial_once=setenv bootselect 0; saveenv")
        parsed = recovery_env.verify_contract(primary, make_env())
        self.assertIn("trial_once", parsed)


class RecoverySourceSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.init = (ROOT / "work/kernel-port/initramfs/recovery_init.c").read_text()
        cls.driver = (ROOT / "work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c").read_text()
        cls.dts = (ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_recovery.dts").read_text()

    def test_initramfs_flash_access_is_read_only(self):
        self.assertIn("O_RDONLY", self.init)
        self.assertNotIn("O_RDWR", self.init)
        self.assertNotIn("O_WRONLY", self.init.replace('open(LED_PATH, O_WRONLY', ''))
        self.assertNotIn("MEMERASE", self.init)

    def test_dts_marks_both_env_copies_read_only(self):
        self.assertEqual(self.dts.count("read-only;"), 2)
        self.assertIn('compatible = "mtd-rom"', self.dts)
        self.assertIn("qtn,recovery-led-pin = <7>", self.dts)

    def test_driver_has_no_spi_or_flash_registers(self):
        lowered = self.driver.lower()
        self.assertNotIn("spi_", lowered)
        self.assertNotIn("mtd", lowered)
        self.assertIn("register_restart_handler", self.driver)


if __name__ == "__main__":
    unittest.main()
