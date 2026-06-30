import sys
import unittest
import datetime
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.append("/Users/vgolugur/Documents/Projects/kitecli")

from cli.live_session import KCLILiveSession

class TestCLIParser(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.client = MagicMock()
        self.accounts = [
            {"name": "ZK8719", "api_key": "api_zk", "user_id": "ZK8719"}
        ]
        self.session = KCLILiveSession(self.client, self.accounts)
        self.session.prompt_control = MagicMock()
        self.session.header_control = MagicMock()
        self.session.log_message = MagicMock()

        # Dummy position data
        self.session.last_positions_response = {
            "accounts": [
                {
                    "name": "ZK8719",
                    "api_key": "api_zk",
                    "status": "success",
                    "positions": [
                        {"tradingsymbol": "NIFTY26JUN22200PE", "quantity": -50}
                    ]
                }
            ]
        }
        self.session.active_positions = [
            {"tradingsymbol": "NIFTY26JUN22200PE", "quantity": -50, "api_key": "api_zk", "account_name": "ZK8719"}
        ]
        self.session.position_id_map = {
            1: self.session.active_positions[0]
        }

    @patch("cli.advisor.get_nifty_options", return_value=[])
    async def test_exit_with_symbol_and_price(self, mock_options):
        # exit <symbol> <price>
        self.session._execute_single_command("exit NIFTY26JUN22200PE 1.4")
        self.assertIsNotNone(self.session.pending_order)
        self.assertEqual(self.session.pending_order["type"], "exit")
        self.assertEqual(self.session.pending_order["symbol"], "NIFTY26JUN22200PE")
        self.assertEqual(self.session.pending_order["price"], 1.4)
        
        # Confirming triggers execute_exit with the limit price
        with patch.object(self.session, "execute_exit", return_value=None) as mock_exec:
            self.session._execute_single_command("y")
            mock_exec.assert_called_once_with("NIFTY26JUN22200PE", ["api_zk"], 1.4)

    @patch("cli.advisor.get_nifty_options", return_value=[])
    async def test_exit_all_with_price(self, mock_options):
        # exit all <price>
        self.session._execute_single_command("exit all 2.5")
        self.assertIsNotNone(self.session.pending_order)
        self.assertEqual(self.session.pending_order["type"], "exit")
        self.assertEqual(self.session.pending_order["symbol"], "all")
        self.assertEqual(self.session.pending_order["price"], 2.5)

        with patch.object(self.session, "execute_exit", return_value=None) as mock_exec:
            self.session._execute_single_command("y")
            mock_exec.assert_called_once_with("all", [], 2.5)

    @patch("cli.advisor.get_nifty_options", return_value=[])
    async def test_exit_by_id_with_price(self, mock_options):
        # exit <id> <price>
        self.session._execute_single_command("exit 1 0.75")
        self.assertIsNotNone(self.session.pending_order)
        self.assertEqual(self.session.pending_order["type"], "exit")
        self.assertEqual(self.session.pending_order["symbol"], "NIFTY26JUN22200PE")
        self.assertEqual(self.session.pending_order["price"], 0.75)

        with patch.object(self.session, "execute_exit", return_value=None) as mock_exec:
            self.session._execute_single_command("y")
            mock_exec.assert_called_once_with("NIFTY26JUN22200PE", ["api_zk"], 0.75)

    @patch("cli.advisor.get_nifty_options", return_value=[])
    async def test_standard_exit_no_price(self, mock_options):
        # exit <symbol> (market order fallback)
        self.session._execute_single_command("exit NIFTY26JUN22200PE")
        self.assertIsNotNone(self.session.pending_order)
        self.assertEqual(self.session.pending_order["type"], "exit")
        self.assertEqual(self.session.pending_order["symbol"], "NIFTY26JUN22200PE")
        self.assertIsNone(self.session.pending_order["price"])

        with patch.object(self.session, "execute_exit", return_value=None) as mock_exec:
            self.session._execute_single_command("y")
            mock_exec.assert_called_once_with("NIFTY26JUN22200PE", ["api_zk"], None)

if __name__ == "__main__":
    unittest.main()
