// Keep editor ownership, submission selection and lazy settings loading independent.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../../web/js/rendering.js'),'utf8');
const calls=[];
function element(){return {children:[],dataset:{},classList:{add(){}},append(...children){this.children.push(...children);},prepend(...children){this.children.unshift(...children);},querySelector(){return this;}};}
const context=vm.createContext({state:{project:{nodes:[{id:'a',name:'Beauty'},{id:'b',name:'Masks'}]}},
  window:{pipelineRenderPlanEditor:(node,options)=>{calls.push({node:node.id,options});return {root:element(),dirty:()=>false};}},
  renderFileEditor:node=>{calls.push({file:node.id});return {root:element(),dirty:()=>false};},
  el:element,button:element,renderPanel:element});
vm.runInContext(source.slice(source.indexOf('function connectedRenderEditors('),source.indexOf('function folderRenderDetails(')),context);
const targets=[{operation_id:'a',target_id:'red'},{operation_id:'a',target_id:'blue'},{operation_id:'b',target_id:'mask'},{id:'direct',name:'Direct file'}];
const folderEditors=context.connectedRenderEditors(element(),targets);
assert.equal(folderEditors.length,3);assert.deepEqual(calls.map(c=>c.node||c.file),['a','b','direct'],'each operation gets one editor, preserving sibling setup drafts');
assert(calls.slice(0,2).every(c=>c.options.context==='folder'&&c.options.targetIds===undefined));
calls.length=0;
context.connectedRenderEditors(element(),targets.slice(0,3),'workspace',{selection:{has(){return true;},change(){}}});
assert.deepEqual(Array.from(calls[0].options.targetIds),['red','blue']);assert.deepEqual(Array.from(calls[1].options.targetIds),['mask']);
assert(calls[0].options.selection,'workspace submission selection is separate from the saved enabled flag');

const catalogue=fs.readFileSync(path.join(__dirname,'../../web/js/render_settings_ui.js'),'utf8');
let loads=0;const saved={'["cycles","adaptive_threshold"]':.25};
const lazyContext=vm.createContext({renderPanel:()=>({open:false,append(){},ontoggle(){}}),
  lazyRenderSettings:()=>({load:()=>loads++,read:()=>saved})});
vm.runInContext(catalogue.slice(catalogue.indexOf('function renderSettingsCatalogue(')),lazyContext);
const editor=lazyContext.renderSettingsCatalogue(element(),saved,()=>{},'project:setup');
assert.equal(loads,0,'opening a basic setup must not launch Blender for its advanced catalog');
assert.deepEqual(editor.read(),saved,'unloaded advanced overrides survive saving other properties');
editor.panel.open=true;editor.panel.ontoggle();assert.equal(loads,1);

(async()=>{
  const order=[];
  assert.equal(await context.saveRenderEditors([
    {dirty:()=>true,save:async()=>{await Promise.resolve();order.push('first');return {}; }},
    {dirty:()=>false,save:()=>{throw Error('unchanged editor should not save');}},
    {dirty:()=>true,save:async()=>{order.push('second');return {};}}
  ]),true);
  assert.deepEqual(order,['first','second'],'saving finishes in revision order before a render submission');
  assert.equal(await context.saveRenderEditors([{dirty:()=>true,save:async()=>null},{dirty:()=>true,save:()=>{throw Error('must stop after failed validation');}}]),false);
  console.log('PASS: inline editor ownership, scope-specific selection, preserved unloaded settings, lazy catalog loading and save-before-render sequencing');
})().catch(error=>{console.error(error);process.exitCode=1;});
