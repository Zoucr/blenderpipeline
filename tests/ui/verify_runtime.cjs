const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createRuntime}=require('../../web/js/ui_runtime.js');

async function main(){
  const runtime=createRuntime(),trace=[];
  runtime.define('render',value=>{trace.push('base');return value*2;});
  // Feature registration order may change; explicit order must preserve behavior.
  runtime.use('render','late',20,(next,value)=>{trace.push('late-before');const result=next(value);trace.push('late-after');return result+1;});
  runtime.use('render','early',10,(next,value)=>{trace.push('early-before');const result=next(value);trace.push('early-after');return result+3;});
  assert.equal(runtime.call('render',4),12);
  assert.deepEqual(trace,['late-before','early-before','base','early-after','late-after']);
  runtime.use('render','replacement',30,()=>99);assert.equal(runtime.call('render',4),99);
  assert.throws(()=>runtime.use('render','late',40,()=>{}),/Duplicate/);
  assert.throws(()=>runtime.define('render',()=>{}),/already defined/);
  assert.throws(()=>runtime.call('missing'),/no base/);
  runtime.define('run',async value=>value+1);
  runtime.use('run','render-result',10,async(next,value)=>(await next(value))*3);
  assert.equal(await runtime.call('run',2),9);
  runtime.define('error',async()=>{throw Error('worker failed');});
  await assert.rejects(runtime.call('error'),/worker failed/);
  let state={project:'first'};
  runtime.connectState({state:{get:()=>state,set:value=>{state=value;}}});
  state={project:'second'};assert.equal(runtime.store.state.project,'second');
  runtime.store.state={project:'third'};assert.equal(state.project,'third');
  assert.throws(()=>runtime.connectState({state:{get:()=>state}}),/already connected/);
  const ticks=[],cleared=[],errors=[];
  const polling=createRuntime({setInterval:callback=>{ticks.push(callback);return ticks.length;},clearInterval:id=>cleared.push(id)});
  let finish,calls=0;
  polling.background('status',700,()=>{calls++;return new Promise(resolve=>finish=resolve);});
  polling.background('error',3000,async()=>{throw Error('poll failed');});
  assert.equal(ticks.length,0,'polling must wait for bootstrap');
  polling.startBackground(error=>errors.push(error.message));
  polling.startBackground(error=>errors.push(error.message));assert.equal(ticks.length,2,'start must be idempotent');
  const active=ticks[0]();await ticks[0]();assert.equal(calls,1,'slow polling must not overlap itself');finish();await active;
  await ticks[1]();assert.deepEqual(errors,['poll failed']);
  polling.stopBackground();assert.deepEqual(cleared,[1,2]);
  assert.throws(()=>polling.background('status',500,()=>{}),/Duplicate/);
  const nativeSet=globalThis.setInterval,nativeClear=globalThis.clearInterval;
  try {
    globalThis.setInterval=function(){assert.equal(this,globalThis,'browser timer receiver');return 1;};
    globalThis.clearInterval=function(){assert.equal(this,globalThis,'browser timer cleanup receiver');};
    const browserPolling=createRuntime();browserPolling.background('bound',100,()=>{});
    browserPolling.startBackground(()=>{});browserPolling.stopBackground();
  } finally {globalThis.setInterval=nativeSet;globalThis.clearInterval=nativeClear;}
  const base=path.resolve(__dirname,'../../web/js');
  for(const file of fs.readdirSync(base).filter(file=>file.endsWith('.js'))){
    const source=fs.readFileSync(path.join(base,file),'utf8');new vm.Script(source,{filename:file});
    assert(!/\b(?:render|inspect|pick|paintTasks|paintNavigator|run)\s*=\s*(?:async\s+)?function/.test(source),file+' must register lifecycle extensions instead of overwriting entry points');
  }
  console.log('PASS: deterministic UI extension order, short-circuiting, async results/errors, shared state, deferred non-overlapping polling and production lifecycle ownership.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
