PipelineUI.define('paintTasks',paintTasksBase);
function paintTasks(...args){return PipelineUI.call('paintTasks',...args);}
/* Native-looking graph interactions layered onto the local file interface. */
const selection=new Set(), pendingJobs=new Map();
let selectedConnection=null, adding=false, placingFolder=null, box=null;
window.pipelineBusy=()=>pendingJobs.size>0;
const baseDrag=drag;
const baseProblem=problem;
problem=function(n){if(n.last_error)return 'Operation failed';if(state.updates?.[n.id]?.length)return 'Linked asset changed';return baseProblem(n);};
function visibleNodes(){return (state.project?.nodes||[]).filter(n=>!n.hidden&&!state.project.nodes.some(f=>f.id===n.group&&f.collapsed&&!f.hidden));}
function keepLocalLayout(next){
  if(next.project?.id===state.project?.id){next.project.view={...view};}
  return next;
}
PipelineUI.use('run','queued-operations',100,async function(next, action,args={}){
  if(action==='state'){state=await api('state');if(state.project){view=state.project.view;selected=state.view_state?.selected||null;if(typeof inspectorTab!=='undefined')inspectorTab=state.view_state?.tab||'overview';}render();return state;}
  if(action==='render_cancel'||action==='cancel_queue'){try{state=keepLocalLayout(await api(action,args));render();}catch(e){error(e);}return;}
  const before=new Set((state.project?.nodes||[]).map(n=>n.id));
  try{
    if(!pendingJobs.size&&state.project&&!['load','create'].includes(action))await flushLayout();
    if(action==='layout'||action==='settings'){state=keepLocalLayout(await api(action,args));render();return state;}
    const response=await api('async',{action,...args});
    pendingJobs.set(response.job,{action,args,before,created:new Date().toISOString()});status('Queued · '+action);paintTasks();
    return await new Promise(resolve=>pendingJobs.get(response.job).resolve=resolve);
  }catch(e){error(e);$('ghost')?.remove();}
});
async function pollJobs(){
  if(move||box)return;
  if(document.activeElement?.matches('textarea,input:not([type=checkbox]):not([readonly]),select')||$('commandPalette')?.open)return;
  if(document.activeElement?.classList.contains('nodeName')&&!document.activeElement.readOnly)return;
  try{
    const next=await api('state');let changed=false;
    if(!pendingJobs.size&&!wire&&!adding&&!$('dialog').open){
      const signature=p=>JSON.stringify(p?Object.fromEntries(Object.entries(p).filter(([k])=>!['revision','renders','render_queue','view'].includes(k))):null);
      if(next.project?.id!==state.project?.id||!layoutDirty&&(signature(next.project)!==signature(state.project))){
        const switched=next.project?.id!==state.project?.id;state=switched?next:keepLocalLayout(next);if(switched){selected=null;selection.clear();view=state.project?.view||{x:0,y:0,zoom:1};}render();
      }
    }
    for(const [id,local] of [...pendingJobs]){
      const job=next.jobs?.find(j=>j.id===id);if(!job)continue;
      if(['Complete','Failed','Interrupted'].includes(job.status)){
        pendingJobs.delete(id);changed=true;
        if(job.status!=='Complete'){if(job.error_code==='render_image_warnings')status('Review image warnings before rendering');else error(job.error);}else status(next.notice||'Ready · '+local.action+' completed');
        if(['blend','duplicate','import','folder','frame','export_node','render_node','restore_graph_node','restore_archived','restore_folder'].includes(local.action)&&job.status==='Complete'){
          const added=next.project.nodes.find(n=>!local.before.has(n.id));if(added){selected=added.id;selection.clear();selection.add(added.id);}
        }
        local.resolve?.(next);
      }
    }
    if(changed){state=keepLocalLayout(next);if(state.project)view=state.project.view;render();$('ghost')?.remove();if(!pendingJobs.size&&layoutDirty)persist();}
    else if(!pendingJobs.size&&!move&&!wire&&!adding&&!$('dialog').open){
      const liveChanged=JSON.stringify((state.live||[]).map(s=>[s.id,s.file,s.dirty,s.overrides]))!==JSON.stringify((next.live||[]).map(s=>[s.id,s.file,s.dirty,s.overrides]));
      const folderChanged=JSON.stringify(state.folder_info)!==JSON.stringify(next.folder_info);state.folder_info=next.folder_info;if(folderChanged&&state.project?.nodes.find(n=>n.id===selected)?.type==='folder')inspect();
      const healthChanged=JSON.stringify(state.health)!==JSON.stringify(next.health);
      state.files=next.files;state.open=next.open;state.updates=next.updates;state.live=next.live;state.health=next.health;state.render_targets=next.render_targets;
      const previous=JSON.stringify([state.project?.renders||[],state.project?.render_queue||[]]);if(state.project){state.project.renders=next.project.renders||[];state.project.render_queue=next.project.render_queue||[];state.project.revision=next.project.revision;}
      if(healthChanged||liveChanged)inspect();if(healthChanged||liveChanged||previous!==JSON.stringify([state.project?.renders||[],state.project?.render_queue||[]]))paintTasks();
    }
    state.jobs=next.jobs;paintTasks();
  }catch(e){status('Local server unavailable. Restart Launch.cmd.');}
}
PipelineUI.background('operation-status',700,pollJobs);
function paintTasksBase(){
  const jobs=state.jobs||[];const running=jobs.filter(j=>['Queued','Running'].includes(j.status));
  if(!$('taskMessage').dataset.activityOwner){$('taskMessage').hidden=!running.length;if(running.length)$('taskMessage').textContent=running.map(j=>j.action+' · '+j.status).join(' | ');}
  for(const n of state.project?.nodes||[]){const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;const active=running.find(j=>j.node_id===n.id),renderRun=state.project.renders?.find(r=>r.node_id===n.id&&r.status==='Rendering');let indicator=card.querySelector('.nodeProgress');if((active||renderRun)&&!indicator){indicator=el('div',undefined,'nodeProgress');card.append(indicator);}if(!active&&!renderRun&&indicator)indicator.remove();const label=card.querySelector('.nodeStatus');if(label)label.textContent=active?active.action+' · '+active.status:renderRun?'Rendering · '+renderRun.progress+'%':`History ${n.snapshots?.length||0} · ${problem(n)}`;}
}
PipelineUI.use('pick','graph-selection',101,function(next, id,additive=false){
  selectedConnection=null;selected=id;
  if(additive){if(selection.has(id))selection.delete(id);else selection.add(id);}else if(!selection.has(id)){selection.clear();selection.add(id);}
  for(const card of $('nodes').children){card.classList.toggle('selected',card.dataset.id===id);card.classList.toggle('multiSelected',selection.has(card.dataset.id)&&selection.size>1);}inspect();
});
function editGraph(n,changes){Object.assign(n,changes);if(changes.hidden&&selected===n.id){selected=null;selection.delete(n.id);}render();run('graph_edit',{node_id:n.id,group:n.group||null,...changes});}
function showNote(n,s){modal('Snapshot note',[{key:'note',label:'Note',value:s.note||''},{key:'checkpoint',label:'Mark as checkpoint',type:'checkbox',value:!!s.checkpoint}],v=>run('snapshot_note',{node_id:n.id,snapshot_id:s.id,...v}));}
function inlineHistory(n,container,limit=3){
  for(const s of [...n.snapshots].reverse().slice(0,limit)){const entry=el('div',undefined,'history');entry.append(el('div',`${s.checkpoint?'★ ':''}#${String(s.number).padStart(3,'0')} · ${s.note||new Date(s.created).toLocaleTimeString()}`));const buttons=el('div',undefined,'buttons');buttons.append(button('Note',()=>showNote(n,s)),button('Open copy',()=>run('inspect_snapshot',{node_id:n.id,snapshot_id:s.id})),button('Restore',()=>modal('Restore snapshot #'+s.number,[closedField],v=>run('restore',{node_id:n.id,snapshot_id:s.id,closed:v.closed}))));entry.append(buttons);container.append(entry);}
}
function startPlacement(folder=null){if(!state.project)return error('Create a project first.');adding=true;placingFolder=folder;wire=null;$('ghost')?.remove();const ghost=el('div','Blend File · click to place','node placementGhost');ghost.id='ghost';const p=lastPoint||placement();ghost.style.left=p.x+'px';ghost.style.top=p.y+'px';$('nodes').append(ghost);status('Place Blend File · click canvas · Escape cancels');}
async function placeAt(p){adding=false;const folder=placingFolder;placingFolder=null;await run('blend',{folder_id:folder||null,x:p.x,y:p.y});}
$('addBlend').onclick=e=>{if(e.shiftKey){const p=placement();modal('Create from template',[{key:'title',label:'File name (optional)'},folderField(),{key:'template',label:'Template .blend path (optional)'}],v=>run('blend',{...v,title:v.title||null,folder_id:v.folder_id||null,template:v.template||null,...p}));}else{const n=state.project?.nodes.find(n=>n.id===selected);startPlacement(['folder','frame'].includes(n?.type)?n.id:n?.group||null);}};
quickCreate=async function(p){if(!state.project)return error('Create a project first.');const n=state.project.nodes.find(n=>n.id===selected);placingFolder=['folder','frame'].includes(n?.type)?n.id:n?.group||null;await placeAt(placement(p));};
PipelineUI.use('render','graph-cards',102,function(next){
  next();
  const nodes=state.project?.nodes||[];
  for(const n of nodes){
    const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;
    if(n.hidden||nodes.some(f=>f.id===n.group&&f.collapsed&&!f.hidden)){card.remove();continue;}
    card.onclick=e=>pick(n.id,e.shiftKey);card.classList.toggle('multiSelected',selection.has(n.id)&&selection.size>1);
    const head=card.querySelector('header'),down=head.onpointerdown;head.onpointerdown=e=>{if(e.shiftKey){e.stopPropagation();return;}down(e);};
    if(n.type==='folder'){
      card.style.width=(n.width||650)+'px';card.style.height=(n.collapsed?112:n.height||420)+'px';card.style.zIndex='0';card.querySelector('.body').remove();
      const toggle=button(n.collapsed?'▸':'▾',()=>editGraph(n,{collapsed:!n.collapsed}),'Collapse folder frame');card.querySelector('header').prepend(toggle);toggle.onpointerdown=e=>e.stopPropagation();
      const tools=el('div',undefined,'folderTools');tools.append(button('Open Folder',()=>run('launch',{node_id:n.id})),button('＋ File',()=>startPlacement(n.id)));
      const input=el('span',undefined,'port folderIn');input.dataset.folder=n.id;input.style.left='-6px';input.style.top='42px';input.title='Drop a blue render output here';card.append(input,tools,el('div',`${nodes.filter(child=>child.group===n.id&&!child.hidden).length} files · visual grouping; disk moves are explicit`,'folderLabel'));
      if(!n.collapsed){const resize=el('div','◢','frameResize');resize.onpointerdown=e=>{e.stopPropagation();move={type:'resize',id:n.id,x:e.clientX,y:e.clientY,width:n.width||650,height:n.height||420};resize.setPointerCapture(e.pointerId);};resize.onpointermove=e=>drag(e);resize.onpointerup=()=>{move=null;run('graph_edit',{node_id:n.id,group:null,width:n.width,height:n.height});};card.append(resize);}
    }else if(n.type==='blend'){
      card.style.zIndex='2';const body=card.querySelector('.body');
      const actions=el('div',undefined,'row');actions.append(button('Duplicate',()=>run('duplicate',{node_id:n.id,...placement()})),button('Render',()=>n.render_config?run('render_start',{node_id:n.id}):configureRender(n)));body.append(actions);
      const output=el('div','Output'+(n.render_config?' → '+(nodes.find(f=>f.id===n.render_config.folder_id)?.name||'?'):''),'renderOutput');const port=el('span',undefined,'port renderOut');port.dataset.render=n.id;port.onpointerdown=e=>{e.stopPropagation();wire={render:n.id};status('Drop onto a Render node, Folder, or empty canvas');};output.append(port);body.append(output);
      const history=el('div',undefined,'nodeHistory');history.append(button((n.history_open?'▾':'▸')+' History · '+n.snapshots.length,()=>editGraph(n,{history_open:!n.history_open})));if(n.history_open)inlineHistory(n,history);body.append(history);
      const caption=body.querySelector('.caption');if(caption){caption.textContent=(n.collections_closed?'▸':'▾')+' COLLECTIONS · SAVED FILE';caption.style.cursor='pointer';caption.onclick=e=>{e.stopPropagation();editGraph(n,{collections_closed:!n.collections_closed});};}
      const details=n.scan?.collection_details||[];
      for(const row of body.querySelectorAll('.collection')){const collection=row.querySelector('.out').dataset.collection,detail=details.find(c=>c.name===collection);if($('hideEmpty').checked&&detail?.objects===0){row.hidden=true;continue;}const depth=detail?.parents?.length||0;row.style.paddingLeft=(depth*12)+'px';const marker=el('span',detail?.children?.length?'▸':'·');marker.title=detail?.hidden?'Hidden in viewport or render':'Collection';row.prepend(marker);if(detail?.hidden)row.style.opacity='.65';}
      if(n.last_error){const warning=el('div',undefined,'nodeError');warning.append(el('div',n.last_error.action+' failed'),button('Details',()=>{pick(n.id);}),button('Retry',()=>run(n.last_error.action,n.last_error.args)),button('Dismiss',()=>run('dismiss_error',{node_id:n.id})));body.append(warning);}
      if(state.updates?.[n.id]?.length)body.append(button('↻ Linked asset changed',()=>refreshAssets(n)));
    }
  }
  drawEdges();paintTasks();inspect();
});
function nodeAnchor(n,side){const frame=state.project.nodes.find(f=>f.id===n.group&&f.collapsed);const visible=frame||n;const card=document.querySelector(`[data-id="${visible.id}"]`);if(!card)return null;return {x:visible.x+(side==='out'?card.offsetWidth:0),y:visible.y+(frame?20:90)};}
drawEdges=function(){
  $('edges').replaceChildren();const nodes=state.project?.nodes||[];
  for(const target of nodes.filter(n=>n.type==='blend'&&!n.hidden)){
    const done=new Set();for(const instance of target.scan?.instances||[]){
      const source=nodes.find(n=>n.type==='blend'&&!n.hidden&&normalize(nodeFile(n))===normalize(instance.source));if(!source)continue;
      const key=source.id+'|'+instance.collection;if(done.has(key))continue;done.add(key);
      const socket=sourceSocket(source.id,instance.collection),input=document.querySelector(`[data-target="${target.id}"]`);
      const a=socket&&socket.getBoundingClientRect().width?point(socket):nodeAnchor(source,'out'),b=input?point(input):nodeAnchor(target,'in');if(!a||!b)continue;
      const connection={source:source.id,target:target.id,collection:instance.collection,key};const path=document.createElementNS('http://www.w3.org/2000/svg','path');if(source.external)path.style.strokeDasharray='6 4';curve(path,a,b);
      const detail=source.scan?.collection_details?.find(c=>c.name===instance.collection);const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=`${source.path} · ${instance.collection} (${detail?.objects??'?'} objects) → ${target.path}`;path.append(title);
      if(selectedConnection?.key===key)path.classList.add('connectionSelected');path.onclick=e=>{e.stopPropagation();selectedConnection=connection;drawEdges();inspect();};$('edges').append(path);
    }
    if(target.render_config){const folder=nodes.find(n=>n.id===target.render_config.folder_id&&!n.hidden);if(folder){const port=document.querySelector(`[data-render="${target.id}"]`),input=document.querySelector(`[data-folder="${folder.id}"]`);const a=port?point(port):nodeAnchor(target,'out'),b=input?point(input):nodeAnchor(folder,'in');if(a&&b){const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.style.stroke='#73aaca';curve(path,a,b);const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=target.name+' renders → '+folder.path;path.append(title);path.onclick=()=>configureRender(target,folder.id);$('edges').append(path);}}}
  }
};
function refreshAssets(n){modal('Refresh linked assets',[closedField],v=>run('refresh_dependencies',{node_id:n.id,closed:v.closed}));}
function configureRender(n,folderId){
  const scenes=(n.scan?.scenes||[]).filter(s=>!s.linked);if(!scenes.length)return error('Refresh this file before configuring renders.');const config=n.render_config||{},scene=scenes.find(s=>s.name===config.scene)||scenes[0];
  const outputFolders=folders().filter(f=>f.value);if(!outputFolders.length)return error('Create a Folder node for render outputs first.');
  modal('Render settings',[
    {key:'folder_id',label:'Output folder',type:'select',options:outputFolders},
    {key:'scene',label:'Scene',type:'select',options:scenes.map(s=>({label:s.name,value:s.name}))},
    {key:'camera',label:'Camera',type:'select',options:scene.cameras.map(c=>({label:c,value:c}))},
    {key:'start',label:'Start frame',type:'number',value:config.start??scene.start,required:true},
    {key:'end',label:'End frame',type:'number',value:config.end??scene.start,required:true},
    {key:'percentage',label:'Resolution percentage',type:'number',value:config.percentage||100,required:true},
    {key:'prefix',label:'Output filename prefix',value:config.prefix||'render',required:true,help:'PNG frames use a new numbered output directory. Source and supported relative dependencies are frozen for this run; no thumbnails.'}
  ],v=>run('render_config',{node_id:n.id,...v}));
  $('field-folder_id').value=folderId||config.folder_id||outputFolders[0].value;$('field-scene').value=scene.name;$('field-camera').value=config.camera||scene.camera||scene.cameras[0]||'';
  $('field-scene').onchange=()=>{const s=scenes.find(s=>s.name===$('field-scene').value);$('field-camera').replaceChildren();for(const c of s.cameras){const o=el('option',c);o.value=c;$('field-camera').append(o);}};
}
function relocateFile(n){modal('Move / rename file on disk',[folderField(),{key:'title',label:'New filename',value:n.path.split('/').pop(),required:true},{...closedField,label:'This file and ALL registered dependent files are saved and closed',help:'Snapshots are made before the move. Registered library paths are repaired. Unregistered files outside this graph cannot be repaired.'}],v=>run('relocate',{node_id:n.id,...v,folder_id:v.folder_id||null}));}
function locateFile(n){modal('Locate / adopt saved file',[{key:'source',label:'Full path to saved .blend file',required:true,help:'The selected file is copied back to this node’s managed path. Existing working contents are snapshotted first; incoming links keep their stable path.'},closedField],v=>run('adopt',{node_id:n.id,...v}));}
PipelineUI.use('inspect','graph-inspector',103,function(next){
  if(selectedConnection){const pane=$('inspector'),c=selectedConnection,source=state.project.nodes.find(n=>n.id===c.source),target=state.project.nodes.find(n=>n.id===c.target);pane.replaceChildren(el('h3','Collection connection'),el('p',source.path+' → '+target.path),el('p',c.collection));pane.append(button('Select source',()=>pick(source.id)),button('Select destination',()=>pick(target.id)),button('Unlink instance',()=>modal('Unlink '+c.collection,[closedField],v=>run('link',{source_id:c.source,target_id:c.target,collection:c.collection,closed:v.closed,unlink:true}))));return;}
  next();const pane=$('inspector'),n=state.project?.nodes.find(n=>n.id===selected);
  for(const section of pane.querySelectorAll('.section'))if(section.querySelector('h3')?.textContent.startsWith('Saved states'))section.remove();
  if(!n){pane.append(el('p','Place nodes before file creation. Shift-drag empty canvas to box-select; Shift-click adds to selection. Move folder frames to move their grouped nodes.'));
    for(const job of state.jobs?.filter(j=>j.status==='Failed'&&!j.node_id)||[]){pane.append(el('p',job.action+': '+job.error,'warning'),button('Retry '+job.action,()=>run(job.action,job.args)));}
    const hidden=state.project?.nodes.filter(n=>n.hidden)||[];if(hidden.length){pane.append(el('h3','Hidden files'));for(const item of hidden)pane.append(button('Show '+item.name,()=>editGraph(item,{hidden:false})));}return;}
  pane.append(el('div',undefined,'section'),button('Remove from graph',()=>editGraph(n,{hidden:true}),'File stays on disk; restore from the project inspector'));
  if(selection.size>1){pane.append(el('p',selection.size+' nodes selected'),button('Align left',()=>alignSelection('left')),button('Align top',()=>alignSelection('top')),button('Distribute horizontally',()=>alignSelection('distribute')));}
  if(n.type==='folder'){
    for(const b of pane.querySelectorAll('button'))if(b.textContent==='＋ Blend File here')b.onclick=()=>startPlacement(n.id);
    const children=state.project.nodes.filter(child=>child.group===n.id&&!child.hidden);pane.append(button(n.collapsed?'Expand frame':'Collapse frame',()=>editGraph(n,{collapsed:!n.collapsed})),el('p',children.length+' grouped files. Grouping is visual; Move / rename is a separate disk operation.'));return;
  }
  if(n.type!=='blend')return;
  const section=el('div',undefined,'section');section.append(el('h3','File actions'),button('Duplicate working copy',()=>run('duplicate',{node_id:n.id,...placement()})),button('Locate / adopt file',()=>locateFile(n)),button('Move / rename on disk',()=>relocateFile(n)),button('Refresh linked assets',()=>refreshAssets(n)));
  const groups=el('select');const none=el('option','No folder frame');none.value='';groups.append(none);for(const f of state.project.nodes.filter(f=>f.type==='folder'&&!f.hidden)){const o=el('option',f.name);o.value=f.id;groups.append(o);}groups.value=n.group||'';groups.onchange=()=>editGraph(n,{group:groups.value||null});section.append(el('label','Visual folder frame'),groups);pane.append(section);
  if(n.last_error){const failure=el('div',undefined,'section');failure.append(el('h3','Operation failed'),el('p',n.last_error.message,'warning'),button('Retry',()=>run(n.last_error.action,n.last_error.args)),button('Dismiss',()=>run('dismiss_error',{node_id:n.id})));pane.append(failure);}
  const notes=el('div',undefined,'section');notes.append(el('h3','Checkpoint notes'));inlineHistory(n,notes,n.snapshots.length);pane.append(notes);
  const renders=el('div',undefined,'section');renders.append(el('h3','Render runs'),button('Settings',()=>configureRender(n)),button('Render saved file',()=>n.render_config?run('render_start',{node_id:n.id}):configureRender(n)));
  for(const r of [...(state.project.renders||[])].reverse().filter(r=>r.node_id===n.id)){
    const entry=el('div',undefined,'renderRun');entry.append(el('div',`r${String(r.number).padStart(3,'0')} · ${r.status}`),el('p',r.output));const progress=el('progress');progress.max=100;progress.value=r.progress||0;entry.append(progress);
    if(r.status==='Rendering')entry.append(button('Cancel',()=>run('render_cancel',{run_id:r.id})));entry.append(button('Open output folder',()=>run('render_open',{run_id:r.id})));
    if(r.error)entry.append(el('p',r.error,'warning'));if(r.detail){const detail=el('details');detail.append(el('summary','Progress details'),el('pre',r.detail));entry.append(detail);}renders.append(entry);
  }pane.append(renders);
});
drag=function(e){
  if(!move)return;
  if(move.type==='resize'){const n=state.project.nodes.find(n=>n.id===move.id);n.width=Math.max(300,move.width+(e.clientX-move.x)/view.zoom);n.height=Math.max(150,move.height+(e.clientY-move.y)/view.zoom);const card=document.querySelector(`[data-id="${n.id}"]`);card.style.width=n.width+'px';card.style.height=n.height+'px';drawEdges();return;}
  if(move.type==='node'){
    if(!move.positions){const ids=new Set(selection);ids.add(move.id);for(const f of state.project.nodes.filter(n=>['folder','frame'].includes(n.type)&&ids.has(n.id)))for(const child of state.project.nodes.filter(n=>n.group===f.id||(typeof inFrame==='function'&&inFrame(n,f.id))))ids.add(child.id);move.positions=state.project.nodes.filter(n=>ids.has(n.id)).map(n=>({id:n.id,x:n.x,y:n.y}));}
    const dx=(e.clientX-move.x)/view.zoom,dy=(e.clientY-move.y)/view.zoom;
    for(const p of move.positions){const n=state.project.nodes.find(n=>n.id===p.id);n.x=p.x+dx;n.y=p.y+dy;const card=document.querySelector(`[data-id="${n.id}"]`);if(card){card.style.left=n.x+'px';card.style.top=n.y+'px';}}drawEdges();return;
  }baseDrag(e);
};
const previousDown=$('workspace').onpointerdown,previousMove=$('workspace').onpointermove,previousUp=$('workspace').onpointerup;
$('workspace').onpointerdown=e=>{
  if(adding&&e.button===0){e.preventDefault();e.stopPropagation();placeAt(worldPoint(e.clientX,e.clientY));return;}
  if(e.button===0&&emptyCanvas(e)){e.preventDefault();box={x:e.clientX,y:e.clientY,additive:e.shiftKey||e.ctrlKey};const rectangle=el('div',undefined,'selectionBox');rectangle.id='selectionBox';$('workspace').append(rectangle);$('workspace').setPointerCapture(e.pointerId);return;}
  previousDown(e);
};
$('workspace').onpointermove=e=>{
  lastPoint=worldPoint(e.clientX,e.clientY);
  if(adding){const ghost=$('ghost');if(ghost){ghost.style.left=lastPoint.x+'px';ghost.style.top=lastPoint.y+'px';}return;}
  if(box){const bounds=$('workspace').getBoundingClientRect(),r=$('selectionBox');r.style.left=Math.min(box.x,e.clientX)-bounds.left+'px';r.style.top=Math.min(box.y,e.clientY)-bounds.top+'px';r.style.width=Math.abs(e.clientX-box.x)+'px';r.style.height=Math.abs(e.clientY-box.y)+'px';box.end={x:e.clientX,y:e.clientY};return;}
  if(wire?.render){let preview=$('wirePreview');if(!preview){preview=document.createElementNS('http://www.w3.org/2000/svg','path');preview.id='wirePreview';preview.style.stroke='#73aaca';preview.style.pointerEvents='none';$('edges').append(preview);}curve(preview,point(document.querySelector(`[data-render="${wire.render}"]`)),lastPoint);return;}
  previousMove(e);
};
$('workspace').onpointerup=e=>{
  if(box){const a=worldPoint(Math.min(box.x,box.end?.x||box.x),Math.min(box.y,box.end?.y||box.y)),b=worldPoint(Math.max(box.x,box.end?.x||box.x),Math.max(box.y,box.end?.y||box.y));if(!box.additive)selection.clear();for(const n of visibleNodes()){const card=document.querySelector(`[data-id="${n.id}"]`);if(card&&(['folder','frame'].includes(n.type)?(n.x>=a.x&&n.y>=a.y&&n.x+card.offsetWidth<=b.x&&n.y+card.offsetHeight<=b.y):(n.x<b.x&&n.x+card.offsetWidth>a.x&&n.y<b.y&&n.y+card.offsetHeight>a.y)))selection.add(n.id);}box=null;$('selectionBox').remove();selected=[...selection][0]||null;render();return;}
  previousUp(e);
};
// Handle output-folder wires before the collection-wire listener registered by the base UI.
document.addEventListener('pointerup',e=>{
  if(!wire?.render)return;e.stopImmediatePropagation();const n=state.project.nodes.find(n=>n.id===wire.render),hit=document.elementFromPoint(e.clientX,e.clientY),target=hit?.closest('.node.folder');wire=null;$('wirePreview')?.remove();if(window.pipelineExportDrop?.(n.id,hit))return;if(target)configureRender(n,target.dataset.id);else if(window.pipelineOfferOutputNodes&&$('workspace').contains(hit)&&emptyCanvas({target:hit}))window.pipelineOfferOutputNodes(n,worldPoint(e.clientX,e.clientY),e);else status('Output connection cancelled');
},true);
document.addEventListener('pointerup',e=>{
  if(move?.type!=='node')return;
  if(window.pipelineGroupDrop){window.pipelineGroupDrop(e);return;}
  const moved=state.project.nodes.find(n=>n.id===move.id);if(moved.type==='folder')return;
  for(const id of selection){const n=state.project.nodes.find(n=>n.id===id);if(!n||n.type!=='blend')continue;
    const frame=state.project.nodes.filter(f=>f.type==='folder'&&!f.hidden&&!f.collapsed&&n.x+119>f.x&&n.x+119<f.x+(f.width||650)&&n.y+15>f.y+28&&n.y+15<f.y+(f.height||420)).at(-1);
    const group=frame?.id||null;if(group!==n.group){n.group=group;run('graph_edit',{node_id:n.id,group});}
  }
},true);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(adding)status('Placement cancelled');adding=false;placingFolder=null;$('ghost')?.remove();}});
function alignSelection(mode){const nodes=state.project.nodes.filter(n=>selection.has(n.id)&&n.type==='blend');if(nodes.length<2)return error('Select at least two file nodes.');if(mode==='left'){const x=Math.min(...nodes.map(n=>n.x));for(const n of nodes)n.x=x;}else if(mode==='top'){const y=Math.min(...nodes.map(n=>n.y));for(const n of nodes)n.y=y;}else{nodes.sort((a,b)=>a.x-b.x);const start=nodes[0].x,step=Math.max(280,(nodes.at(-1).x-start)/(nodes.length-1));nodes.forEach((n,i)=>n.x=start+i*step);}render();persist();}
$('alignNodes').onclick=()=>modal('Align selected files',[{key:'mode',label:'Alignment',type:'select',options:[{label:'Align left',value:'left'},{label:'Align top',value:'top'},{label:'Distribute horizontally',value:'distribute'}]}],v=>alignSelection(v.mode));
$('frameSelection').onclick=()=>{const nodes=visibleNodes().filter(n=>selection.has(n.id));if(!nodes.length)return error('Select nodes first.');const minX=Math.min(...nodes.map(n=>n.x)),minY=Math.min(...nodes.map(n=>n.y)),maxX=Math.max(...nodes.map(n=>n.x+document.querySelector(`[data-id="${n.id}"]`).offsetWidth)),maxY=Math.max(...nodes.map(n=>n.y+document.querySelector(`[data-id="${n.id}"]`).offsetHeight));view.zoom=Math.min(1.4,($('workspace').clientWidth-80)/(maxX-minX),($('workspace').clientHeight-80)/(maxY-minY));view.x=40-minX*view.zoom;view.y=40-minY*view.zoom;transform();persist();};
$('frame').onclick=()=>{const saved=[...selection];selection.clear();visibleNodes().forEach(n=>selection.add(n.id));$('frameSelection').onclick();selection.clear();saved.forEach(id=>selection.add(id));render();};
$('hideEmpty').onchange=()=>render();
$('backupProject').onclick=()=>{if(!state.project)return error('Open a project first.');modal('Project backup',[{key:'destination',label:'New ZIP path',value:state.root+'-backup.zip',required:true},{key:'include_renders',label:'Include render output files',type:'checkbox',value:true},{key:'allow_incomplete',label:'Allow incomplete archive with dependency warnings',type:'checkbox',value:false,help:'Default preflight blocks missing or unsupported dependencies. Graph metadata, history and ordinary project files are included.'}],v=>run('backup',v));};
if(state.project)render();
