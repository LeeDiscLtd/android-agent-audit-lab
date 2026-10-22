"""验证核验器能拒绝会误导实验结论的数据，并允许尚未完成的快照。"""
import copy
import unittest

from validate_log import ROOT, read_events, validate


class LogValidationTests(unittest.TestCase):
    def setUp(self):
        self.events = read_events(ROOT / 'results/acceptance/round-1.jsonl')[:2]

    def test_real_exports(self):
        paths = list((ROOT / 'results/acceptance').glob('round-*.jsonl'))
        paths += [ROOT / f'results/edgecases/{name}.jsonl' for name in ('10MB', '1000MB', 'http404')]
        self.assertEqual(len(paths), 6)
        for path in paths:
            with self.subTest(path=path.name):
                self.assertEqual(validate(read_events(path))['pending'], 0)

    def test_pending_is_not_reported_as_success(self):
        result = validate(self.events[:1])
        self.assertEqual((result['pending'], result['success']), (1, 0))

    def test_partial_failure_is_valid_but_not_success(self):
        self.events[1]['params'].update(execution_result='failed', received_bytes=1234)
        result = validate(self.events)
        self.assertEqual((result['failed'], result['success']), (1, 0))

    def test_rejects_misleading_records(self):
        for problem in ('sequence', 'trace', 'time', 'bytes', 'file', 'duplicate', 'missing_submit', 'schema', 'type'):
            events = copy.deepcopy(self.events)
            if problem == 'sequence': events[1]['event_id'] = 3
            elif problem == 'trace': events[1]['trace_id'] = '00000000-0000-4000-8000-000000000000'
            elif problem == 'time': events[1]['ts_monotonic'] = 0
            elif problem == 'bytes': events[1]['params']['received_bytes'] = 1
            elif problem == 'file': events[1]['params']['file'] = 'other.bin'
            elif problem == 'duplicate':
                events.append(copy.deepcopy(events[1]))
                events[-1]['event_id'] = 3
            elif problem == 'missing_submit':
                events = events[1:]
                events[0]['event_id'] = 1
            elif problem == 'schema': del events[1]['source_type']
            elif problem == 'type': events[1]['params']['received_bytes'] = True
            with self.subTest(problem=problem), self.assertRaises(ValueError):
                validate(events)

    def test_empty_cannot_prove_anything(self):
        with self.assertRaises(ValueError):
            validate([])


if __name__ == '__main__':
    unittest.main(verbosity=2)
