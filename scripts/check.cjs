// Run with node scripts/check.cjs. No dependencies, no network or GitHub writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
process.chdir(path.join(__dirname,'..'));
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id,{textContent:'',innerHTML:'',dataset:{},style:{},children:[],
    classList:{contains:()=>false,add(){},remove(){},toggle(){}},addEventListener(){},setAttribute(){},querySelectorAll:()=>[]});
  return elements.get(id);
};
const sandbox = {console,Date,URL,URLSearchParams,AbortSignal,setInterval(){},setTimeout(){},clearTimeout(){},
  document:{getElementById:element,addEventListener(){},hidden:false},window:{addEventListener(){}},location:{hostname:'localhost',search:'?data=local'}};
const code = fs.readFileSync('index.html','utf8').split('<script>')[1].split('</script>')[0].replace('refresh(false);\nsetInterval','setInterval');
vm.createContext(sandbox);vm.runInContext(code,sandbox);
const run = code => vm.runInContext(code,sandbox);
const now = Date.now(), hour=3600000;
sandbox.now=now;
run(`inprogressByArea = {Demo:[{branch:'parity/keyboard-shortcuts'},{branch:'parity/keyboard-shortcuts'}]}`);
const mixed = {name:'Demo',doneItems:['Done'],pendingItems:[{text:'Keyboard shortcuts reference'},{text:'Keyboard customizable key bindings'},{text:'Blocked keyboard shortcuts',blocked:true}]};
sandbox.mixed=mixed;
// Duplicate records should be filtered before state matching. No item can be blocked and active.
let counts=run('areaCounts(mixed)');
assert.equal(counts.done+counts.active+counts.queued+counts.blocked,counts.total);
assert.equal(counts.blocked,1);assert.ok(counts.active<=2);assert.ok(!counts.activeIndexes.has(2));
assert.equal(run(`areaCounts({name:'Demo',doneItems:['Done'],pendingItems:[]}).active`),0);
const blocked=run(`areaCounts({name:'Demo',doneItems:[],pendingItems:[{text:'Blocked',blocked:true}]})`);
assert.equal(blocked.blocked,blocked.total);
sandbox.blocked=blocked;
assert.match(run(`statusBar(blocked,'Demo')`),/blocked-only/);
assert.doesNotMatch(run(`statusBar(blocked,'Demo')`),/segment (done|active|queued)/);
assert.match(run(`statusBar({total:0},'Demo')`),/No checklist/);
assert.equal(run(`loopState({updated_at:new Date(now-1000).toISOString(),last_evidence_at:new Date(now-2*3600000).toISOString(),current:{phase:'implementing'},stale:true},now).label`),'Evidence overdue');
assert.equal(run(`loopState({updated_at:new Date(now-2*3600000).toISOString(),last_evidence_at:new Date(now).toISOString()},now).label`),'Heartbeat overdue');
assert.equal(run(`loopState({updated_at:'invalid'},now).label`),'No heartbeat');
assert.equal(run(`loopState({updated_at:new Date(now).toISOString(),current:{phase:'implementing'}},now).label`),'No work evidence');
assert.equal(run(`loopState({updated_at:new Date(now).toISOString(),parked:true},now).label`),'Parked');
assert.equal(run(`loopState({updated_at:new Date(now).toISOString(),current:{phase:'blocked'}},now).tone`),'blocked');
assert.equal(run(`loopState({updated_at:new Date(now).toISOString(),last_evidence_at:new Date(now).toISOString(),current:{phase:'gating'}},now).tone`),'wip');
const points = [0,1,2,3].map(i=>({t:new Date(now-(3-i)*hour).toISOString(),done:70+i*2,total:100}));
sandbox.points=points;
let model=run('forecast(points,now)');
assert.ok(Math.abs(model.slope-48)<1e-8);assert.ok(Math.abs(model.days-.5)<1e-8);
assert.equal(run('forecast(points.map(p=>({...p,done:70})),now).days'),null);
assert.equal(run('forecast(points.map((p,i)=>({...p,done:80-i})),now).days'),null);
assert.equal(run('forecast(points.slice(-2),now)'),null);
assert.equal(run('forecast(points,now+3600000).stale'),true);
assert.equal(run('forecast(points.map((p,i)=>({...p,total:i===3?101:100})),now)'),null);
assert.equal(run(`trendPoints({points:[...points,...points]}, {at:points[0].t,done:80,total:100},0).length`),4);
assert.equal(run(`trendPoints({points:[...points,{t:'invalid',done:0,total:0}]},null,0).length`),4);
assert.equal(run(`validCounts({done:101,total:100})`),false);
assert.equal(run(`pctText(9999,10000)`),'99.9');
assert.equal(run(`pctText(10000,10000)`),'100.0');
assert.equal(run(`pctText(0,0)`),'0.0');
assert.equal(run(`validFeed('areas.json',{areas:[{name:'Bad',done:[],pending:[null]}]})`),false);
assert.equal(run(`safeURL('javascript:alert(1)')`),'#');
assert.equal(run(`safeURL('https://evil.example/')`),'#');
assert.equal(run(`ago(undefined)`),'unknown');
const feeds=Object.fromEntries(['github.json','loops.json','parity-history.json','areas.json','inprogress.json'].map(f=>[f,JSON.parse(fs.readFileSync(f,'utf8'))]));
sandbox.feeds=feeds;
run(`Object.assign(bodies,feeds);githubPayload(bodies['github.json']);renderLoops(bodies['loops.json']);`);
assert.doesNotMatch(element('loops').innerHTML,/native code|Loop undefined/);
assert.match(element('loops').innerHTML,/S18 sticker-suggest/);
const originalWorkCount=run(`inprogressByArea['Auth & accounts'].length`);
run(`bodies['inprogress.json'].items.push({...bodies['inprogress.json'].items[0]});githubPayload(bodies['github.json']);`);
assert.equal(run(`inprogressByArea['Auth & accounts'].length`),originalWorkCount);
run(`bodies['inprogress.json'].items.push({area:'Demo',pr:216,branch:'merged-branch'});githubPayload(bodies['github.json']);`);
assert.equal(run(`inprogressByArea.Demo`),undefined);
// Fetch failures/malformed responses preserve last-valid data independently.
sandbox.fetch=async url=>({ok:true,status:200,headers:{get:()=>new Date(now).toUTCString()},json:async()=>url==='loops.json'?{loops:null}:feeds[url]});
(async()=>{
  const result = await run('loadFeeds()');assert.ok(result.failures.includes('loops.json'));assert.equal(run('bodies["loops.json"].loops.length'),4);
  sandbox.fetch=async()=>{throw new Error('Offline');};
  const offline = await run('loadFeeds()');assert.equal(offline.failures.length,5);assert.equal(run('bodies["github.json"].parity.done'),feeds['github.json'].parity.done);
  // The live branch is an atomic, single-request feed; outage/corruption cannot downgrade it.
  const liveSandbox={...sandbox,location:{hostname:'shinycake.github.io',search:''}};
  vm.createContext(liveSandbox);vm.runInContext(code,liveSandbox);
  const runLive=expression=>vm.runInContext(expression,liveSandbox);
  let requests=0;
  const bundle={generated_at:new Date(now).toISOString(),feeds};
  liveSandbox.fetch=async url=>{requests++;return {ok:!url.includes('/quill/'),status:url.includes('/quill/')?404:200,headers:{get:()=>null},json:async()=>bundle};};
  const fallback=await runLive('loadFeeds()');assert.equal(requests,2);assert.equal(fallback.failures.length,0);
  assert.equal(runLive('activeBundleURL'),runLive('BUNDLE_URLS[1]'));
  requests=0;
  liveSandbox.fetch=async()=>{requests++;return {ok:true,status:200,headers:{get:()=>null},json:async()=>bundle};};
  await runLive('loadFeeds()');assert.equal(requests,1);assert.equal(runLive('activeBundleURL'),runLive('BUNDLE_URLS[0]'));
  assert.equal(runLive(`sourceTimes['github.json']`),bundle.generated_at);
  const corrupt=JSON.parse(JSON.stringify(bundle));corrupt.feeds['github.json'].parity.done++;
  liveSandbox.fetch=async()=>({ok:true,status:200,headers:{get:()=>null},json:async()=>corrupt});
  const rejected=await runLive('loadFeeds()');assert.deepEqual(Array.from(rejected.failures),['repository snapshot']);assert.equal(runLive(`bodies['github.json'].parity.done`),feeds['github.json'].parity.done);
  // A malformed optional report must not freeze the authoritative parity/PR snapshot.
  const optional=JSON.parse(JSON.stringify(bundle));optional.feeds['loops.json']={loops:null};
  liveSandbox.fetch=async()=>({ok:true,status:200,headers:{get:()=>null},json:async()=>optional});
  const partial=await runLive('loadFeeds()');assert.ok(partial.failures.includes('loops.json'));assert.equal(runLive(`bodies['loops.json'].loops.length`),4);
  const older={...bundle,generated_at:new Date(now-60000).toISOString()};
  liveSandbox.fetch=async()=>({ok:true,status:200,headers:{get:()=>null},json:async()=>older});
  assert.equal((await runLive('loadFeeds()')).failures.length,1);assert.equal(runLive('lastBundleAt'),now);
  requests=0;liveSandbox.fetch=async()=>{requests++;throw new Error('Offline');};
  const bundleOffline=await runLive('loadFeeds()');assert.equal(requests,1);assert.equal(bundleOffline.failures.length,1);
  // The publisher API is faked: verify atomic tree/commit/ref writes and unchanged-data skip.
  execFileSync('python3',['-c', String.raw`
import base64, importlib.util, json, subprocess, tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('publisher','scripts/publish-data.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
data=p.snapshot(Path('.'));calls=[]
def fake(args, **kwargs):
    path=args[2]; payload=json.loads(kwargs['input']) if kwargs.get('input') else None;calls.append((path,payload))
    if '/git/ref/' in path: return subprocess.CompletedProcess(args,1,'','HTTP 404')
    if path.endswith('/git/trees'): value={'sha':'tree'}
    elif path.endswith('/git/commits'):
        assert payload['parents']==[];value={'sha':'commit'}
    else:
        assert payload['ref']=='refs/heads/codex/dashboard-data' and payload['sha']=='commit';value={}
    return subprocess.CompletedProcess(args,0,json.dumps(value),'')
p.subprocess.run=fake;p.publish(data,'example/repo');assert len(calls)==4
assert calls[1][1]['tree'][0]['path']=='data.json'
assert json.loads(calls[1][1]['tree'][0]['content'])['feeds']==data['feeds']
def unchanged(args,**kwargs):
    path=args[2]
    if '/git/ref/' in path: value={'object':{'sha':'parent'}}
    else:
        assert '/contents/data.json' in path;value={'content':base64.b64encode(json.dumps(data).encode()).decode()}
    assert args[args.index('--method')+1]=='GET'
    return subprocess.CompletedProcess(args,0,json.dumps(value),'')
p.subprocess.run=unchanged;p.publish(data,'example/repo')
def race(args,**kwargs):
    path=args[2];payload=json.loads(kwargs['input']) if kwargs.get('input') else None
    if '/git/ref/' in path:value={'object':{'sha':'parent'}}
    elif '/contents/' in path:value={'content':base64.b64encode(json.dumps({'feeds':{}}).encode()).decode()}
    elif path.endswith('/git/trees'):value={'sha':'tree'}
    elif path.endswith('/git/commits'):
        assert payload['parents']==['parent'];value={'sha':'child'}
    else:
        assert payload=={'sha':'child','force':False}
        return subprocess.CompletedProcess(args,1,'','HTTP 422: non-fast-forward')
    return subprocess.CompletedProcess(args,0,json.dumps(value),'')
p.subprocess.run=race
try:p.publish(data,'example/repo');raise AssertionError('Concurrent publish was overwritten')
except RuntimeError:pass
with tempfile.TemporaryDirectory() as tmp:
    for name,feed in data['feeds'].items(): Path(tmp,name).write_text(json.dumps(feed))
    gh=json.loads(Path(tmp,'github.json').read_text());gh['parity']['done']+=1;Path(tmp,'github.json').write_text(json.dumps(gh))
    try:p.snapshot(Path(tmp));raise AssertionError('Mismatched data accepted')
    except ValueError:pass
`],{stdio:'inherit',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  console.log('Dashboard checks passed: state partitions, bounded bars, loop freshness, slope/ETA, feed fallback, and atomic publication.');
})().catch(error=>{console.error(error);process.exitCode=1;});
