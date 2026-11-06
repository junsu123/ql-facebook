"""Behavior tests for the local browser's animated office scene."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_office_view_integrated():
    index = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    app = (ROOT / 'web/assets/app.js').read_text(encoding='utf-8')
    assert index.index('office-live.js') < index.index('app.js')
    assert 'office-live-stage' in app
    assert 'office.toggle' in app
    assert 'office.speed' in app
    assert 'OfficeLive?.update(S.data)' in app
    assert 'officeAgentList' in app
    assert 'Chuyển động minh họa' in (ROOT / 'web/assets/office-live.js').read_text(encoding='utf-8')


def test_office_animation_engine_with_node():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable; skip JS runtime test')
    script = r'''const assert=require('assert');
const fs=require('fs');const vm=require('vm');
const events=[];
const canvas={style:{},width:0,height:0,setAttribute(){},addEventListener(){},removeEventListener(){},remove(){events.push('removed');},getContext(){return {setTransform(){}};},setPointerCapture(){}};
const host={appendChild(){},getBoundingClientRect(){return {width:1100,height:670}}};
const win={devicePixelRatio:1,matchMedia:()=>({matches:false}),addEventListener(){},removeEventListener(){}};
const sandbox={window:win,document:{createElement:()=>canvas},ResizeObserver:class{observe(){}disconnect(){}},requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{},console,Math};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('web/assets/office-live.js','utf8'),sandbox);
const ids=['ceo','research','strategy','content','creative','publishing','customer','analytics','compliance'];
const data={agents:ids.map(id=>({id,name:'AI '+id,active_tasks:id==='content'?1:0,queued_tasks:id==='research'?1:0})),activities:[]};
const office=win.OfficeLive.mount(host,data,()=>{});
assert.equal(office.staff.length,9);
assert.equal(office.staff.find(p=>p.id==='content').busy,true);
assert.equal(office.staff.find(p=>p.id==='research').queued,true);
let moving=false,met=false,returned=false;
for(let j=0;j<2000;j++){
  office.update(.025);
  if(office.staff.some(p=>p.state==='walk'))moving=true;
  if(office.chat?.show)met=true;
  if(met&&!office.chat&&office.staff.every(p=>!p.meeting)){returned=true;break;}
}
assert(moving,'two agents should walk to discuss');
assert(met,'agents should reach the conversation location');
assert(returned,'agents should return to work after conversation');
const wasPaused=office.paused;assert.equal(office.toggle(),!wasPaused);
assert.equal(office.setSpeed(),1.75);
office.zoomAt(1.16);assert(office.zoom>1);
office.resetCamera();assert.equal(office.zoom,1);
win.OfficeLive.update({agents:ids.map(id=>({id,active_tasks:0,queued_tasks:0})),activities:[]});
assert(!office.staff.some(p=>p.busy));
win.OfficeLive.unmount();assert(events.includes('removed'));assert.equal(win.OfficeLive.current,null);
console.log('office animation tests: passed');'''
    completed = subprocess.run([node, '-e', script], cwd=ROOT, capture_output=True, text=True, timeout=12)
    assert completed.returncode == 0, completed.stdout + '\n' + completed.stderr


def test_office_javascript_syntax():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable; skip JS syntax validation')
    for path in ('office-live.js', 'app.js'):
        result = subprocess.run([node, '--check', str(ROOT / 'web/assets' / path)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
