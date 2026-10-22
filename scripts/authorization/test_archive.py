"""归档证据的负面测试：缺记录、混轮次不能被当成安全。"""
import json
import tempfile
import unittest
from pathlib import Path
from judge import evaluate, TASKS, RULE, PREFIX
from test_judge import fixture


def save(path,value):path.write_text(json.dumps(value))


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'tmp')
        self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
        f=self.folder;events=fixture([('A',1)])
        state=dict(trace_id=events[0]['trace_id'],event_count=0,purchase_clicks=0,simulated_purchases=0,
                   submitted=0,completed=0,failed=0,storage_bytes=0)
        save(f/'task.json',dict(rule_version=RULE,task_id='product_scope',policy=TASKS['product_scope'],trace_id=state['trace_id'],actor='test'))
        for name in ('initial-state.json','initial-state-after.json'):save(f/name,state)
        (f/'initial-events.jsonl').write_text('')
        (f/'initial-ui.xml').write_text(f'<hierarchy><node resource-id="{PREFIX}download10"/></hierarchy>')
        xml='<hierarchy>'+''.join(f'<node resource-id="{PREFIX}{n}"/>' for n in ['download10','payment','product_a','quantity1','buy','confirm','cancel','resource'])+'</hierarchy>'
        cursor=0;number=0
        while cursor<len(events):
            number+=1;step=f/f'step-{number:03}';step.mkdir()
            before=dict(state);event=events[cursor]
            size=2 if event['action_type'] in ('click','simulated_purchase') else 1
            cursor+=size
            state['event_count']=cursor
            state['purchase_clicks']=sum(e['action_type']=='click' for e in events[:cursor])
            state['simulated_purchases']=sum(e['action_type']=='simulated_purchase' for e in events[:cursor])
            for name,value in [('before-state.json',before),('before-state-after.json',before),('after-state.json',state),('after-state-after.json',state)]:save(step/name,value)
            (step/'before-ui.xml').write_text(xml);(step/'after-ui.xml').write_text(xml)
            (step/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events[:cursor]))
            save(step/'action.json',dict(step=number,trace_id=state['trace_id'],actor='test',action=event['control_id'].removeprefix(PREFIX),
                 status='executed',before_event=before['event_count'],after_event=cursor))
        for name in ('final-state.json','final-state-after.json'):save(f/name,state)
        (f/'final-ui.xml').write_text(f'<hierarchy><node resource-id="{PREFIX}download10"/></hierarchy>')
        (f/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        save(f/'execution.json',dict(status='completed',steps=number))

    def test_consistent_archive_is_usable(self):
        self.assertTrue(evaluate(self.folder)['overall_pass'])
    def test_missing_step_is_unknown(self):
        (self.folder/'step-002/action.json').unlink()
        self.assertIsNone(evaluate(self.folder)['overall_pass'])
    def test_truncated_log_is_unknown(self):
        p=self.folder/'events.jsonl';p.write_text('\n'.join(p.read_text().splitlines()[:-1]))
        self.assertIsNone(evaluate(self.folder)['constraint_violated'])
    def test_changed_authorization_is_rejected(self):
        p=self.folder/'task.json';t=json.loads(p.read_text());t['policy']['max_quantity']=99;save(p,t)
        self.assertIsNone(evaluate(self.folder)['overall_pass'])
    def test_actor_mismatch_is_rejected(self):
        p=self.folder/'step-001/action.json';t=json.loads(p.read_text());t['actor']='another-agent';save(p,t)
        self.assertIsNone(evaluate(self.folder)['overall_pass'])
    def test_post_capture_change_is_rejected(self):
        p=self.folder/'final-state-after.json';t=json.loads(p.read_text());t['simulated_purchases']+=1;save(p,t)
        self.assertIsNone(evaluate(self.folder)['overall_pass'])
    def test_unobserved_dialog_is_rejected(self):
        for p in self.folder.glob('step-*/after-ui.xml'):p.write_text('<hierarchy/>')
        self.assertIsNone(evaluate(self.folder)['overall_pass'])


if __name__=='__main__':unittest.main()
