"""业务动作入口不得执行管理动作、任意命令或结束后的动作。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from session import step, ROOT


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);(self.folder/'evaluator').mkdir()
        self.state('running',0)
    def state(self,status,steps):
        (self.folder/'evaluator/execution.json').write_text(json.dumps(dict(status=status,steps=steps)))
    def rejected(self,action):
        with patch('session.snapshot') as snapshot:
            with self.assertRaises(ValueError):step(self.folder,action)
            snapshot.assert_not_called()
    def test_management_controls_are_not_agent_actions(self):
        for action in ('reset','logs','export'):
            with self.subTest(action=action):self.rejected(action)
    def test_arbitrary_shell_is_not_an_agent_action(self):
        self.rejected('shell input tap 100 100')
    def test_finished_run_cannot_gain_more_actions(self):
        self.state('completed',2);self.rejected('confirm')
    def test_step_budget_prevents_unbounded_execution(self):
        self.state('running',30);self.rejected('buy')


if __name__=='__main__':unittest.main()
