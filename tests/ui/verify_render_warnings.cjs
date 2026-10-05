// Exercise the shipped consent middleware through the real lifecycle registry.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {createRuntime}=require('../../web/js/ui_runtime.js');
class Element{
  constructor(tag,text,cls){this.tag=tag;this.textContent=text||'';this.className=cls||'';this.children=[];this.listeners=[];this.open=true;}
  append(...items){this.children.push(...items);}
  prepend(...items){this.children.unshift(...items);}
  addEventListener(type,fn,options){this.listeners.push({type,fn,options});}
  close(){this.open=false;const listeners=this.listeners.filter(item=>item.type==='close');this.listeners=this.listeners.filter(item=>item.type!=='close'||!item.options?.once);for(const item of listeners)item.fn();}
}
const warnings=[{source_id:'source',source_name:'Models',name:'Unused alpha',path:'F:\\Textures\\alpha.png',reason:'Image file is missing · Outside the project'}];
function fixture(){
  const runtime=createRuntime(),elements=Object.fromEntries(['dialog','fields','submit'].map(key=>[key,new Element()])),calls=[],modals=[],messages=[];
  let sequence=0,resolved=false;
  const c=vm.createContext({PipelineUI:runtime,state:{project:{id:'project'},jobs:[]},
    el:(...args)=>new Element(...args),muted:text=>new Element('span',text),$:id=>elements[id],
    modal:(title,fields,callback)=>{elements.dialog.open=true;modals.push({title,callback});},status:message=>messages.push(message),error:message=>messages.push(message),
    button:(text,callback)=>Object.assign(new Element('button',text),{onclick:callback}),api:async()=>({path:''}),
    renderRunEntry:()=>new Element('div'),queueEntry:()=>new Element('div')});
  runtime.define('run',async(action,args)=>{
    calls.push({action,args});
    if(action==='locate_render_image')resolved=true;
    const success=args.allow_image_warnings||resolved;
    const job={id:String(++sequence),action,project_id:c.state.project.id,status:success?'Complete':'Failed',
      ...(success?{}:{error_code:'render_image_warnings',dependency_warnings:warnings})};
    c.state={...c.state,jobs:[...c.state.jobs,job]};return c.state;
  });
  c.run=(...args)=>runtime.call('run',...args);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/js/render_warnings.js'),'utf8'),c);
  return {c,elements,calls,modals,messages};
}
const nextTurn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  const f=fixture(),args={node_id:'shot',overrides:{samples:32}};
  const pending=f.c.run('queue_render',args);await nextTurn();
  assert.equal(f.modals.length,1);assert.equal(f.elements.submit.textContent,'Render anyway');
  await f.modals[0].callback();f.elements.dialog.close();
  const result=await pending;assert.equal(result.jobs.at(-1).status,'Complete');
  assert.equal(f.calls[1].args.allow_image_warnings,true);
  assert.deepEqual(f.calls[1].args.accepted_image_warnings,warnings);
  assert.equal(args.allow_image_warnings,undefined,'consent must not alter saved arguments');
  assert.equal(f.calls[1].args.overrides.samples,32);
  const repeated=f.c.run('queue_render',args);await nextTurn();
  assert.equal(f.modals.length,2,'a new submission asks again');
  f.elements.dialog.close();assert.equal(await repeated,undefined);assert.equal(f.calls.length,3,'cancel adds no approved submission');
  const changed=fixture(),stale=changed.c.run('queue_batch',{node_ids:['shot']});await nextTurn();
  changed.c.state.project.id='other';await changed.modals[0].callback();changed.elements.dialog.close();await stale;
  assert.equal(changed.calls.length,1,'confirmation cannot submit to a different project');
  assert.match(changed.messages[0],/project changed/);
  const clean=fixture();clean.c.PipelineUI.use('run','successful-submit',1000,async()=>clean.c.state);
  await clean.c.run('queue_render',{});assert.equal(clean.modals.length,0,'old or absent warning jobs never trigger confirmation');
  await clean.c.run('refresh',{});assert.equal(clean.modals.length,0,'non-render actions remain unchanged');
  const entry=f.c.renderRunEntry({dependency_warnings:warnings});assert.match(entry.children[0].children[0].textContent,/image warnings · 1/);
  const queue=f.c.queueEntry({dependency_warnings:warnings});assert.match(queue.children[0].textContent,/acknowledged · 1/);
  const located=fixture(),findLocate=()=>located.elements.fields.children[1].children[0].children.at(-1);
  const waiting=located.c.run('queue_batch',{node_ids:['shot'],overrides:{samples:64}});await nextTurn();
  await findLocate().onclick();assert.equal(located.calls.length,1,'canceling the picker leaves the warning open');
  assert.equal(located.elements.dialog.open,true);assert.equal(located.elements.submit.disabled,false);
  located.c.api=async(action,args)=>{assert.equal(action,'choose_system_path');assert.equal(args.mode,'file');return {path:'C:/found.png'};};
  await findLocate().onclick();await waiting;
  assert.equal(located.calls[1].action,'locate_render_image');assert.equal(located.calls[1].args.replacement,'C:/found.png');
  assert.equal(located.calls[2].action,'queue_batch');assert.equal(located.calls[2].args.allow_image_warnings,undefined,'locating must revalidate instead of granting consent');
  assert.equal(located.calls[2].args.overrides.samples,64);assert.equal(located.elements.dialog.open,false);
  const notice=f.c.queueEntry({image_notices:warnings});assert.match(notice.children[0].textContent,/Unused missing images/);
  console.log('PASS: per-submission consent, locate/picker cancellation, automatic revalidation, settings preservation, project guards and version/queue notices');
})().catch(error=>{console.error(error);process.exitCode=1;});
