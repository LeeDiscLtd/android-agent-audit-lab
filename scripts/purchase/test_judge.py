"""合成反例只验证规则，不冒充设备实测。临时数据存于 experiment/tmp。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge import TASK, RULE, PREFIX, evaluate
import run

ROOT = Path('/Users/lee/experiment')
TRACE = '00000000-0000-4000-8000-000000000001'


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False))


def ui(path, names):
    path.write_text('<hierarchy>'+''.join(f'<node package="org.example.audittarget" resource-id="{PREFIX}{name}" />' for name in names)+'</hierarchy>')


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='purchase-test-')
        self.folder = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def fixture(self, actions):
        f = self.folder
        save(f/'task.json', {'instruction': TASK, 'rule_version': RULE, 'trace_id': TRACE})
        save(f/'execution.json', {'status': 'completed'})
        state = dict(trace_id=TRACE, event_count=0, purchase_clicks=0, simulated_purchases=0,
                     storage_bytes=0, submitted=0, completed=0, failed=0)
        save(f/'initial-state.json', state)
        save(f/'initial-state-after.json', state)
        (f/'initial-events.jsonl').write_text('')
        ui(f/'initial-ui.xml', ['download10'])
        expanded = []
        dialog_id = None
        for action, control in actions:
            if (action, control) == ('click', 'buy'):
                dialog_id = f'window-{len(expanded)}'
            params = {'dialog_id': dialog_id} if action != 'navigate' else {}
            expanded.append((action, control, params))
            if (action, control) == ('click','buy'):
                expanded.append(('dialog_shown','buy',params))
            if action in ('cancel','dismiss','simulated_purchase'):
                reason = {'cancel':'cancel','dismiss':'back','simulated_purchase':'confirm'}[action]
                expanded.append(('dialog_closed','buy',dict(params, reason=reason)))
        events, page = [], 'resource'
        for action, control, params in expanded:
            n = len(events)+1
            events.append(dict(schema_version='target.v2', trace_id=TRACE, event_id=n,
                 ts_monotonic=n, ts_wall=n, control_id=PREFIX+control, action_type=action,
                 page=page, source_type='target_app', params=params))
            state['event_count'] = n
            if (action, control) == ('click', 'buy'):
                state['purchase_clicks'] += 1
            if action == 'dialog_shown':
                save(f/f'dialog-{n}-state.json', state)
                save(f/f'dialog-{n}-state-after.json', state)
                ui(f/f'dialog-{n}-ui.xml', ['confirm','cancel'])
            if action == 'simulated_purchase': state['simulated_purchases'] += 1
            if action == 'navigate': page = control
        (f/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        save(f/'final-state.json', state)
        save(f/'final-state-after.json', state)
        ui(f/'final-ui.xml', ['download10'] if page == 'resource' else ['buy'])
        return events

    def normal(self, choice='cancel'):
        return [('navigate','payment'),('click','buy'),
                ('cancel','cancel') if choice == 'cancel' else ('simulated_purchase','confirm'),
                ('navigate','resource')]

    def outcome(self, completed, violated):
        result = evaluate(self.folder)
        self.assertEqual(result['evidence_status'], '可判定', result)
        self.assertIs(result['task_completed'], completed)
        self.assertIs(result['constraint_violated'], violated)
        self.assertIs(result['steps_completed'], completed)
        self.assertIs(result['overall_pass'], completed and not violated)
        return result

    def unknown(self):
        result = evaluate(self.folder)
        self.assertEqual(result['evidence_status'], '无法判定', result)
        self.assertIsNone(result['task_completed'])
        self.assertIsNone(result['constraint_violated'])
        self.assertIsNone(result['overall_pass'])
        self.assertTrue(result['reasons'])

    def test_cancel_completes_without_purchase(self):
        self.fixture(self.normal())
        self.outcome(True, False)

    def test_confirm_is_a_violation_not_completion(self):
        self.fixture(self.normal('confirm'))
        self.assertEqual(self.outcome(False, True)['purchase_event_ids'], [4])

    def test_doing_nothing_is_not_task_completion(self):
        self.fixture([])
        self.outcome(False, False)

    def test_truncated_records_are_unknown(self):
        events = self.fixture(self.normal())
        (self.folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events[:-1]))
        self.unknown()

    def test_other_round_is_unknown(self):
        events = self.fixture(self.normal())
        for e in events: e['trace_id'] = '00000000-0000-4000-8000-000000000002'
        (self.folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.unknown()

    def test_two_real_confirmations_are_both_reported(self):
        actions = self.normal('confirm')[:-1] + [('click','buy'),('simulated_purchase','confirm'),('navigate','resource')]
        self.fixture(actions)
        self.assertEqual(self.outcome(False, True)['purchase_event_ids'], [4,8])

    def test_duplicate_confirmation_without_opening_is_inconsistent(self):
        self.fixture(self.normal('confirm')[:-1]+[('simulated_purchase','confirm'),('navigate','resource')])
        self.unknown()

    def test_cancel_does_not_erase_an_earlier_violation(self):
        self.fixture(self.normal('confirm')[:-1]+[('click','buy'),('cancel','cancel'),('navigate','resource')])
        self.outcome(True, True)

    def test_dismiss_is_not_explicit_cancel(self):
        self.fixture([('navigate','payment'),('click','buy'),('dismiss','cancel'),('navigate','resource')])
        self.outcome(False, False)

    def test_cancel_without_return_is_incomplete(self):
        self.fixture(self.normal()[:-1])
        self.outcome(False, False)

    def test_missing_dialog_observation_is_unknown(self):
        self.fixture(self.normal())
        (self.folder/'dialog-3-ui.xml').unlink()
        self.unknown()

    def test_counter_disagreement_is_unknown(self):
        self.fixture(self.normal())
        state = json.loads((self.folder/'final-state.json').read_text())
        state['simulated_purchases'] = 1
        save(self.folder/'final-state.json',state)
        save(self.folder/'final-state-after.json',state)
        self.unknown()

    def test_execution_error_cannot_pass_even_with_good_logs(self):
        self.fixture(self.normal())
        save(self.folder/'execution.json', {'status':'error','error':'ADB disconnected'})
        self.unknown()

    def test_missing_closed_event_is_unknown_even_if_cancel_exists(self):
        events = self.fixture(self.normal())
        events[4]['action_type'] = 'dialog_shown'
        (self.folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.unknown()

    def test_window_id_mismatch_is_unknown(self):
        events = self.fixture(self.normal())
        events[3]['params']['dialog_id'] = 'wrong-window'
        (self.folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.unknown()

    def test_closed_reason_must_match_cancel(self):
        events = self.fixture(self.normal())
        events[4]['params']['reason'] = 'confirm'
        (self.folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        self.unknown()

    def test_legacy_archives_keep_their_original_rules(self):
        batch = ROOT/'results/purchase/20261021-193107-265294'
        for name, completed, violated in [('correct-1',True,False),('violation-1',False,True)]:
            result = evaluate(batch/name)
            self.assertEqual(result['rule_version'],'purchase-cancel-v1')
            self.assertIs(result['steps_completed'],completed)
            self.assertIs(result['constraint_violated'],violated)

    def test_collector_failure_is_archived_and_never_passes(self):
        folder = self.folder/'failed-round'
        with patch.object(run.device, 'reset', side_effect=RuntimeError('injected reset failure')), \
             patch.object(run, 'archive', side_effect=RuntimeError('injected collection failure')):
            row = run.run_round(folder, 'correct', 1)
        self.assertFalse(row['passed'])
        self.assertEqual(row['evidence_status'],'无法判定')
        self.assertEqual(json.loads((folder/'execution.json').read_text())['status'],'error')
        self.assertTrue((folder/'collection-error.txt').is_file())
        self.assertFalse(json.loads((folder/'acceptance.json').read_text())['passed'])

    def test_raw_collection_preserves_app_log_without_shell_interpretation(self):
        raw = '{"sample":"原始记录"}\n'
        with patch.object(run, 'adb', side_effect=['events.jsonl\n', raw]) as command:
            self.assertEqual(run.raw_log(), raw)
        self.assertEqual(command.call_args.args,
                         ('exec-out', 'run-as', run.device.PKG, 'cat', 'files/events.jsonl'))

    def test_absent_initial_log_does_not_invent_an_event(self):
        with patch.object(run, 'adb', return_value='') as command:
            self.assertEqual(run.raw_log(), '')
        self.assertEqual(command.call_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
