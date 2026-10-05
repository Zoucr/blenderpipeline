// Exercise production drop handlers and the asynchronous create-then-pick flow.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=file=>fs.readFileSync(path.join(__dirname,'../../web/js',file),'utf8').replaceAll('\r\n','\n');
function excerpt(file,start,end){const text=source(file),a=text.indexOf(start),b=text.indexOf(end,a);assert(a>=0&&b>a);return text.slice(a,b);}
const calls=[],listeners=[],fields={append(){}},submit={},workspace={contains:hit=>hit.inside};
let dialog,hit;
const c=vm.createContext({window:{pipelineBusy:()=>false},state:{project:{id:'project',nodes:[{id:'source',name:'Models',type:'blend'}]}},busy:false,wire:null,
  $:id=>id==='workspace'?workspace:id==='fields'?fields:id==='submit'?submit:{remove(){}},
  document:{addEventListener:(type,callback,capture)=>listeners.push({type,callback,capture:!!capture}),elementFromPoint:()=>hit,querySelectorAll:()=>[]},
  emptyCanvas:({target})=>!target.blocked,worldPoint:(x,y)=>({x:x/2,y:y/2}),muted:text=>text,
  modal:(title,fields,callback)=>{dialog={title,callback};},error:text=>calls.push(['error',text]),status:text=>calls.push(['status',text]),
  batchLinkDialog:(...args)=>calls.push(['pick',...args]),dataLinkDialog:(...args)=>calls.push(['existing',...args]),
  configureRender:(node,id)=>calls.push(['output',node.id,id]),clearLinkDrag(){},
  run:async(action,args)=>{calls.push(['run',action,args]);const next={project:{id:'project',nodes:[...c.state.project.nodes,{id:'created',type:'blend'}]}};c.state=next;return next;}
});
vm.runInContext(excerpt('linking.js','// A connector dropped','function batchLinkDialog'),c);
const offer=c.window.pipelineOfferLinkedFile;
c.window.pipelineOfferOutputNodes=(node,p)=>calls.push(['output-menu',node.id,p]);
vm.runInContext(excerpt('workspace.js',"// Handle output-folder wires","document.addEventListener('pointerup',e=>{\n  if(move?.type"),c);
vm.runInContext(excerpt('assets.js',"document.addEventListener('pointerup',e=>{if(!wire?.asset)","if(state.project)render();"),c);
vm.runInContext(excerpt('ui.js',"document.addEventListener('pointerup',e=>{\n  if(!wire)","$('workspace').ondblclick="),c);
const target=(inside=true,blocked=false,blend=null,folder=null)=>({inside,blocked,closest:selector=>selector==='.node.blend'||selector==='[data-target]'?blend?{dataset:{id:blend,target:blend}}:null:selector==='.node.folder'?folder?{dataset:{id:folder}}:null:null});
const drop=wire=>{c.wire=wire;let stopped=false;const event={clientX:840,clientY:520,stopImmediatePropagation:()=>stopped=true};for(const listener of [...listeners.filter(l=>l.capture),...listeners.filter(l=>!l.capture)]){if(stopped)break;listener.callback(event);}assert.equal(c.wire,null);};
async function main(){
  hit=target();drop({asset:'source'});assert.equal(dialog.title,'Create a linked Blend File here?');assert.equal(calls.filter(c=>c[0]==='run').length,0,'a drop must ask before creating');
  await dialog.callback();assert.deepEqual(JSON.parse(JSON.stringify(calls.find(c=>c[0]==='run'))),['run','blend',{folder_id:null,x:420,y:260}]);assert.deepEqual(calls.find(c=>c[0]==='pick'),['pick','source','created',undefined]);
  calls.length=0;c.state.project.nodes=c.state.project.nodes.filter(n=>n.id!=='created');hit=target(true,false,null,'parent');drop({source:'source',collection:'Hero'});await dialog.callback();assert.equal(calls.find(c=>c[0]==='run')[2].folder_id,'parent');assert.equal(calls.find(c=>c[0]==='pick')[3].name,'Hero');
  calls.length=0;hit=target(true,true,'existing');drop({asset:'source',preset:{kind:'materials',name:'Metal'}});assert.equal(calls[0][0],'existing');assert.equal(calls[0][2],'existing');
  calls.length=0;hit=target(false);drop({asset:'source'});assert.deepEqual(calls,[['status','Link cancelled']]);
  calls.length=0;hit=target(true,true);drop({source:'source',collection:'Hero'});assert.deepEqual(calls,[['status','Link cancelled']]);
  calls.length=0;hit=target();drop({render:'source'});assert.equal(calls[0][0],'output-menu');assert.equal(calls[0][2].x,420);
  calls.length=0;hit=target(true,true,null,'output');drop({render:'source'});assert.deepEqual(calls,[['output','source','output']]);
  calls.length=0;hit=target();offer('source',hit,{clientX:10,clientY:20});c.run=async()=>undefined;await dialog.callback();assert.equal(calls.length,0,'failed creation must not open a linking picker');
  offer('source',hit,{clientX:10,clientY:20});c.state.project.id='other';await dialog.callback();assert.equal(calls[0][0],'error','changing projects must not create in the wrong project');
  console.log('PASS: asset/collection empty drops, confirmed exact-position creation, folder parent, preselection, existing targets, invalid drops, output folder routing and failed/context-changed creation');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
