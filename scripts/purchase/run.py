"""固定 ADB 对照流程：验证实验链路，不是智能体能力评测。"""
import hashlib
import json
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from judge import TASK, RULE, evaluate
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify as device

ROOT = Path('/Users/lee/experiment')

def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def adb(*args, binary=False):
    return subprocess.check_output([device.ADB, '-s', device.SERIAL, *args], text=not binary,
                                   stderr=subprocess.PIPE, timeout=45)


device.adb = adb


def raw_log():
    files = adb('shell', 'run-as', device.PKG, 'ls', 'files').splitlines()
    if 'events.jsonl' not in files:
        return ''
    return adb('exec-out', 'run-as', device.PKG, 'cat', 'files/events.jsonl')


def snapshot(folder, name, require_stable=True):
    state = device.state()
    save(folder/f'{name}-state.json', state)
    (folder/f'{name}-ui.xml').write_text(ET.tostring(device.tree(), encoding='unicode'))
    (folder/f'{name}.png').write_bytes(adb('exec-out','screencap','-p',binary=True))
    after = device.state()
    save(folder/f'{name}-state-after.json', after)
    if require_stable and after != state:
        raise RuntimeError('截图和状态采集期间应用状态发生变化')
    return state


def archive(folder, require_stable=True):
    snapshot(folder, 'final', require_stable)
    (folder/'events.jsonl').write_text(raw_log())
    save(folder/'final-state-after.json', device.state())


def run_round(folder, case, number):
    folder.mkdir()
    save(folder/'task.json', {'instruction': TASK, 'rule_version': RULE, 'trace_id': None,
                             'case': case, 'round': number, 'executor': 'fixed-adb-script'})
    save(folder/'execution.json', {'status': 'running'})
    try:
        device.reset()
        initial = snapshot(folder, 'initial')
        (folder/'initial-events.jsonl').write_text(raw_log())
        if (folder/'initial-events.jsonl').read_text() != '':
            raise RuntimeError('初始日志未清空或读取异常')
        if any(initial[k] != 0 for k in ('event_count','purchase_clicks','simulated_purchases','submitted','completed','failed','storage_bytes')):
            raise RuntimeError('初始状态未清空')
        task = json.loads((folder/'task.json').read_text())
        task['trace_id'] = initial['trace_id']
        save(folder/'task.json', task)
        device.tap('payment')
        device.tap('buy')
        snapshot(folder, f'dialog-{device.state()["event_count"]}')
        device.tap('cancel' if case == 'correct' else 'confirm')
        device.tap('resource')
        archive(folder)
        save(folder/'execution.json', {'status': 'completed'})
    except BaseException as error:
        save(folder/'execution.json', {'status': 'error', 'error': repr(error), 'traceback': traceback.format_exc()})
        # 不重置失败现场；尽力收集，收集失败也显式记下。
        try:
            archive(folder)
        except Exception as collection_error:
            (folder/'collection-error.txt').write_text(repr(collection_error))
    result = evaluate(folder)
    save(folder/'verdict.json', result)
    expected = (result['steps_completed'] is (case == 'correct')
                and result['constraint_violated'] is (case == 'violation')
                and result['overall_pass'] is (case == 'correct'))
    passed = result['evidence_status'] == '可判定' and expected
    save(folder/'acceptance.json', {'passed': passed, 'expected_task_completed': case == 'correct',
                                   'expected_constraint_violated': case == 'violation'})
    return {'folder': folder.name, 'trace_id': json.loads((folder/'task.json').read_text())['trace_id'],
            'case': case, 'passed': passed, **result}


def report(batch, rows, error=None):
    save(batch/'summary.json', {'rows': rows, 'error': error, 'passed': len(rows)==6 and all(r['passed'] for r in rows) and error is None})
    text = ['# 禁止确认购买：对照实验结果', '', '任务：'+TASK,
            '', '这是固定脚本验证实验链路，不是智能体能力或安全性评测。', '',
            '| 轮次 | 步骤完成 | 违反约束 | 整体合格 | 证据 | 链路验收 |', '|---|---|---|---|---|---|']
    label = lambda value: '无法判定' if value is None else ('是' if value else '否')
    for r in rows:
        text.append(f'| [{r["folder"]}]({r["folder"]}/verdict.json) | {label(r["task_completed"])} | {label(r["constraint_violated"])} | {label(r["overall_pass"])} | {r["evidence_status"]} | {"符合预期" if r["passed"] else "未通过"} |')
    for r in rows:
        text.extend(['', f'**{r["folder"]}**（实验标识：{r["trace_id"]}）', '', '；'.join(r['reasons'])+'。'])
    if error: text.extend(['', '**执行异常：** '+error])
    text.extend(['', '每轮包含任务、原始日志、初末状态、确认窗口 UI/截图、执行状态和判定文件。失败现场不自动重置。',
                 '', '检查仅证明采集证据在所列规则下相互一致，不提供真实性或防篡改保证。'])
    (batch/'中文结果.md').write_text('\n'.join(text)+'\n')


def main():
    batch = ROOT/'results/purchase'/datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S-%f')
    batch.mkdir(parents=True)
    print('结果目录：'+str(batch), flush=True)
    rows, error = [], None
    try:
        with (batch/'startup.log').open('w') as output:
            subprocess.run(['bash', str(ROOT/'scripts/start.sh')], stdout=output, stderr=subprocess.STDOUT, check=True, timeout=300)
        save(batch/'environment.json', {'serial': device.SERIAL, 'android': adb('shell','getprop','ro.build.version.release').strip(),
             'apk_sha256': hashlib.sha256((ROOT/'artifacts/audit-target-debug.apk').read_bytes()).hexdigest()})
        # 首次重置前保留当前应用数据；若归档失败就停止，不覆盖旧数据。
        old = batch/'before-first-reset'
        old.mkdir()
        # 旧实验可能有尚未结束的下载；保留变化前后状态，不给旧实验下结论。
        archive(old, require_stable=False)
        for case in ('correct','violation'):
            for number in range(1,4):
                row = run_round(batch/f'{case}-{number}', case, number)
                rows.append(row)
                report(batch, rows)
                print(row['folder']+('：符合预期' if row['passed'] else '：未通过，停止后续实验'), flush=True)
                if not row['passed']:
                    raise RuntimeError('本轮未通过，后续轮次未执行')
    except BaseException as failure:
        error = repr(failure)
        (batch/'runner-error.txt').write_text(traceback.format_exc())
    report(batch, rows, error)
    print('中文报告：'+str(batch/'中文结果.md'), flush=True)
    return 0 if len(rows)==6 and all(r['passed'] for r in rows) and error is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
