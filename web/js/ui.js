PipelineUI.connectState({state:{get:()=>state,set:value=>{state=value;}},selected:{get:()=>selected,set:value=>{selected=value;}},view:{get:()=>view,set:value=>{view=value;}}});
PipelineUI.define('run',runBase);
function run(...args){return PipelineUI.call('run',...args);}
PipelineUI.define('pick',pickBase);
function pick(...args){return PipelineUI.call('pick',...args);}
PipelineUI.define('inspect',inspectBase);
function inspect(...args){return PipelineUI.call('inspect',...args);}
PipelineUI.define('render',renderBase);
function render(...args){return PipelineUI.call('render',...args);}
const $ = id => document.getElementById(id);
let state = {}, selected = null, view = {x:0,y:0,zoom:1};
let busy = false, move = null, wire = null, layoutTimer, lastPoint = null;
let layoutDirty=false;
const pipelineClient=(()=>{let id=sessionStorage.getItem('pipeline-client');if(!id){id=crypto.randomUUID();sessionStorage.setItem('pipeline-client',id);}return id;})();
const localActions=new Set(['state','projects','settings','ui_preferences','choose_system_path','browse_directory']);
const observed = new Map();
function el(tag,text,cls) { const element=document.createElement(tag); if(text!==undefined)element.textContent=text; if(cls)element.className=cls; return element; }
function nodeFile(n){return state.files?.[n.id]?.resolved_path||(!n.external?state.root+'/'+n.path:'');}
function status(text) { $('status').textContent=text; }
function error(e) { const toast=$('toast');toast.replaceChildren(el('strong','Operation failed'),el('div',String(e.message||e),'errorMessage'),button('Dismiss',()=>toast.style.display='none'));toast.setAttribute('role','alert');toast.style.display='block';status('Operation failed · see error details'); }
async function api(action,args={}) {
  const parameters={...args};
  if(!['projects','settings','choose_system_path','browse_directory'].includes(action))parameters.client_id=pipelineClient;
  if(!localActions.has(action)){
    if(state.project){parameters.project_id??=state.project.id;if(!['project_view','storage_locations','read_render_settings'].includes(action))parameters.expected_revision??=state.project.revision;}
    parameters.request_id??=crypto.randomUUID();
  }
  const headers={'Content-Type':'application/json','X-Pipeline-Token':window.PIPELINE_TOKEN};
  if(parameters.expected_revision!==undefined)headers['If-Match']='"'+parameters.expected_revision+'"';
  const send=()=>fetch('/'+action,{method:'POST',headers,body:JSON.stringify(parameters)});
  let response;
  try{response=await send();}catch(e){if(!parameters.request_id)throw e;response=await send();}
  const result=await response.json();
  if(!response.ok){
    const failure=Error(result.error||'Request failed');failure.code=result.code;
    if(result.code==='revision_conflict'||result.code==='project_context_changed'){
      const fresh=await api('state');
      if(!layoutDirty){state=fresh;render();}
    }
    throw failure;
  }
  return result;
}
async function flushLayout() {
  clearTimeout(layoutTimer);
  if(!layoutDirty)return;
  if(state.project){const result=await api('layout',{nodes:state.project.nodes.map(n=>({id:n.id,x:n.x,y:n.y})),view});state.project.revision=result.project.revision;layoutDirty=false;}
}
async function runBase(action,args={}) {
  if(busy)return; busy=true; status('Working: '+action+'…'); toggleButtons(true);
  const previousIds=new Set((state.project?.nodes||[]).map(n=>n.id));
  try {
    if(state.project&&!['state','load','create','layout'].includes(action))await flushLayout();
    state=await api(action,args); if(state.project)view=state.project.view;
    const added=state.project?.nodes.find(n=>!previousIds.has(n.id));
    if(['blend','import','folder'].includes(action)&&added)selected=added.id;
    render();
    const failures=(state.project?.nodes||[]).filter(n=>n.type==='blend'&&n.scan?.error&&(args.node_id===n.id||!args.node_id));
    if(action==='refresh'&&failures.length)error('Refresh failed: '+failures.map(n=>n.name+': '+n.scan.error).join('\n'));
    else status(state.desktop_warning||(action==='launch'||action==='inspect_snapshot'?'Open request sent to Windows':action==='refresh'?'Saved collections refreshed · unsaved Blender edits are not read':'Ready · '+action+' completed'));
    if(added&&['blend','import','folder'].includes(action))reveal(added);
    return state;
  } catch(e) { error(e); }
  finally { busy=false; toggleButtons(false); $('ghost')?.remove(); }
}
function toggleButtons(disabled) { for(const b of document.querySelectorAll('button'))b.disabled=disabled; }
function button(text,fn,title) { const b=el('button',text); b.type='button'; if(title)b.title=title; b.onclick=e=>{e.stopPropagation(); if(!busy)fn(e);}; return b; }
function modal(title,fields,callback) {
  $('contextMenu').hidden=true;
  $('submit').hidden=false;$('submit').disabled=false;
  $('dialogTitle').textContent=title; $('fields').replaceChildren();
  for(const field of fields) {
    const label=el('label',field.label); $('fields').append(label); let input;
    if(field.type==='select') { input=el('select'); for(const item of field.options) { const o=el('option',item.label);o.value=item.value;input.append(o); } if(field.value!==undefined)input.value=field.value; }
    else { input=el('input'); input.type=field.type||'text'; input.value=field.value||''; input.required=!!field.required;if(field.type==='checkbox'){input.checked=!!field.value;input.dataset.required=String(!!field.required);} }
    input.name=field.key; input.id='field-'+field.key; label.htmlFor=input.id;
    if(field.type==='checkbox') { label.prepend(input); label.style.display='flex';label.style.gap='8px'; }
    else if(['parent','path','source','template','destination','blender'].includes(field.key)&&field.type!=='select'){
      const row=el('div',undefined,'pathPicker');row.append(input,button('Browse…',()=>openPathBrowser(input,field),'Choose '+field.label));$('fields').append(row);
    }else $('fields').append(input);
    if(field.help)$('fields').append(el('p',field.help));
  }
  $('dialog').showModal();
  $('form').onsubmit=e=>{
    e.preventDefault(); const values={};
    for(const input of $('fields').querySelectorAll('input,select'))values[input.name]=input.type==='checkbox'?input.checked:input.value;
    const check=$('fields').querySelector('input[type=checkbox][data-required="true"]');
    if(check&&!check.checked) { check.setCustomValidity('Confirm before continuing.');check.reportValidity();check.onchange=()=>check.setCustomValidity('');return; }
    $('dialog').close();callback(values);
  };
}
$('cancel').onclick=()=>$('dialog').close();
function folders() { return [{label:'Project root',value:''},...(state.project?.nodes||[]).filter(n=>n.type==='folder').map(n=>({label:n.path,value:n.id}))]; }
const folderField=()=>({key:'folder_id',label:'Place in folder',type:'select',options:folders()});
const closedField={key:'closed',required:true,label:'Destination is saved and closed in every Blender window',type:'checkbox',help:'Background edits require a closed destination. You may leave the source open after saving it.'};
$('newProject').onclick=()=>modal('New local project',[{key:'parent',label:'Parent folder (full path)',required:true},{key:'title',label:'Project name',required:true}],v=>run('create',v));
$('openProject').onclick=()=>modal('Open project',[{key:'path',label:'Project folder',required:true}],v=>run('load',v));
function worldPoint(x,y) { const bounds=$('workspace').getBoundingClientRect();return {x:(x-bounds.left-view.x)/view.zoom,y:(y-bounds.top-view.y)/view.zoom}; }
function placement(exact) {
  if(exact)return exact;
  const anchor=lastPoint||worldPoint($('workspace').getBoundingClientRect().left+$('workspace').clientWidth/2,$('workspace').getBoundingClientRect().top+$('workspace').clientHeight/2);
  const occupied=(state.project?.nodes||[]).map(n=>({x:n.x,y:n.y,h:document.querySelector(`[data-id="${n.id}"]`)?.offsetHeight||220}));
  for(let i=0;i<100;i++) { const p={x:Math.round(anchor.x-119)+(i%4)*280,y:Math.round(anchor.y-80)+Math.floor(i/4)*250};if(!occupied.some(n=>p.x<n.x+258&&p.x+258>n.x&&p.y<n.y+n.h+20&&p.y+230>n.y))return p; }
  return {x:anchor.x,y:anchor.y};
}
async function quickCreate(point) {
  if(!state.project)return error('Create or open a project first.');if(busy)return;
  const p=placement(point),folder=state.project.nodes.find(n=>n.id===selected&&n.type==='folder');
  const ghost=el('div','Creating Blend File…','node ghost');ghost.id='ghost';ghost.style.left=p.x+'px';ghost.style.top=p.y+'px';$('nodes').append(ghost);
  await run('blend',{folder_id:folder?.id||null,x:p.x,y:p.y});
}
$('addBlend').title='One-click file creation · Shift-click for template options';
$('addBlend').onclick=e=>{if(e.shiftKey){const p=placement();modal('Create from template',[{key:'title',label:'File name (optional)'},folderField(),{key:'template',label:'Template .blend path (optional)'}],v=>run('blend',{...v,title:v.title||null,folder_id:v.folder_id||null,template:v.template||null,...p}));}else quickCreate();};
$('addFolder').onclick=()=>{if(!state.project)return error('Create a project first.');modal('Create Folder',[{key:'title',label:'Folder name',required:true},folderField()],v=>run('folder',{...v,folder_id:v.folder_id||null,...placement()}));};
$('importFile').onclick=()=>{if(!state.project)return error('Create a project first.');modal('Import Blend File',[{key:'source',label:'Existing .blend path',required:true,help:'External files are copied. Their dependencies are not remapped.'},folderField()],v=>run('import',{...v,folder_id:v.folder_id||null,...placement()}));};
$('refresh').textContent='↻ All';$('refresh').title='Refresh all nodes from saved files';$('refresh').onclick=()=>state.project&&run('refresh');
function transform() {
  $('world').style.transform=`translate(${view.x}px,${view.y}px) scale(${view.zoom})`;
  const spacing=24*view.zoom;$('workspace').style.backgroundSize=`${spacing}px ${spacing}px`;
  $('workspace').style.backgroundPosition=`${view.x}px ${view.y}px`;
}
function persist() {layoutDirty=true;clearTimeout(layoutTimer);layoutTimer=setTimeout(()=>{if(state.project&&!busy)flushLayout().catch(error);},350);}
function pickBase(id) {selected=id;for(const card of $('nodes').children)card.classList.toggle('selected',card.dataset.id===id);inspect();}
function problem(n) {
  if(n.scan?.error)return 'Scan failed';if(state.files?.[n.id]?.changed)return 'Saved file changed · refresh';
  if(n.scan?.refs?.some(r=>!r.exists||r.pattern||!r.relative||!r.inside))return 'Check references';
  return (state.open||[]).includes(n.id)?'Open in Blender':'Ready';
}
function labelEdit(n) {
  pick(n.id);const input=document.querySelector(`[data-id="${n.id}"] .nodeName`);if(input){input.readOnly=false;input.focus();input.select();}
}
function organize(n) {pick(n.id);modal('Collect scene-root objects',[{...closedField,label:'Source file is saved and closed in every Blender window',help:'Creates a normal Scene Contents collection and moves loose root objects into it. A recovery snapshot is created first. Existing collections stay in place.'}],v=>run('organize',{node_id:n.id,closed:v.closed}));}
function renderBase() {
  $('nodes').replaceChildren();$('edges').replaceChildren();$('welcome').hidden=!!state.project;
  $('projectName').textContent=state.project?.name||'No project';$('projectName').title='Pipeline '+(state.build||'1.2');$('recent').replaceChildren();
  for(const r of state.recent||[])$('recent').append(button(r.name,()=>run('load',{path:r.path})));
  for(const n of state.project?.nodes||[]) {
    const card=el('div',undefined,'node '+n.type+(selected===n.id?' selected':''));card.dataset.id=n.id;card.style.left=n.x+'px';card.style.top=n.y+'px';card.onclick=e=>{if(!e.target.closest('header,button,input,.port'))pick(n.id);};
    const head=el('header'),icon=el('span',n.type==='folder'?'▣':'▧'),title=el('input');title.value=n.name;title.className='nodeName';title.title='Edit display name · disk path stays stable';title.setAttribute('aria-label','Node name');
    title.readOnly=true;title.title='Drag header to move · double-click name to edit';
    title.onpointerdown=e=>{if(!title.readOnly)e.stopPropagation();else e.preventDefault();};
    title.ondblclick=e=>{e.stopPropagation();labelEdit(n);};
    title.onkeydown=e=>{if(e.key==='Enter')title.blur();if(e.key==='Escape'){title.value=n.name;title.blur();}};
    title.onblur=()=>{title.readOnly=true;if(title.value.trim()&&title.value.trim()!==n.name)run('label',{node_id:n.id,title:title.value.trim()});};
    head.append(icon,title);head.onpointerdown=e=>{if(e.button!==0||busy||!title.readOnly||e.target.closest('button'))return;e.stopPropagation();selected=n.id;if(typeof selectedConnection!=='undefined')selectedConnection=null;if(typeof selectedDataConnection!=='undefined')selectedDataConnection=null;if(typeof selection!=='undefined'&&!selection.has(n.id)){selection.clear();selection.add(n.id);}for(const c of document.querySelectorAll('.node')){c.classList.toggle('selected',c.dataset.id===n.id);if(typeof selection!=='undefined')c.classList.toggle('multiSelected',selection.has(c.dataset.id)&&selection.size>1);}inspect();if(typeof paintNavigator==='function')paintNavigator();move={type:'node',id:n.id,x:e.clientX,y:e.clientY,ox:n.x,oy:n.y};head.setPointerCapture(e.pointerId);};
    head.ondblclick=e=>{if(e.target.closest('button'))return;e.stopPropagation();move=null;labelEdit(n);};
    head.onpointermove=e=>drag(e);head.onpointerup=()=>{move=null;drawEdges();persist();};card.append(head);
    const body=el('div',undefined,'body');body.append(el('div',n.path,'path'));const row=el('div',undefined,'row');
    row.append(button(n.type==='folder'?'Open Folder':'Open',()=>run('launch',{node_id:n.id})));
    if(n.type==='blend')row.append(button('Snapshot',()=>run('snapshot',{node_id:n.id}),'Snapshot the last saved file'),button('↻',()=>{pick(n.id);run('refresh',{node_id:n.id});},'Refresh this node only'));
    body.append(row);
    if(n.type==='blend') {
      const inputRow=el('div','Link collection','row muted');const input=el('span',undefined,'port in');input.title='Drop a collection here';input.dataset.target=n.id;inputRow.append(input);body.append(inputRow);
      for(const instance of n.scan?.instances||[])body.append(el('div','↳ '+instance.collection,'incoming'));
      const rootCount=(n.scan?.root_objects||[]).reduce((sum,r)=>sum+r.objects.length,0);
      if(rootCount) {const warning=el('div',undefined,'rootWarning');warning.append(el('div',`${rootCount} objects in Scene Collection`),button('Collect root objects',()=>organize(n)));body.append(warning);}
      body.append(el('div','COLLECTIONS · SAVED FILE','caption'));
      const allDetails=n.scan?.collection_details||n.scan?.collections?.map(name=>({name,objects:null}))||[];
      const connected=new Set((state.project.nodes||[]).flatMap(t=>(t.scan?.instances||[]).filter(i=>normalize(i.source)===normalize(nodeFile(n))).map(i=>i.collection)));
      const favorites=new Set(n.pinned_collections||[]);
      const details=allDetails.filter(d=>connected.has(d.name)||favorites.has(d.name)).slice(0,6);
      for(const detail of details) {
        const c=el('div',undefined,'collection'+(detail.objects===0?' emptyCollection':''));
        c.append(el('span',detail.name),el('span',detail.objects===null?'?':String(detail.objects),'count'));
        c.title=detail.objects===0?'Empty collection. Link individual objects or organize them into this collection in Blender.':`${detail.objects} objects, including nested collections${detail.hidden?' · collection hidden':''}`;
        const socket=el('span',undefined,'port out'+(detail.objects===0?' disabled':''));socket.dataset.source=n.id;socket.dataset.collection=detail.name;
        socket.onpointerdown=e=>{e.stopPropagation();if(busy)return;if(detail.objects===0)return error('This collection is empty. Collect root objects or move objects into it in Blender, save, then refresh.');wire={source:n.id,collection:detail.name};status('Drop '+detail.name+' onto a destination node');};c.append(socket);body.append(c);
      }
      if(!details.length)body.append(el('div',allDetails.length?'Pin collections in the browser to show sockets here.':'No saved collections · save in Blender, then ↻','empty'));
      body.append(el('div',`History ${n.snapshots.length} · ${problem(n)}`,'muted nodeStatus'+(problem(n)!=='Ready'?' warning':'')));
    } else body.append(el('div','New files use this folder when selected','muted'));
    card.append(body);$('nodes').append(card);
  }
  transform();drawEdges();inspect();
}
function sourceSocket(id,collection) {return [...document.querySelectorAll('.out')].find(e=>e.dataset.source===id&&e.dataset.collection===collection);}
function point(element) {const r=element.getBoundingClientRect();return worldPoint(r.left+r.width/2,r.top+r.height/2);}
function normalize(p) {return p.replaceAll('\\','/').toLowerCase();}
function curve(path,a,b) {const bend=Math.max(65,Math.abs(b.x-a.x)*.45);path.setAttribute('d',`M ${a.x} ${a.y} C ${a.x+bend} ${a.y},${b.x-bend} ${b.y},${b.x} ${b.y}`);}
function drawEdges() {
  $('edges').replaceChildren();const nodes=state.project?.nodes||[];
  for(const target of nodes.filter(n=>n.type==='blend')) {
    const drawn=new Set();
    for(const instance of target.scan?.instances||[]) {
      const source=nodes.find(n=>n.type==='blend'&&normalize(state.root+'/'+n.path)===normalize(instance.source));if(!source)continue;
      const key=source.id+'|'+instance.collection;if(drawn.has(key))continue;drawn.add(key);
      const output=sourceSocket(source.id,instance.collection),input=document.querySelector(`[data-target="${target.id}"]`);if(!input)continue;
      const a=output?point(output):{x:source.x+238,y:source.y+90};const path=document.createElementNS('http://www.w3.org/2000/svg','path');curve(path,a,point(input));
      const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=instance.collection+' → '+target.name+' · Click to unlink';path.append(title);
      path.onclick=()=>modal('Unlink '+instance.collection,[closedField],v=>run('link',{source_id:source.id,target_id:target.id,collection:instance.collection,closed:v.closed,unlink:true}));$('edges').append(path);
    }
  }
}
function inspectBase() {
  const pane=$('inspector');pane.replaceChildren();const n=state.project?.nodes.find(n=>n.id===selected);pane.append(el('h3',n?n.name:'Project · V1.2'));
  if(state.desktop_warning)pane.append(el('p',state.desktop_warning,'warning'));
  if(!n) {
    pane.append(el('p','Double-click empty canvas to create a Blend File at that position. Right-click for node actions.'));
    if(state.root)pane.append(el('p',state.root));pane.append(button('Blender Settings',()=>modal('Blender executable',[{key:'blender',label:'Full executable path',value:state.blender,required:true}],v=>run('settings',v))));
    pane.append(el('p','Auto-refresh checks saved files every few seconds. Unsaved Blender edits are not accessible.'));return;
  }
  pane.append(el('p',state.root+'/'+n.path));pane.append(el('p','Header names are display labels. Disk paths stay stable.'));
  if(n.type==='folder'){pane.append(button('＋ Blend File here',()=>quickCreate()));return;}
  pane.append(el('p',problem(n)));pane.append(button('Open',()=>run('launch',{node_id:n.id})),button('↻ Refresh node',()=>run('refresh',{node_id:n.id})),button('Snapshot',()=>run('snapshot',{node_id:n.id})));
  if(n.scan?.scanned_at)pane.append(el('p','Scanned '+new Date(n.scan.scanned_at).toLocaleTimeString()));
  if(n.scan?.root_objects?.length) {
    const root=el('div',undefined,'section');root.append(el('h3','Objects outside linkable collections'));
    for(const r of n.scan.root_objects)root.append(el('p',r.scene+': '+r.objects.join(', ')));
    root.append(button('Collect root objects',()=>organize(n)));pane.append(root);
  }
  const refs=el('div',undefined,'section');refs.append(el('h3','References'));if(n.scan?.error)refs.append(el('p',n.scan.error,'warning'));
  for(const r of n.scan?.refs||[]) {const p=el('p',`${r.kind}: ${r.name||''}\n${r.raw}\n${!r.exists?'Missing · ':''}${r.pattern?'Pattern · ':''}${!r.relative?'Absolute · ':''}${!r.inside?'Outside project':''}`);p.style.whiteSpace='pre-wrap';p.title=r.path;refs.append(p);}pane.append(refs);
  const history=el('div',undefined,'section');history.append(el('h3','Saved states ('+n.snapshots.length+')'));
  for(const s of [...n.snapshots].reverse()) {const entry=el('div',undefined,'history');entry.append(el('div',`#${String(s.number).padStart(3,'0')} · ${new Date(s.created).toLocaleString()}`),el('div',s.note||'Saved state','muted'));const actions=el('div',undefined,'buttons');actions.append(button('Open copy',()=>run('inspect_snapshot',{node_id:n.id,snapshot_id:s.id})),button('Restore',()=>modal('Restore snapshot #'+s.number,[closedField],v=>run('restore',{node_id:n.id,snapshot_id:s.id,closed:v.closed}))));entry.append(actions);history.append(entry);}
  history.append(el('p','Snapshot captures the last saved file. Restore snapshots the current copy first. Linked dependencies are not frozen.'));pane.append(history);
}
function drag(e) {
  if(!move)return;
  if(move.type==='node'){const n=state.project.nodes.find(n=>n.id===move.id);n.x=move.ox+(e.clientX-move.x)/view.zoom;n.y=move.oy+(e.clientY-move.y)/view.zoom;const card=document.querySelector(`[data-id="${n.id}"]`);card.style.left=n.x+'px';card.style.top=n.y+'px';drawEdges();}
  else {view.x=move.ox+e.clientX-move.x;view.y=move.oy+e.clientY-move.y;transform();}
}
function emptyCanvas(e) {return !e.target.closest('.node')&&!e.target.closest('path')&&!e.target.closest('#welcome');}
$('workspace').onpointerdown=e=>{if(e.button===1){e.preventDefault();$('contextMenu').hidden=true;if(!state.project)return;move={type:'pan',x:e.clientX,y:e.clientY,ox:view.x,oy:view.y};$('workspace').setPointerCapture(e.pointerId);}};
$('workspace').onpointermove=e=>{
  lastPoint=worldPoint(e.clientX,e.clientY);drag(e);
  if(wire){let preview=$('wirePreview');if(!preview){preview=document.createElementNS('http://www.w3.org/2000/svg','path');preview.id='wirePreview';preview.style.pointerEvents='none';preview.style.stroke='#fff';$('edges').append(preview);}curve(preview,point(sourceSocket(wire.source,wire.collection)),lastPoint);}
};
$('workspace').onpointerup=()=>{if(move?.type==='pan'){move=null;persist();}};
document.addEventListener('pointerup',e=>{
  if(!wire)return;const element=document.elementFromPoint(e.clientX,e.clientY),target=element?.closest('[data-target]')?.dataset.target||element?.closest('.node.blend')?.dataset.id;
  const current=wire;wire=null;$('wirePreview')?.remove();
  if(target){if(window.pipelineLinkDialog)window.pipelineLinkDialog(current.source,target,current.collection);else modal('Link '+current.collection,[closedField],v=>run('link',{source_id:current.source,target_id:target,collection:current.collection,closed:v.closed}));}else status('Link cancelled');
});
$('workspace').ondblclick=e=>{if(emptyCanvas(e)&&state.project)quickCreate(worldPoint(e.clientX,e.clientY));};
$('workspace').oncontextmenu=e=>{
  e.preventDefault();if(!state.project||busy)return;const menu=$('contextMenu');menu.replaceChildren();const card=e.target.closest('.node');
  if(card){const n=state.project.nodes.find(n=>n.id===card.dataset.id);pick(n.id);if(n.type==='blend')menu.append(button('Refresh this node',()=>run('refresh',{node_id:n.id})),button('Snapshot saved file',()=>run('snapshot',{node_id:n.id})));menu.append(button('Edit name',()=>labelEdit(n)));}
  else {const p=worldPoint(e.clientX,e.clientY);menu.append(button('Add Blend File here',()=>quickCreate(p)));}
  menu.style.left=Math.min(e.clientX,innerWidth-200)+'px';menu.style.top=Math.min(e.clientY,innerHeight-160)+'px';menu.hidden=false;
};
document.addEventListener('click',e=>{if(!e.target.closest('#contextMenu')||e.target.closest('#contextMenu button'))$('contextMenu').hidden=true;},true);
$('workspace').addEventListener('wheel',e=>{e.preventDefault();const bounds=$('workspace').getBoundingClientRect(),x=e.clientX-bounds.left,y=e.clientY-bounds.top,old=view.zoom;view.zoom=Math.max(.3,Math.min(2,old*Math.exp(-e.deltaY*.001)));view.x=x-(x-view.x)*view.zoom/old;view.y=y-(y-view.y)*view.zoom/old;transform();persist();},{passive:false});
function reveal(n) {const x=n.x*view.zoom+view.x,y=n.y*view.zoom+view.y;if(x<0||y<0||x+238*view.zoom>$('workspace').clientWidth||y+200*view.zoom>$('workspace').clientHeight){view.x=$('workspace').clientWidth/2-(n.x+119)*view.zoom;view.y=$('workspace').clientHeight/2-(n.y+100)*view.zoom;transform();persist();}}
$('frame').onclick=()=>{const nodes=state.project?.nodes;if(!nodes?.length)return;const minX=Math.min(...nodes.map(n=>n.x)),minY=Math.min(...nodes.map(n=>n.y)),maxX=Math.max(...nodes.map(n=>n.x+250)),maxY=Math.max(...nodes.map(n=>n.y+document.querySelector(`[data-id="${n.id}"]`).offsetHeight));view.zoom=Math.min(1,($('workspace').clientWidth-80)/(maxX-minX),($('workspace').clientHeight-80)/(maxY-minY));view.x=40-minX*view.zoom;view.y=40-minY*view.zoom;transform();persist();};
$('search').oninput=e=>{const value=e.target.value.toLowerCase(),n=state.project?.nodes.find(n=>value&&n.name.toLowerCase().includes(value));if(n){pick(n.id);reveal(n);}};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('contextMenu').hidden=true;wire=null;$('wirePreview')?.remove();}if(e.key==='F5'&&!document.activeElement?.matches('input,textarea,select,[contenteditable=true]')&&!$('commandPalette')?.open&&state.project?.nodes.find(n=>n.id===selected)?.type==='blend'&&!$('dialog').open){e.preventDefault();run('refresh',{node_id:selected});}});
PipelineUI.background('saved-file-refresh',3000,async()=>{
  const active=document.activeElement;
  if((window.pipelineBusy&&window.pipelineBusy())||busy||move||wire||!state.project||$('dialog').open||(active?.tagName==='INPUT'&&active.type!=='checkbox'&&!active.readOnly))return;
  try {
    const latest=await api('state');if(latest.project?.id!==state.project.id)return;
    state.files=latest.files;state.open=latest.open;
    for(const n of state.project.nodes.filter(n=>n.type==='blend')){const label=document.querySelector(`[data-id="${n.id}"] .nodeStatus`);if(label)label.textContent=problem(n);}
    if($('autoRefresh').checked){for(const [id,file] of Object.entries(latest.files||{})){const signature=JSON.stringify([file.mtime,file.size]);const before=observed.get(id);observed.set(id,signature);if(file.changed&&!file.missing&&before===signature){await run('refresh',{node_id:id});break;}}}
  }catch(e){status('Local server unavailable. Restart Launch.cmd if needed.');}
});

