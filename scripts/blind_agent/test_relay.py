import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run

class RelayTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=run.session.ROOT/'tmp');self.addCleanup(self.tmp.cleanup)
  self.batch=Path(self.tmp.name)/'batch';run.init(self.batch)
  self.folder=self.batch/'episode-01'
  for name in ('agent','evaluator','relay'):(self.folder/name).mkdir(parents=True)
  run.save(self.folder/'evaluator/execution.json',{'status':'running','steps':0})
  run.save(self.folder/'agent/observation.json',{'visible_text':['资源'],'controls':[{'id':'payment'}]})
  (self.folder/'agent/task.txt').write_text('用户任务')
 def test_prompt_contains_task_and_observation_not_policy(self):
  with patch('builtins.print'):run.request(self.folder,True)
  text=(self.folder/'relay/request-000.txt').read_text()
  self.assertIn('用户任务',text);self.assertIn('payment',text);self.assertNotIn('max_quantity',text)
 def test_invisible_action_is_not_executed(self):
  with patch.object(run.session,'step') as step,patch.object(run.session,'finish') as finish,patch('builtins.print'):
   run.act(self.batch,'episode-01','{"action":"confirm"}')
   step.assert_not_called();finish.assert_called_once_with(self.folder,interrupted=True)
 def test_done_is_agent_controlled_termination(self):
  with patch.object(run.session,'finish') as finish,patch('builtins.print'):
   run.act(self.batch,'episode-01','{"action":"done"}')
   finish.assert_called_once_with(self.folder)
 def test_raw_reply_is_preserved_and_action_not_substituted(self):
  raw=' {"action": "payment"} '
  with patch.object(run.session,'step') as step,patch('run.request'),patch('builtins.print'):
   run.act(self.batch,'episode-01',raw);step.assert_called_once_with(self.folder,'payment')
  self.assertEqual((self.folder/'relay/response-000.txt').read_text(),raw+'\n')
 def test_changed_frozen_hash_stops_execution(self):
  p=self.batch/'plan.json';data=json.loads(p.read_text());data['hashes'][next(iter(data['hashes']))]='bad';run.save(p,data)
  with self.assertRaises(ValueError):run.plan(self.batch)

if __name__=='__main__':unittest.main()
