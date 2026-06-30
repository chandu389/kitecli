import sys
import unittest
import datetime
import asyncio
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.append("/Users/vgolugur/Documents/Projects/kitecli")

from cli.live_session import KCLILiveSession

class TestNLIParsing(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.client = MagicMock()
        self.accounts = [
            {"name": "ZK8719", "api_key": "api_zk", "user_id": "ZK8719"}
        ]
        self.session = KCLILiveSession(self.client, self.accounts)
        self.session.gemini_api_key = "dummy_api_key"
        self.session.prompt_control = MagicMock()
        self.session.header_control = MagicMock()
        self.session.log_message = MagicMock()

        # Mock positions
        self.session.last_positions_response = {
            "accounts": [
                {
                    "name": "ZK8719",
                    "api_key": "api_zk",
                    "status": "success",
                    "positions": [
                        {"tradingsymbol": "NIFTY_E0_NEAR_CE", "quantity": -50}
                    ]
                }
            ]
        }
        self.session.active_positions = [
            {"tradingsymbol": "NIFTY_E0_NEAR_CE", "quantity": -50, "api_key": "api_zk", "account_name": "ZK8719"}
        ]
        self.session.position_id_map = {
            1: self.session.active_positions[0]
        }

    @patch("cli.advisor.get_nifty_options")
    @patch("cli.nli.parse_natural_language")
    async def test_nli_translation_flow(self, mock_parse, mock_options):
        # 1. Setup mocks
        mock_options.return_value = [
            {"name": "NIFTY", "expiry": datetime.date.today(), "strike": 23500.0, "instrument_type": "CE", "tradingsymbol": "NIFTY_E0_NEAR_CE"}
        ]
        
        # Define mock Gemini JSON response
        mock_nli_response = {
            "command": "account ZK8719 && exit NIFTY_E0_NEAR_CE",
            "explanation": "Switch to account ZK8719 and exit NIFTY_E0_NEAR_CE position",
            "confidence": 0.98
        }
        
        async def async_parse(*args, **kwargs):
            return mock_nli_response
            
        mock_parse.side_effect = async_parse

        # 2. Simulate slash input
        self.session._execute_single_command("/exit weekly options on zk")
        
        # Yield to allow the async resolve_nli_command task to run
        await asyncio.sleep(0.05)

        # Check staged action state
        self.assertIsNotNone(self.session.pending_order)
        self.assertEqual(self.session.pending_order["type"], "nli_command")
        self.assertEqual(self.session.pending_order["command"], "account ZK8719 && exit NIFTY_E0_NEAR_CE")

        # 3. Simulate user confirmation 'y'
        with patch.object(self.session, "execute_exit", return_value=None) as mock_exec:
            self.session._execute_single_command("y")
            await asyncio.sleep(0.05)
            
            # Assert ZK8719 context switched and exit called
            self.assertEqual(self.session.selected_account_name, "ZK8719")
            mock_exec.assert_called_once_with("NIFTY_E0_NEAR_CE", ["api_zk"], None)
            self.assertFalse(self.session._skip_confirmation)

if __name__ == "__main__":
    unittest.main()
