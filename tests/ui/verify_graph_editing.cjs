// Exercise shipped menu/clipboard code, including the drag-release click regression.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
  constructor(tag='div',text='',className=''){this.tag=tag;this.text=text||'';this.className=className;this.children=[];this.dataset={};this.style={};this.hidden=true;this.attributes={};this.classList={add(){},remove(){},toggle(){}};}
  append(...items){for(const item of items){item.parent=this;this.children.push(item);}}
  replaceChildren(...items){this.children=[];this.append(...items);}
  setAttribute(key,value){this.attributes[key]=value;}
  removeAttribute(key){delete this.attributes[key];}
  querySelector(selector){return this.children.find(item=>selector==='button'?item.tag==='button':item.className===selector.slice(1))||this.children.map(item=>item.querySelector(selector)).find(Boolean);}
  replaceWith(item){const items=this.parent.children;items[items.indexOf(this)]=item;item.parent=this.parent;}
  focus(){}
  get offsetWidth(){return 210;}
  get offsetHeight(){return this.children.length*30;}
}
const menu=new Element(),workspace=new Element(),calls=[],listeners=[],storage=new Map(),middleware=[];
const nodes=[{id:'a',type:'blend',name:'Models',scan:{active_scene:'Scene',scenes:[{name:'Scene',camera:'Camera'}]}},{id:'b',type:'blend',name:'Lighting'}];
let systemText='',editable=false;
const c=vm.createContext({state:{project:{id:'project',nodes}},selection:new Set(['a','b']),busy:false,selected:'a',lastPoint:{x:440,y:250},
  window:{pipelineBusy:()=>false},PipelineUI:{graphNodes:{activeGroup:()=>null,addFrame:(...args)=>calls.push(['frame',...args]),addExport:(...args)=>calls.push(['export',...args]),removeNode(){}},use:(...args)=>middleware.push(args)},
  document:{activeElement:{matches:()=>editable},querySelector:()=>null,addEventListener:(type,callback)=>listeners.push({type,callback})},
  sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},navigator:{clipboard:{writeText:async text=>{systemText=text;},readText:async()=>systemText}},
  innerWidth:1000,innerHeight:700,inspectorOpen:true,inspectorTab:'',inspectorToggle:{click(){}},
  $:id=>id==='contextMenu'?menu:workspace,button:(text,action)=>Object.assign(new Element('button',text),{onclick:action}),el:(tag,text,cls)=>new Element(tag,text,cls),blenderIcon:()=>new Element('svg','','blIcon'),
  topSelection:()=>nodes,emptyCanvas:()=>true,worldPoint:(x,y)=>({x,y}),placement:()=>({x:0,y:0}),reportedOpen:()=>false,
  pick:id=>{c.selected=id;},createFolderHere:(...args)=>calls.push(['folder',...args]),run:async(action,args)=>{calls.push([action,args]);},
  status:text=>calls.push(['status',text]),error:text=>calls.push(['error',text]),render(){},reveal(){},editGraph(){},openRenderManager(){},collectLibrary(){},deleteFolder(){},configureRender(){},modal(){}
});
const load=file=>vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/js',file),'utf8'),c,{filename:file});
load('graph_clipboard.js');load('graph_menu.js');
const labels=()=>menu.children.filter(item=>item.tag==='button').map(item=>item.attributes['aria-label']);
const action=label=>menu.children.find(item=>item.attributes['aria-label']===label).onclick();
const outside={closest:()=>null};
const click=event=>listeners.filter(l=>l.type==='click').forEach(l=>l.callback(event));
(async()=>{
  workspace.oncontextmenu({preventDefault(){},target:outside,clientX:200,clientY:300});
  assert.deepEqual(labels(),['Blend node','Render node','Export node','Folder node','Frame']);
  action('Folder node');assert.equal(calls.pop()[3],true,'Folder wraps a selection');
  action('Frame');assert.equal(calls.pop()[2],true,'Frame wraps a selection');
  c.nodeMenu(nodes[0],{getBoundingClientRect:()=>({left:30,bottom:100})});
  assert.deepEqual(labels(),['Details','Copy','Duplicate','Delete file…'],'avoid redundant node actions');
  const panel=menu.children.find(item=>item.className==='graphSubmenu').children[1];
  panel.children.find(item=>item.attributes['aria-label']==='Purple').onclick();
  assert.deepEqual(Array.from(calls.at(-1)[1].node_ids),['a','b']);assert.equal(calls.at(-1)[1].color,'purple');
  const event={clientX:400,clientY:350,timeStamp:100};
  c.window.pipelineOfferOutputNodes(nodes[0],{x:30,y:40},event);
  assert.deepEqual(labels(),['Folder','Render','Export']);
  click({...event,timeStamp:105,target:outside});assert.equal(menu.hidden,false,'synthetic release click must not close output picker');
  click({...event,timeStamp:120,target:outside});assert.equal(menu.hidden,true,'a later outside click closes it');
  c.window.pipelineOfferOutputNodes(nodes[0],{x:30,y:40},event);action('Render');
  assert.equal(calls.at(-1)[0],'render_node');assert.deepEqual(Array.from(calls.at(-1)[1].source_ids),['a']);assert.equal(calls.at(-1)[1].x,30);
  action('Export');assert.equal(calls.at(-1)[0],'export');assert.equal(calls.at(-1)[2],'a');
  c.state.project.id='other';const count=calls.length;action('Render');assert.equal(calls.length,count,'stale picker cannot act in another project');c.state.project.id='project';
  await c.window.PipelineClipboard.copySelection();const payload=JSON.parse(systemText);assert.deepEqual(payload.node_ids,['a','b']);
  await c.window.PipelineClipboard.pasteSelection();const paste=calls.at(-1);assert.equal(paste[0],'paste_nodes');assert.equal(paste[1].clipboard_project_id,'project');assert.equal(paste[1].x,440);
  editable=true;let prevented=false;
  listeners.filter(l=>l.type==='keydown').forEach(l=>l.callback({ctrlKey:true,key:'c',preventDefault:()=>{prevented=true;}}));
  assert.equal(prevented,false,'text editing keeps its own copy shortcut');
  editable=false;c.state.project.id='other';await c.window.PipelineClipboard.pasteSelection();assert.equal(calls.at(-1)[0],'error');
  console.log('PASS: selection-aware creation, compact node actions, batch color choice, usable output drop menus, clipboard positions, text editing and project guards');
})().catch(error=>{console.error(error);process.exitCode=1;});
