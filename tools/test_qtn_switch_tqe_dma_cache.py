import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.c"
MODULE = ROOT / "outputs/kernel-port/qtn-switch-tqe-dma-device-fix-20260821/switch_tqe.ko"
OBJDUMP = os.environ.get(
    "ARC_OBJDUMP",
    "/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/"
    "arc-arc700-linux-uclibc/bin/arc-linux-objdump",
)


class SwitchTqeDmaCacheTest(unittest.TestCase):
    def test_uses_linux510_cache_compat_header(self):
        text = SOURCE.read_text()
        self.assertIn("#include <asm/board/dma_cache_ops.h>", text)
        self.assertNotIn("#include <drivers/ruby/dma_cache_ops.h>", text)

    def test_drop_path_has_no_dma_map_page_attrs(self):
        self.assertTrue(MODULE.is_file())
        module = "/mnt/c" + str(MODULE)[2:].replace("\\", "/")
        disasm = subprocess.check_output(
            ["wsl.exe", OBJDUMP, "-dr", module], text=True
        )
        start = disasm.index("<tqe_rx_pkt_drop>:")
        end = disasm.index("\n\n", start)
        drop = disasm[start:end]
        self.assertIn("dma_cache_inv", drop)
        self.assertNotIn("dma_map_page_attrs", drop)


if __name__ == "__main__":
    unittest.main()
