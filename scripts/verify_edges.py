"""Check both remaining size tiers and cancellation of an in-flight 1GB download."""
import json,time
import verify as v
v.OUT=v.ROOT/'results'/'edgecases'
v.OUT.mkdir(exist_ok=True)
v.launch();v.reset()
summary=[]
for mb in (10,1000):
 v.tap(f'download{mb}')
 v.adb('shell','input','keyevent','KEYCODE_HOME')
 v.wait(lambda:v.state()['completed']==1,120)
 raw,es=v.events();v.validate(es)
 payload=v.verify_file(es,mb*1000000)
 (v.OUT/f'{mb}MB.jsonl').write_text(raw)
 summary.append({'case':f'{mb}MB download','passed':True,**payload})
 v.launch();v.reset()
 print(f'{mb}MB verified',flush=True)
v.tap('download1000')
v.wait(lambda:(s:=v.state())['storage_bytes']>0 and s['completed']==0)
before=v.state();assert before['completed']==0
post=v.reset()
time.sleep(4)
assert v.state()==post,'Cancelled download must not write files or append events into the new experiment'
summary.append({'case':'reset active download','passed':True,'before':before,'after':post})
(v.OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print('Size tiers and in-flight reset: PASS',flush=True)
# Route the same app request to a controlled 404 endpoint; a failed request must not count as success.
import subprocess,sys,socket
empty=v.ROOT/'tmp'/'http404';empty.mkdir(exist_ok=True)
with (v.OUT/'http404.log').open('w') as log:
 process=subprocess.Popen([sys.executable,'-m','http.server','8766','--bind','127.0.0.1','--directory',str(empty)],stdout=log,stderr=log)
 try:
  def ready():
   try:
    with socket.create_connection(('127.0.0.1',8766),timeout=.2):return True
   except OSError:return False
  v.wait(ready,5)
  v.adb('reverse','tcp:8765','tcp:8766')
  v.tap('download10');v.wait(lambda:v.state()['failed']==1)
  s=v.state();assert s['completed']==0 and s['storage_bytes']==0
  raw,es=v.events();v.validate(es)
  result=[e['params'] for e in es if e['action_type']=='download_result']
  assert len(result)==1 and result[0]['execution_result']=='failed' and result[0]['reason']==404,result
  (v.OUT/'http404.jsonl').write_text(raw)
  summary.append({'case':'HTTP 404 must not count as success','passed':True,'state':s,'result':result[0]})
  v.reset()
 finally:
  v.adb('reverse','tcp:8765','tcp:8765');process.terminate();process.wait(timeout=5)
(v.OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print('HTTP 404 failure accounting: PASS',flush=True)
