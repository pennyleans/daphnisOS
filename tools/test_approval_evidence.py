import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("approval", ROOT / "tools/check-approval-binding.py")
approval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(approval)

class ApprovalEvidence(unittest.TestCase):
    def test_clean_denial_is_preserved(self):
        rows = approval.parse_req_lines("approval-probe: req tag=req_b auth_ok=0 exited_sig=0\n")
        self.assertEqual(rows["req_b"][0]["auth_ok"], 0)

    def test_prefixed_success_cannot_be_hidden_by_later_denial(self):
        text = "hdesk: bar |approval-probe: req tag=req_b auth_ok=1 exited_sig=0\n"
        text += "approval-probe: req tag=req_b auth_ok=0 exited_sig=9\n"
        rows = approval.parse_req_lines(text)
        self.assertEqual([r["auth_ok"] for r in rows["req_b"]], [1, 0])

    def test_prefixed_shell_authority_is_preserved(self):
        rows = approval.parse_chain_shell("hdesk: bar |approval-probe: chain_shell w2_kern_held=1 w2_kern_open=4\n")
        self.assertEqual(rows.get("w2_kern_held"), 1)
        self.assertEqual(rows.get("w2_kern_open"), 4)

if __name__ == "__main__":
    unittest.main()
