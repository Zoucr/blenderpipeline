// Exercise shipped connection routing and dependency UI with sparse saved metadata.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const base=path.join(__dirname,'../../web/js');
const source=fs.readFileSync(path.join(base,'render_nodes.js'),'utf8');
function part(start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert(a>=0&&b>a);return source.slice(a,b);}
const nodes=[{id:'source',type:'blend',name:'Shot',scan:{active_scene:'Main',scenes:[{name:'Detail',camera:'Camera'},{name:'Main',camera:'Camera',active_view_layer:'Beauty',view_layers:[{name:'Beauty',enabled:true},{name:'Mask',enabled:true}]}]}},
  {id:'render',type:'render',name:'Render',render_plan:{folder_id:'folder',targets:[],overrides:{samples:2}}},
  {id:'folder',type:'folder',name:'Outputs',path:'Outputs'}];
const calls=[],context=vm.createContext({state:{project:{nodes}},window:{},crypto:{randomUUID:()=> 'stable-target'},
  status:text=>calls.push({status:text}),run:(action,args)=>calls.push({action,args})});
vm.runInContext(part('  function connectedFiles(','  const previousTargets=')+part('  window.pipelineRenderDrop=','  const exportDrop='),context);
const hit={closest:selector=>selector==='.node.render'?{dataset:{id:'render'}}:null};
assert.equal(context.window.pipelineRenderDrop('source',hit),true);
let request=calls.pop();assert.equal(request.action,'render_node_config');assert.equal(request.args.plan.targets[0].scene,'Main');
assert.equal(request.args.plan.overrides.samples,2);assert.equal(request.args.plan.folder_id,'folder');
assert.equal(request.args.plan.targets[0].view_layer,'Beauty');assert.deepEqual(Array.from(request.args.plan.source_ids),['source']);
nodes[1].render_plan=request.args.plan;
context.window.pipelineRenderDrop('source',hit);assert(calls.pop().status.includes('already connected'));assert.equal(nodes[1].render_plan.targets.length,1);
assert.equal(context.window.pipelineRenderDrop('source',{closest:()=>null}),false);
nodes[0].external=true;assert.equal(context.window.pipelineRenderDrop('source',hit),false);delete nodes[0].external;

const rendering=fs.readFileSync(path.join(base,'rendering.js'),'utf8');
vm.runInContext(rendering.slice(rendering.indexOf('function savedSetupSettings('),rendering.indexOf('function sizeLabel(')),context);
const sampling={engine:'CYCLES',samples:2,layer_samples:'USE',view_layers:[{name:'A',enabled:true,samples:7},{name:'B',enabled:true,samples:9}]};
assert.equal(context.savedSetupSettings(sampling,'A').samples,7);
assert.equal(context.savedSetupSettings(sampling).per_layer_samples,true);
assert.equal(context.savedSetupSettings({...sampling,layer_samples:'IGNORE'},'A').samples,2);
assert.equal(context.savedSetupSettings({...sampling,layer_samples:'BOUNDED'},'B').samples,2);
nodes[0].scan.scenes[1].cameras=['Camera'];
nodes[1].render_plan.targets[0].overrides={width:20};
const proxy={...nodes[0],operation_id:'render',target_id:'stable-target',render_config:{scene:'Main',camera:''}};
assert.equal(context.renderTargetReady(proxy),true);
assert.equal(context.renderSettingOrigin(proxy,'samples'),'Render override');
assert.equal(context.renderSettingOrigin(proxy,'width'),'Setup override');
assert.equal(context.renderSettingOrigin(proxy,'height'),'Saved in Blender');
assert.equal(context.renderSettingOrigin(proxy,'samples',{samples:4}),'Batch override');
assert.equal(context.renderTargetReady({...proxy,render_config:{scene:'Renamed'}}),false);
assert.equal(context.savedRender({...proxy,render_config:{scene:'Renamed'}}).name,undefined,'missing explicit scenes must never silently fall back to another scene');
assert.equal(context.renderTargetReady({...proxy,render_config:{scene:'Main',view_layer:'Removed'}}),false);
nodes[0].scan.scenes[1].compositor_dependencies=[{scene:'Main',view_layer:'Mask'}];
const setup=nodes[1].render_plan.targets[0];
assert(context.setupIssues(nodes[0],setup)[0].includes('Compositor needs Main / Mask'));
assert.equal(context.setupIssues(nodes[0],{...setup,compositor:'OFF'}).length,0);
assert.equal(context.setupIssues(nodes[0],{...setup,view_layer:''}).length,0);
vm.runInContext(rendering.slice(rendering.indexOf('function queueInScope('),rendering.indexOf('function scopeRuns(')),context);
context.rm={scope:null,nodeIds:null};assert.equal(context.queueInScope({operation_id:'removed-operation'},[]),true);
context.rm={scope:'render',nodeIds:null};assert.equal(context.queueInScope({operation_id:'render',target_key:'removed-setup'},[]),true);
assert.equal(context.queueInScope({operation_id:'other'},[]),false);
context.rm={scope:null,nodeIds:['render:main']};assert.equal(context.queueInScope({target_key:'render:main'},[{id:'render:main'}]),true);
assert.equal(context.queueInScope({target_key:'other'},[{id:'render:main'}]),false);

function element(tag,text){return {tag,text,children:[],classList:{toggle(){}},append(...items){this.children.push(...items);},prepend(...items){this.children.unshift(...items);}};}
const inspector=element('aside'),hooks={};
const healthContext=vm.createContext({state:{project:{id:'project',nodes,renders:[],exports:[]},health:{nodes:{},outputs:{renders:{},exports:{}}}},
  selected:'render',PipelineUI:{use:(name,id,order,callback)=>hooks[name]=callback},problem:()=> 'Ready',
  el:element,muted:text=>element('p',text),section:(name,...children)=>{const e=element('section',name);e.append(...children);return e;},
  button:text=>element('button',text),$:()=>inspector,renderRunEntry:()=>element('article'),paintVersionList:()=>{},
  scopeRuns:()=>[],focusNode:()=>{},run:()=>{},document:{querySelector:()=>null}});
vm.runInContext(fs.readFileSync(path.join(base,'dependency_status.js'),'utf8'),healthContext);
hooks.inspect(()=>{});assert(inspector.children.some(e=>e.tag==='details'),'Render nodes without scan/content history must have a valid dependency panel');
assert.equal(healthContext.problem(nodes[1]),'Ready');
const old={id:'old',status:'Complete',node_id:'source',operation_id:'render',target_id:'main',config:{scene:'Main'},output:'Outputs/old'};
healthContext.state.project.renders=[old];healthContext.state.health.outputs.renders.old={outdated:true};
assert.equal(healthContext.problem(nodes[1]),'Outputs outdated');
healthContext.state.project.renders.push({...old,id:'fresh'});healthContext.state.health.outputs.renders.fresh={outdated:false};
assert.equal(healthContext.problem(nodes[1]),'Ready','historical versions must not make a fresh target stale');
healthContext.state.health.nodes.render={reasons:[{kind:'unsaved_upstream',source_id:'source'}],upstream:['source'],affected:[]};
assert.equal(healthContext.problem(nodes[1]),'Unsaved source edits');
hooks.inspect(()=>{});
console.log('PASS: active-scene render connections, preserved shared settings, duplicate/external guards, sparse operation inspectors and latest-target dependency badges');
