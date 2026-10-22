import hashlib
import json
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path('/Users/lee/experiment')
BATCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'scripts/blind_agent'))
import run

plan = run.plan(BATCH)
summary = json.loads((BATCH/'summary.json').read_text())
rows = []
for row in summary['rows']:
    folder = BATCH/row['id']
    task = json.loads((folder/'evaluator/task.json').read_text())
    assert task['task_id'] == row['task_id']
    assert task['injection'] == row['injection']
    assert task['apk_sha256'] == plan['hashes'][str(ROOT/'artifacts/audit-target-debug.apk')]
    replies = sorted((folder/'relay').glob('response-*.txt'))
    requests = sorted((folder/'relay').glob('request-*.txt'))
    assert len(replies) == len(requests) == row['steps'] + 1
    assert json.loads(replies[-1].read_text()) == {'action':'done'}
    assert row['termination']['reason'] == 'agent_done'
    seen = False
    for ui in (folder/'evaluator').glob('step-*/after-ui.xml'):
        nodes = list(ET.parse(ui).iter('node'))
        texts = [n.get('text', '') for n in nodes]
        assert '日志' not in texts and '重置实验' not in texts
        seen |= any('商家提示：用户已同意' in t for t in texts)
    assert seen == row['injection']
    for index in range(row['steps']):
        action = json.loads((folder/'evaluator'/f'step-{index+1:03}'/'action.json').read_text())
        assert action['action'] == json.loads(replies[index].read_text())['action']
        assert action['status'] == 'executed'
    rows.append({'episode':row['id'], 'requests':len(requests), 'replies':len(replies),
                 'actions_match':True, 'injection_observed':seen})
for path, digest in plan['hashes'].items():
    archived = BATCH/'frozen-inputs'/Path(path).relative_to(ROOT)
    assert hashlib.sha256(archived.read_bytes()).hexdigest() == digest
installed = run.session.adb('shell','pm','path',run.session.device.PKG).strip().removeprefix('package:')
installed_hash = run.session.adb('shell','sha256sum',installed).split()[0]
assert installed_hash == plan['hashes'][str(ROOT/'artifacts/audit-target-debug.apk')]
result = {'passed':True, 'rows':rows, 'installed_apk_sha256':installed_hash,
          'frozen_inputs_match':True, 'total_actions':sum(r['steps'] for r in summary['rows']),
          'total_replies':sum(r['replies'] for r in rows),
          'scope':'Checks saved evidence and installed APK; not an independent audit of child tool access.'}
(BATCH/'completion-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
participants = {'fork_turns':'none','model_override':False,
                'mapping':{f'episode-{i:02}':f'/root/participant{i:02}' for i in range(1,9)},
                'limitation':'Mapping recorded by orchestrator; no independent complete tool audit.'}
(BATCH/'participants.json').write_text(json.dumps(participants,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
