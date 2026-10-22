"""设备端存储故障注入与相关回归；执行前备份现有应用数据。"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import run

ROOT = run.ROOT
v = run.device
OUT = ROOT/'results/optimization-20261022'/datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H%M%S')
OUT.mkdir()
print('优化验收目录：'+str(OUT), flush=True)
rows = []

def record(name, **facts):
    rows.append(dict(case=name, passed=True, **facts))
    run.save(OUT/'checks.json', rows)
    print(name+'：PASS', flush=True)


def instrument(case):
    v.adb('shell','am','force-stop',v.PKG)
    output = v.adb('shell','am','instrument','-w','-e','case',case,
                   v.PKG+'.test/org.example.audittarget.StoreInstrumentation')
    (OUT/f'{case}-instrumentation.txt').write_text(output)
    return output


try:
    devices = subprocess.check_output([v.ADB,'devices'],text=True)
    if 'emulator-5554' not in devices:
        with (OUT/'emulator.log').open('w') as log:
            emulator = subprocess.Popen([str(ROOT/'tools/android-sdk/emulator/emulator'),'-avd','AuditApi33','-port','5554',
                '-no-window','-no-audio','-no-boot-anim','-no-snapshot','-gpu','swiftshader_indirect','-memory','2048','-cores','2'],stdout=log,stderr=log)
    for _ in range(90):
        try:
            if v.adb('shell','getprop','sys.boot_completed').strip() == '1': break
        except subprocess.CalledProcessError: pass
        time.sleep(2)
    else: raise RuntimeError('模拟器未启动')
    assert 'AuditApi33' in v.adb('emu','avd','name')
    # 在升级安装和任何重置之前保存旧版文件；不把这份备份当作本次验收证据。
    paths = ['files','shared_prefs']
    if 'databases' in v.adb('shell','run-as',v.PKG,'ls').splitlines(): paths.append('databases')
    (OUT/'pre-upgrade.tar').write_bytes(v.adb('exec-out','run-as',v.PKG,'tar','-cf','-',*paths,binary=True))
    with (OUT/'startup.log').open('w') as log:
        subprocess.run(['bash',str(ROOT/'scripts/start.sh')],check=True,stdout=log,stderr=log,timeout=300)
    before = v.state()
    run.save(OUT/'after-upgrade-state.json',before)
    (OUT/'after-upgrade-events.jsonl').write_text(run.raw_log())
    record('upgrade-readable', state=before)
    v.adb('install','-r',str(ROOT/'android-target/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'))
    for case in ('rollback','snapshot'):
        output = instrument(case)
        assert output.strip() == 'STORE_TEST_PASS',output
        record(case)
    for case, expected in [('before_commit',0),('after_commit',1)]:
        output = instrument(case)
        assert 'Process crashed' in output,output
        assert v.adb('exec-out','run-as',v.PKG,'cat','files/crash-marker').strip()==case
        state = v.state()  # 新进程重开数据库并重新生成导出快照。
        raw = run.raw_log()
        events = [json.loads(line) for line in raw.splitlines()]
        assert state['simulated_purchases']==state['event_count']==len(events)==expected,(state,events)
        (OUT/f'{case}.jsonl').write_text(raw)
        run.save(OUT/f'{case}-state.json',state)
        record(case, recovered_purchases=expected)
    v.launch();v.reset()
    v.tap('payment');v.tap('buy')
    v.adb('shell','input','keyevent','KEYCODE_HOME');v.launch()
    ids={n.get('resource-id') for n in v.tree().iter('node')}
    assert v.PKG+':id/confirm' in ids,'恢复前台后窗口丢失'
    v.adb('shell','input','keyevent','KEYCODE_BACK');time.sleep(.5)
    state=v.state();raw,events=v.events()
    assert state['simulated_purchases']==0
    assert events[-1]['action_type']=='dialog_closed' and events[-1]['params']['reason']=='back'
    assert sum(e['action_type']=='dialog_shown' for e in events)==1
    (OUT/'background-back.jsonl').write_text(raw)
    record('background-and-back', state=state)
    v.reset();v.tap('payment');v.tap('buy')
    node=next(n for n in v.tree().iter('node') if n.get('resource-id')==v.PKG+':id/confirm')
    x1,y1,x2,y2=map(int,re.findall(r'\d+',node.get('bounds')))
    for _ in range(2): v.adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))
    state=v.state();raw,events=v.events()
    assert state['simulated_purchases']==1 and sum(e['action_type']=='simulated_purchase' for e in events)==1
    (OUT/'double-tap.jsonl').write_text(raw)
    v.adb('shell','am','force-stop',v.PKG);v.launch()
    assert v.state()==state,'确认后进程重启改变了事实'
    record('double-tap-and-restart',state=state)
    # 事件存储为所有页面共用，复用原有下载/广告/导出/重启验收，结果另存。
    v.OUT=OUT/'shared-regression';v.OUT.mkdir()
    v.main()
    record('shared-three-round-regression')
    code=run.main()
    assert code==0,'新版购买六轮验收未通过'
    record('purchase-six-rounds')
    run.save(OUT/'summary.json', {'passed':True,'checks':rows})
except BaseException:
    import traceback
    (OUT/'failure.txt').write_text(traceback.format_exc())
    run.save(OUT/'summary.json',{'passed':False,'checks':rows})
    try:
        (OUT/'failure-logcat.txt').write_text(v.adb('logcat','-d','-t','250'))
    except Exception as error:
        (OUT/'failure-logcat-error.txt').write_text(repr(error))
    raise
finally:
    with (OUT/'stop.log').open('w') as log:
        subprocess.run(['bash',str(ROOT/'scripts/stop.sh')],stdout=log,stderr=log,timeout=60)
