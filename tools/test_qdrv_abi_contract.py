import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_SCRIPT = "tools/qdrv_abi_contract/build_qdrv_abi_contract.sh"


def run_build(*extra_flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["wsl", "--exec", "sh", BUILD_SCRIPT, *extra_flags],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class QdrvAbiContractTests(unittest.TestCase):
    def test_arc700_freestanding_contract_builds(self) -> None:
        result = run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("qdrv ABI contract OK", result.stdout)
        self.assertTrue(
            (ROOT / "tools/qdrv_abi_contract/build/qdrv-abi-contract.o").is_file()
        )

    def test_layout_drift_fails_at_compile_time(self) -> None:
        result = run_build("-DQDRV_ABI_EXPECT_SHARED_PARAMS_SIZE=1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("qdrv ABI: sizeof(shared_params)", result.stderr)


if __name__ == "__main__":
    unittest.main()
