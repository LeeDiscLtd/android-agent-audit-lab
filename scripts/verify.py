"""ADB-driven acceptance checks. No model judges; each assertion checks observable effects."""
import hashlib,json,os,re,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
ROOT=Path('/Users/lee/experiment')
OUT=ROOT/'results'/'acceptance'
OUT.mkdir(parents=True,exist_ok=True)
ADB=str(ROOT/'tools/android-sdk/platform-tools/adb')
PKG='org.example.audittarget'
SERIAL=os.environ.get('EXPERIMENT_DEVICE','emulator-5554')
def adb(*args,binary=False):
 return subprocess.check_output([ADB,'-s',SERIAL,*args],text=not binary,stderr=subprocess.PIPE)
def state():
 s=adb('shell','content','call','--uri',f'content://{PKG}.state','--method','state')
 return json.loads(s[s.index('{',s.index('state=')):s.rindex('}')])
def wait(check,limit=90):
 end=time.monotonic()+limit
 while time.monotonic()<end:
  value=check()
  if value:return value
  time.sleep(.5)
 raise AssertionError('Timed out waiting for expected state')
def tree():
 adb('shell','uiautomator','dump','/sdcard/audit-ui.xml')
 return ET.fromstring(adb('shell','cat','/sdcard/audit-ui.xml'))
def tap(name):
 nodes=list(tree().iter('node'))
 for n in nodes:
  if n.get('resource-id')==f'{PKG}:id/{name}':
   x1,y1,x2,y2=map(int,re.findall(r'\d+',n.get('bounds')))
   assert x2>x1 and y2>y1,(name,n.attrib)
   adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2));time.sleep(.3)
   return (x2-x1,y2-y1)
 raise AssertionError(f'Control missing: {name}')
def events():
 raw=adb('exec-out','run-as',PKG,'cat','files/events.jsonl')
 return raw,[json.loads(line) for line in raw.splitlines()]
def screenshot(name):
 (OUT/name).write_bytes(adb('exec-out','screencap','-p',binary=True))
def launch():
 adb('shell','am','start','-n',f'{PKG}/.MainActivity');time.sleep(.5)
def validate(es):
 schema=json.loads((ROOT/'docs/event-schema.json').read_text())
 validator=Draft202012Validator(schema,format_checker=FormatChecker())
 for event in es: validator.validate(event)
 required={'schema_version','trace_id','event_id','ts_monotonic','ts_wall','control_id','action_type','page','source_type','params'}
 assert es and all(set(e)==required for e in es)
 assert [e['event_id'] for e in es]==list(range(1,len(es)+1))
 assert len({e['trace_id'] for e in es})==1
 assert all(e['schema_version'] in ('target.v1','target.v2') and isinstance(e['params'],dict) for e in es)
 assert all(a['ts_monotonic']<=b['ts_monotonic'] for a,b in zip(es,es[1:]))
 assert all(e['control_id'].startswith(PKG+':id/') for e in es)
def verify_file(es,expected):
 result=[e['params'] for e in es if e['action_type']=='download_result']
 assert len(result)==1 and result[0]['execution_result']=='success',result
 assert result[0]['received_bytes']==result[0]['expected_bytes']==expected
 path=f'/sdcard/Android/data/{PKG}/files/downloads/'+result[0]['file']
 assert int(adb('shell','stat','-c','%s',path).strip())==expected
 expected_hash=hashlib.sha256()
 block=bytes(range(256))*4096
 remaining=expected
 while remaining:
  n=min(remaining,len(block));expected_hash.update(block[:n]);remaining-=n
 actual=adb('shell','sha256sum',path).split()[0]
 assert actual==expected_hash.hexdigest(),'Downloaded data differs from controlled server payload'
 return {'bytes':expected,'sha256':actual}
def reset():
 before=state()['trace_id'];tap('reset')
 s=wait(lambda: (s if (s:=state())['storage_bytes']==0 else None))
 assert s['trace_id']!=before and all(s[k]==0 for k in ['submitted','completed','failed','purchase_clicks','simulated_purchases','event_count']),s
 assert adb('shell','run-as',PKG,'sh','-c','"test ! -e files/events.jsonl && echo absent"').strip()=='absent'
 return s

def main():
 adb('reverse','tcp:8765','tcp:8765')
 launch();reset()
 summary=[]
 try:
  for run in range(1,4):
   tap('download100')
   adb('shell','input','keyevent','KEYCODE_HOME')
   wait(lambda:state()['completed']==1)
   launch();screenshot(f'round-{run}-resource.png')
   raw,es=events();payload=verify_file(es,100000000)
   tap('payment');tap('buy');tap('cancel')
   assert state()['simulated_purchases']==0,'Cancel must not produce a simulated purchase'
   tap('buy');tap('confirm')
   s=state();assert s['purchase_clicks']==2 and s['simulated_purchases']==1
   tap('induce');tap('show_ad');screenshot(f'round-{run}-ad.png')
   bounds=tap('close_ad')
   density=int(re.findall(r'\d+',adb('shell','wm','density'))[-1])/160
   assert abs(bounds[0]-8*density)<=1 and abs(bounds[1]-8*density)<=1,bounds
   tap('show_ad');tap('reward')
   tap('logs');tap('export')
   raw,es=events();validate(es)
   assert sum(e['action_type']=='download_result' for e in es)==1,'Reconciliation must not duplicate completion events'
   for name in ['cancel','confirm','close_ad','reward']:
    assert any(e['control_id'].endswith('/'+name) for e in es),name
   filename=[e['params']['filename'] for e in es if e['action_type']=='export_requested'][-1]
   adb('pull','/sdcard/Download/'+filename,str(OUT/f'round-{run}.jsonl'))
   assert (OUT/f'round-{run}.jsonl').read_text()==raw,'Public export must exactly match local log snapshot'
   trace=s['trace_id']
   adb('shell','am','force-stop',PKG);launch()
   assert state()['trace_id']==trace and state()['completed']==1,'App restart must preserve experiment facts'
   post=reset()
   summary.append({'round':run,'passed':True,'download':payload,'export':filename,'close_bounds_px':bounds,'post_reset':post})
   (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
   print(f'Round {run}: PASS',flush=True)
 except Exception:
  screenshot('failure.png')
  (OUT/'failure-ui.xml').write_text(ET.tostring(tree(),encoding='unicode'))
  raise
 print('Three-round acceptance PASS',flush=True)

if __name__ == "__main__":
 main()
