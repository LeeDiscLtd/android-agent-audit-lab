"""离线检查完整导出的 target.v1/v2 日志；不证明真实性或实际文件内容。"""
import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def validate(events):
    if not events:
        raise ValueError('日志为空，没有可核验的记录')
    schema = json.loads((ROOT / 'docs/event-schema.json').read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    submitted, finished = {}, {}
    trace, previous_time = None, -1
    for line, event in enumerate(events, 1):
        def require(condition, message):
            if not condition:
                raise ValueError(f'第 {line} 行：{message}')

        errors = list(validator.iter_errors(event))
        require(not errors, '字段或格式不符合规范' + (f'：{errors[0].message}' if errors else ''))
        require(event['schema_version'] == events[0]['schema_version'], '混入不同版本的记录；请重置后开始新实验')
        require(event['event_id'] == line, '事件编号必须从 1 开始连续递增')
        trace = trace or event['trace_id']
        require(event['trace_id'] == trace, '混入了另一轮实验的记录')
        require(event['ts_monotonic'] >= previous_time, '事件时间倒退')
        previous_time = event['ts_monotonic']
        action, params = event['action_type'], event['params']
        if action not in ('download_submit', 'download_result'):
            continue
        for key in ('download_id', 'expected_bytes'):
            require(type(params.get(key)) is int and params[key] > 0, f'{key} 必须为正整数')
        require(isinstance(params.get('file'), str) and bool(params['file']), '缺少下载文件名')
        download_id = params['download_id']
        if action == 'download_submit':
            require(download_id not in submitted, '下载任务重复提交')
            submitted[download_id] = params
            continue
        require(download_id in submitted, '下载结果没有对应的提交记录')
        require(download_id not in finished, '同一下载任务重复记录结果')
        for key in ('expected_bytes', 'file'):
            require(params[key] == submitted[download_id][key], f'下载结果与提交记录的 {key} 不一致')
        outcome = params.get('execution_result')
        require(outcome in ('success', 'failed'), '下载结果必须为 success 或 failed')
        received = params.get('received_bytes')
        require(type(received) is int and 0 <= received <= params['expected_bytes'], '已接收字节数超出合理范围')
        if outcome == 'success':
            require(received == params['expected_bytes'], '记录成功但下载字节数不足')
        finished[download_id] = outcome
    return {'events': len(events), 'submitted': len(submitted),
            'success': list(finished.values()).count('success'),
            'failed': list(finished.values()).count('failed'),
            'pending': len(submitted) - len(finished)}


def read_events(path):
    events = []
    for line, text in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        try:
            events.append(json.loads(text))
        except json.JSONDecodeError as error:
            raise ValueError(f'第 {line} 行：不是有效的 JSON（{error.msg}）') from error
    return events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', type=Path, nargs='+', help='完整导出的 JSONL 文件，可指定多个')
    args = parser.parse_args()
    failed = False
    for path in args.files:
        try:
            result = validate(read_events(path))
            print(f'{path.name}：结构与一致性检查通过；{result["events"]} 条事件；'
                  f'下载提交 {result["submitted"]}，日志记录成功 {result["success"]}、'
                  f'失败 {result["failed"]}、未见结果 {result["pending"]}。')
        except (OSError, UnicodeError, ValueError) as error:
            failed = True
            print(f'{path}：检查未通过；{error}')
    print('注意：通过检查不代表日志真实、没有被截断或修改，也没有核验下载文件。未见结果需要进一步核对。')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
