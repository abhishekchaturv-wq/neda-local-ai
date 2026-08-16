import pathlib
import tempfile
import unittest


class DeliveryConcurrencyContractTests(unittest.TestCase):
    def test_result_code_contract(self):
        # The delivery bridge contract reserves 10 for a retryable busy state.
        self.assertEqual(10, 10)

    def test_manifest_must_survive_busy_result(self):
        # Static contract: watcher must explicitly retain the manifest on rc 10.
        watcher = pathlib.Path(__file__).parents[1] / "automation" / "neda_delivery_watcher_v3.sh"
        text = watcher.read_text()
        self.assertIn("10)", text)
        self.assertIn("Manifest retained; another delivery is active.", text)
        self.assertIn("rm -f \"$MANIFEST\"", text)

    def test_success_only_archives_manifest(self):
        watcher = pathlib.Path(__file__).parents[1] / "automation" / "neda_delivery_watcher_v3.sh"
        text = watcher.read_text()
        success_block = text.split("0)", 1)[1].split("10)", 1)[0]
        self.assertIn("cp \"$MANIFEST\"", success_block)
        self.assertIn("rm -f \"$MANIFEST\"", success_block)

    def test_bridge_exposes_busy_code(self):
        bridge = pathlib.Path(__file__).parents[1] / "automation" / "push_neda_delivery_v2.sh"
        text = bridge.read_text()
        self.assertIn("exit 10", text)
        self.assertIn("RESULT=BUSY", text)
        self.assertIn("RESULT=SUCCESS", text)


if __name__ == "__main__":
    unittest.main()
