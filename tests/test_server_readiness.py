import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from coevo.rsi import Server


class ReadinessTests(unittest.TestCase):
    def test_adapter_ready_requires_its_model_and_free_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            process=MagicMock();process.poll.return_value=None
            replies=[ConnectionError('free endpoint'),{'data':[{'id':'base'}]},{'data':[{'id':'coevo-current'}]}]
            with patch('coevo.rsi.read_config',return_value={'endpoint':'http://127.0.0.1:1/v1','served_model':'base'}), \
                 patch('coevo.rsi.subprocess.Popen',return_value=process), \
                 patch('coevo.rsi.request_json',side_effect=replies) as request, \
                 patch('coevo.rsi.time.sleep') as sleep:
                server=Server('fixture',Path(tmp)/'server.log','fixture-adapter')
                self.assertEqual(request.call_count,3)
                sleep.assert_called_once_with(1)
                server.log.close()
            with patch('coevo.rsi.read_config',return_value={'endpoint':'http://127.0.0.1:1/v1','served_model':'base'}), \
                 patch('coevo.rsi.request_json',return_value={'data':[{'id':'base'}]}), \
                 patch('coevo.rsi.subprocess.Popen') as launch:
                with self.assertRaisesRegex(RuntimeError,'already occupied'):
                    Server('fixture',Path(tmp)/'occupied.log')
                launch.assert_not_called()
