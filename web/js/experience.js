PipelineUI.define('paintNavigator',paintNavigatorBase);
function paintNavigator(...args){return PipelineUI.call('paintNavigator',...args);}
/* Compact workspace, progressive disclosure and keyboard navigation. */
const uxDrag=drag;
let inspectorTab='overview',navigatorOpen=false,inspectorOpen=true,layoutUndo=[],layoutRedo=[],undoProject=null;
let blankPress=null;
const actionNames={blend:'Creating file',folder:'Creating folder',refresh:'Reading saved file',snapshot:'Saving snapshot',duplicate:'Duplicating file',link:'Updating collection link',relocate:'Moving file',backup:'Backing up project',render_start:'Preparing render',graph_edit:'Saving workspace',label:'Renaming label'};
function actions(...items){const row=el('div',undefined,'uxActions');row.append(...items);return row;}
function section(title,...items){const box=el('section',undefined,'uxSection');box.append(el('h4',title),...items);return box;}
function muted(text){return el('p',text,'muted');}
function badge(text,tone=''){return el('span',text,'uxBadge '+tone);}
function focusNode(n){if(n.hidden){editGraph(n,{hidden:false});}const group=state.project.nodes.find(f=>f.id===n.group);if(group?.collapsed)editGraph(group,{collapsed:false});pick(n.id);reveal(n);render();}
function nodeMenu(n,anchor){
  const menu=$('contextMenu');menu.replaceChildren();
  menu.append(el('div',n.name,'uxMenuTitle'));
  if(n.type==='blend')menu.append(button('Open in Blender',()=>run('launch',{node_id:n.id})),button('Refresh saved file · F5',()=>run('refresh',{node_id:n.id})),button('Save snapshot',()=>run('snapshot',{node_id:n.id})),button('Duplicate file · Ctrl D',()=>run('duplicate',{node_id:n.id,...placement()})),button('Render settings',()=>{inspectorTab='render';pick(n.id);configureRender(n);}));
  else menu.append(button('Open folder',()=>run('launch',{node_id:n.id})),button('Add file inside folder',()=>startPlacement(n.id)));
  menu.append(button('Edit display name · F2',()=>labelEdit(n)),button('File details',()=>{inspectorTab='overview';pick(n.id);}),button('Remove from graph',()=>editGraph(n,{hidden:true})));
  const r=anchor.getBoundingClientRect();menu.style.left=Math.max(8,Math.min(r.left,innerWidth-240))+'px';menu.style.top=Math.max(40,Math.min(r.bottom+4,innerHeight-340))+'px';menu.hidden=false;
}
// Preserve the existing controls and their handlers before moving them into menus.
const toolbar=document.querySelector('body > header'),controls=new Map([...toolbar.children].filter(e=>e.id).map(e=>[e.id,e]));
const autoLabel=$('autoRefresh').parentElement,emptyLabel=$('hideEmpty').parentElement;
toolbar.id='topbar';toolbar.replaceChildren();
const projectMenu=el('details',undefined,'uxDropdown');projectMenu.id='projectMenu';projectMenu.append(el('summary','◈ Project'));const projectList=el('div',undefined,'uxMenu');projectList.append(controls.get('newProject'),controls.get('openProject'),controls.get('backupProject'));const recentList=el('div');recentList.id='menuRecent';projectList.append(recentList,button('Blender settings',()=>modal('Blender executable',[{key:'blender',label:'Executable path',value:state.blender,required:true}],v=>run('settings',v))));projectMenu.append(projectList);
const navButton=button('☷',()=>{navigatorOpen=!navigatorOpen;document.body.classList.toggle('navigatorOpen',navigatorOpen);navButton.setAttribute('aria-expanded',String(navigatorOpen));paintNavigator();},'Project files');navButton.id='toggleNavigator';navButton.setAttribute('aria-label','Toggle project files');
const addMenu=el('details',undefined,'uxDropdown');addMenu.append(el('summary','＋ Add'));const addList=el('div',undefined,'uxMenu');addList.append(controls.get('addBlend'),controls.get('addFolder'),controls.get('importFile'));addMenu.append(addList);
const viewMenu=el('details',undefined,'uxDropdown');viewMenu.append(el('summary','View'));const viewList=el('div',undefined,'uxMenu');viewList.append(controls.get('frame'),controls.get('frameSelection'),controls.get('alignNodes'),autoLabel,emptyLabel,button('Reset zoom to 100%',()=>{view.zoom=1;transform();persist();}),button('Keyboard shortcuts',showShortcuts));viewMenu.append(viewList);
const inspectorToggle=button('Details',()=>{inspectorOpen=!inspectorOpen;document.body.classList.toggle('inspectorClosed',!inspectorOpen);inspectorToggle.setAttribute('aria-pressed',String(inspectorOpen));},'Toggle inspector');inspectorToggle.id='toggleInspector';inspectorToggle.setAttribute('aria-pressed','true');
const commands=button('Commands  Ctrl K',openCommands);commands.id='commands';
const spacer=el('span',undefined,'spacer');toolbar.append(navButton,projectMenu,controls.get('projectName'),spacer,commands,addMenu,controls.get('refresh'),viewMenu,inspectorToggle);
const navigator=el('nav');navigator.id='navigator';navigator.setAttribute('aria-label','Project files');document.body.append(navigator);
const resizeHandle=el('div');resizeHandle.id='inspectorResize';resizeHandle.title='Drag to resize details panel';document.body.append(resizeHandle);
resizeHandle.onpointerdown=e=>{e.preventDefault();resizeHandle.setPointerCapture(e.pointerId);};resizeHandle.onpointermove=e=>{if(!resizeHandle.hasPointerCapture(e.pointerId))return;document.documentElement.style.setProperty('--inspector-width',Math.max(290,Math.min(600,innerWidth-e.clientX))+'px');};
document.addEventListener('click',e=>{for(const menu of toolbar.querySelectorAll('details'))if(!menu.contains(e.target)||e.target.closest('button'))menu.open=false;},true);
function paintNavigatorBase(){
  if(!navigatorOpen)return;navigator.replaceChildren();
  const heading=el('div',undefined,'uxNavigatorHeading');heading.append(el('strong','Project files'),button('＋',()=>startPlacement(),'Add Blend File'));navigator.append(heading);
  const search=controls.get('search');search.placeholder='Filter files…';search.setAttribute('aria-label','Filter project files');navigator.append(search);
  const nodes=state.project?.nodes||[];navigator.append(el('div',undefined,'uxTree'));
  const hidden=nodes.filter(n=>n.hidden);if(hidden.length){const details=el('details',undefined,'uxHidden');details.append(el('summary',`Removed from graph · ${hidden.length}`));for(const n of hidden)details.append(button('Show '+n.name,()=>focusNode(n)));navigator.append(details);}
  navigator.append(el('div',`${nodes.filter(n=>n.type==='blend'&&!n.hidden).length} files · ${nodes.filter(n=>n.type==='folder'&&!n.hidden).length} folders`,'uxNavigatorFoot'));
}
controls.get('search').oninput=()=>{const input=controls.get('search'),start=input.selectionStart;paintNavigator();input.focus();input.setSelectionRange(start,start);};
PipelineUI.use('render','workspace-layout',200,function(next){
  if(undoProject!==state.project?.id){layoutUndo=[];layoutRedo=[];undoProject=state.project?.id;selection.clear();selected=state.view_state?.selected||null;if(selected)selection.add(selected);}
  next();
  for(const n of visibleNodes()){
    const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;card.dataset.color=n.color||'default';
    const head=card.querySelector('header');const menuButton=button('⋯',e=>nodeMenu(n,e.currentTarget),'Node actions');menuButton.className='uxNodeMenu';menuButton.onpointerdown=e=>e.stopPropagation();head.append(menuButton);
    if(n.type==='blend'){
      const body=card.querySelector('.body');body.querySelector('.path').hidden=true;
      // Move secondary actions into the inspector/menu; sockets stay available on every file.
      const duplicate=[...body.querySelectorAll('button')].find(b=>b.textContent==='Duplicate');duplicate?.parentElement.remove();
      const row=body.querySelector('.row');row.classList.add('uxNodeActions');const open=row.querySelector('button');open.textContent='Open Blender';
      for(const b of row.querySelectorAll('button')){if(b.textContent==='Snapshot'){b.textContent='◇';b.title='Save snapshot';b.setAttribute('aria-label','Save snapshot');}if(b.textContent==='↻')b.setAttribute('aria-label','Refresh node');}
      const inputRow=body.querySelector('.row.muted');if(inputRow){inputRow.childNodes[0].textContent='Linked collections';inputRow.classList.add('uxInputRow');}
      for(const incoming of body.querySelectorAll('.incoming'))incoming.remove();
      const imports=[...new Set((n.scan?.instances||[]).map(i=>i.collection))];if(imports.length){const incoming=el('div',imports.slice(0,3).join(' · ')+(imports.length>3?' · +'+(imports.length-3):''),'uxIncoming');incoming.title=imports.join('\n');inputRow.after(incoming);}
      const caption=body.querySelector('.caption');if(caption)caption.textContent=(n.collections_closed?'▸':'▾')+' Collections';
      const nodeHistory=body.querySelector('.nodeHistory');nodeHistory.classList.toggle('uxHistoryExpanded',!!n.history_open);const historyButton=nodeHistory.querySelector('button');historyButton.className='uxHistoryToggle';historyButton.title='Expand snapshots · full history in Details';
      const output=body.querySelector('.renderOutput');output.classList.add('uxOutputRow');output.title='Drag the blue socket to an output Folder';
      const stateLabel=body.querySelector('.nodeStatus');body.append(stateLabel);
      if(n.notes){const note=el('div',n.notes.split('\n')[0],'uxNodeNote');note.title=n.notes;head.after(note);}
      card.ondblclick=e=>{if(e.target.closest('header,button,input,.port,.collection,.caption'))return;run('launch',{node_id:n.id});};
    }else{
      card.querySelector('.folderLabel').textContent=`${state.project.nodes.filter(c=>c.group===n.id&&!c.hidden).length} files`;
      if(n.collapsed){card.style.width='260px';card.style.height='92px';}
    }
  }
  drawEdges();paintTasks();paintNavigator();
  recentList.replaceChildren();if(state.recent?.length){recentList.append(el('div','Recent projects','uxMenuTitle'));for(const r of state.recent.slice(0,6))recentList.append(button(r.name,()=>run('load',{path:r.path})));}
  for(const id of ['addBlend','addFolder','importFile','refresh','backupProject'])controls.get(id).disabled=!state.project;
});
PipelineUI.use('pick','navigator-selection',201,function(next, id,additive=false){next(id,additive);paintNavigator();});
function renderRunEntry(r){const entry=el('div',undefined,'renderRun');entry.append(actions(badge(`r${String(r.number).padStart(3,'0')}`),badge(r.status,r.status==='Failed'?'danger':r.status==='Complete'?'good':'')),muted(r.output));const p=el('progress');p.max=100;p.value=r.progress||0;entry.append(p);const buttons=actions(button('Open output',()=>run('render_open',{run_id:r.id})));if(r.status==='Rendering')buttons.append(button('Cancel render',()=>run('render_cancel',{run_id:r.id})));entry.append(buttons);if(r.error)entry.append(el('p',r.error,'warning'));if(r.detail){const details=el('details');details.append(el('summary','Log details'),el('pre',r.detail));entry.append(details);}return entry;}
PipelineUI.use('inspect','file-details',202,function(next){
  if(selectedConnection){next();const title=$('inspector').querySelector('h3');title?.classList.add('uxInspectorTitle');return;}
  const pane=$('inspector');pane.replaceChildren();const n=state.project?.nodes.find(n=>n.id===selected&&!n.hidden);
  const heading=el('div',undefined,'uxInspectorHeading');heading.append(el('span',n?n.type==='blend'?'BLEND FILE':'FOLDER':'PROJECT','uxEyebrow'),el('h3',n?.name||state.project?.name||'Local workspace'));pane.append(heading);
  if(!n){
    if(!state.project){pane.append(muted('Create or open a local project to begin.'),actions(button('New project',()=>controls.get('newProject').click()),button('Open project',()=>controls.get('openProject').click())));return;}
    const nodes=state.project.nodes;const active=state.project.renders?.filter(r=>r.status==='Rendering')||[];
    pane.append(section('Workspace',actions(badge(nodes.filter(n=>n.type==='blend'&&!n.hidden).length+' files'),badge(nodes.filter(n=>n.type==='folder'&&!n.hidden).length+' folders'),badge(active.length+' renders')),muted('Select a file for details. Drag a purple asset socket to another file, choose several items, then link. Blue sockets connect render outputs to folders.')));
    pane.append(section('Project folder',el('p',state.root,'uxPath'),actions(button('Backup project',()=>controls.get('backupProject').click()),button('Project files',()=>{navigatorOpen=true;document.body.classList.add('navigatorOpen');paintNavigator();}))));
    const runs=[...(state.project.renders||[])].reverse().slice(0,5);if(runs.length)pane.append(section('Recent renders',...runs.map(renderRunEntry)));
    const hidden=nodes.filter(n=>n.hidden);if(hidden.length)pane.append(section('Removed from graph',...hidden.map(item=>button('Show '+item.name,()=>focusNode(item)))));
    for(const j of state.jobs?.filter(j=>j.status==='Failed'&&!j.node_id)||[])pane.append(section('Operation failed',el('p',j.error,'warning'),button('Retry',()=>run(j.action,j.args))));
    if(state.desktop_warning)pane.append(section('Desktop launch',el('p',state.desktop_warning,'warning')));
    pane.append(section('Help',muted('Refresh reads saved files. Save in Blender before refreshing or taking a snapshot.'),button('Keyboard shortcuts',showShortcuts)));return;
  }
  if(selection.size>1)pane.append(section(`${selection.size} selected`,actions(button('Align left',()=>alignSelection('left')),button('Align top',()=>alignSelection('top')),button('Distribute',()=>alignSelection('distribute')))));
  if(n.type==='folder'){
    pane.append(section('Folder',el('p',n.path,'uxPath'),actions(button('Open folder',()=>run('launch',{node_id:n.id})),button('Add Blend File',()=>startPlacement(n.id))),muted('The frame groups files visually. Use Move / rename in a file’s details to change its disk location.')));
    const children=state.project.nodes.filter(c=>c.group===n.id&&!c.hidden);pane.append(section('Grouped files',...children.map(c=>button(c.name,()=>focusNode(c))),button(n.collapsed?'Expand frame':'Collapse frame',()=>editGraph(n,{collapsed:!n.collapsed}))));
    pane.append(section('Appearance',button('Edit label',()=>labelEdit(n)),button('Remove from graph',()=>editGraph(n,{hidden:true}))));return;
  }
  const tabs=el('div',undefined,'uxTabs');tabs.setAttribute('role','tablist');for(const [key,label] of [['overview','File'],['history','History'],['render','Render'],['links','Links']]){const b=button(label,()=>{inspectorTab=key;inspect();});b.setAttribute('role','tab');b.setAttribute('aria-selected',String(inspectorTab===key));b.classList.toggle('active',inspectorTab===key);tabs.append(b);}pane.append(tabs);
  const content=el('div',undefined,'uxTabContent');content.setAttribute('role','tabpanel');pane.append(content);
  if(n.last_error)content.append(section('Operation failed',el('p',n.last_error.message,'warning'),actions(button('Retry',()=>run(n.last_error.action,n.last_error.args)),button('Dismiss',()=>run('dismiss_error',{node_id:n.id})))));
  if(inspectorTab==='overview'){
    content.append(section('Working file',el('p',n.path,'uxPath'),actions(button('Open Blender',()=>run('launch',{node_id:n.id})),button('Refresh',()=>run('refresh',{node_id:n.id}))),badge(problem(n),problem(n)==='Ready'?'good':''),muted(n.scan?.scanned_at?'Read '+new Date(n.scan.scanned_at).toLocaleString():'Refresh to read saved collections.')));
    const notes=el('textarea');notes.rows=3;notes.value=n.notes||'';notes.placeholder='Notes for this file…';notes.setAttribute('aria-label','File notes');notes.onblur=()=>{if(notes.value!==(n.notes||''))run('graph_edit',{node_id:n.id,group:n.group||null,notes:notes.value});};
    const color=el('select');color.setAttribute('aria-label','Node color');for(const value of ['default','blue','green','purple','orange','red']){const o=el('option',value==='default'?'Default color':value[0].toUpperCase()+value.slice(1));o.value=value;color.append(o);}color.value=n.color||'default';color.onchange=()=>editGraph(n,{color:color.value});
    const group=el('select');group.setAttribute('aria-label','Visual folder');for(const item of [{value:'',label:'No folder frame'},...state.project.nodes.filter(f=>f.type==='folder'&&!f.hidden).map(f=>({value:f.id,label:f.name}))]){const o=el('option',item.label);o.value=item.value;group.append(o);}group.value=n.group||'';group.onchange=()=>editGraph(n,{group:group.value||null});
    content.append(section('Organization',el('label','Notes'),notes,el('label','Node color'),color,el('label','Visual folder'),group));
    content.append(section('File management',actions(button('Duplicate',()=>run('duplicate',{node_id:n.id,...placement()})),button('Edit label',()=>labelEdit(n))),actions(button('Move / rename',()=>relocateFile(n)),button('Adopt saved file',()=>locateFile(n))),button('Remove from graph',()=>editGraph(n,{hidden:true})),muted('Remove keeps the file on disk. Move and Adopt require saved, closed Blender sessions.')));
    if(n.scan?.error)content.append(section('Cannot read file',el('p',n.scan.error,'warning')));
  }else if(inspectorTab==='history'){
    const history=section('Saved states',button('Save snapshot',()=>run('snapshot',{node_id:n.id})),muted('Captures the last saved file. Linked assets remain separate. Restore first saves the current working copy.'));
    if(!n.snapshots.length)history.append(muted('No snapshots yet. Save a state before experimenting.'));inlineHistory(n,history,n.snapshots.length);content.append(history);
  }else if(inspectorTab==='render'){
    const config=n.render_config,output=state.project.nodes.find(f=>f.id===config?.folder_id);
    content.append(section('Render setup',config?muted(`${config.scene} · ${config.camera}\nFrames ${config.start}–${config.end} · ${config.percentage}%\nOutput: ${output?.path||'Missing folder'}`):muted('Choose an output folder, scene and camera before rendering.'),actions(button(config?'Edit settings':'Set up render',()=>configureRender(n)),button('Render saved file',()=>config?run('render_start',{node_id:n.id}):configureRender(n))),muted('Each run uses frozen inputs and a new output directory.')));
    const runs=[...(state.project.renders||[])].reverse().filter(r=>r.node_id===n.id);content.append(section('Runs',...(runs.length?runs.map(renderRunEntry):[muted('No renders yet.')])));
  }else{
    const imports=n.scan?.instances||[];content.append(section('Linked collections',...(imports.length?imports.map(i=>{const box=el('div',undefined,'uxLinkItem');const source=state.project.nodes.find(s=>normalize(nodeFile(s))===normalize(i.source));box.append(el('strong',i.collection),muted(source?.name||i.source));if(source)box.append(button('Go to source',()=>focusNode(source)));return box;}):[muted('Drag a collection from another file onto this node to link it.')])),button('Reload linked assets',()=>refreshAssets(n)));
    if(n.scan?.root_objects?.length)content.append(section('Scene-root objects',muted('These can be linked as individual objects. Collect them into a reusable collection if you prefer.'),button('Collect root objects',()=>organize(n))));
    const refs=n.scan?.refs||[];content.append(section('External references',...(refs.length?refs.map(r=>{const box=el('div',undefined,'uxLinkItem');box.append(el('strong',r.kind+' · '+(r.name||'')),el('p',r.raw,'uxPath'));if(!r.exists||r.pattern||!r.relative||!r.inside)box.append(badge(!r.exists?'Missing':r.pattern?'Pattern':!r.inside?'Outside project':'Absolute path','danger'));return box;}):[muted('No external references found.')]))) ;
  }
});
PipelineUI.use('paintTasks','workflow-status',203,function(next){next();for(const n of state.project?.nodes||[]){const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;const text=card.querySelector('.nodeStatus'),job=state.jobs?.find(j=>j.node_id===n.id&&['Running','Queued'].includes(j.status)),r=state.project.renders?.find(r=>r.node_id===n.id&&r.status==='Rendering');if(text){text.textContent=job?(actionNames[job.action]||'Working')+'…':r?`Rendering · ${r.progress}%`:problem(n);text.classList.toggle('warning',!!n.last_error||!!n.scan?.error);text.classList.toggle('ready',text.textContent==='Ready');}card.classList.toggle('uxDropTarget',!!wire&&(wire.render?n.type==='folder':n.type==='blend'&&!n.external&&n.id!==wire.source));}const running=state.jobs?.filter(j=>['Running','Queued'].includes(j.status))||[];if(running.length)$('taskMessage').textContent=running.map(j=>actionNames[j.action]||j.action).join(' · ');});
function layoutState(){return {project:state.project?.id,nodes:(state.project?.nodes||[]).map(n=>({id:n.id,x:n.x,y:n.y,width:n.width,height:n.height,group:n.group||null})),view:{...view}};}
function rememberLayout(snapshot){if(!snapshot.project)return;const previous=layoutUndo.at(-1);if(JSON.stringify(previous?.nodes)===JSON.stringify(snapshot.nodes))return;layoutUndo.push(snapshot);if(layoutUndo.length>40)layoutUndo.shift();layoutRedo=[];}
drag=function(e){if(move?.type==='node'&&!move.uxRecorded){move.uxRecorded=true;rememberLayout(layoutState());}uxDrag(e);};
const uxAlign=alignSelection;alignSelection=function(mode){rememberLayout(layoutState());uxAlign(mode);};
function applyLayout(snapshot){if(snapshot.project!==state.project?.id)return;for(const p of snapshot.nodes){const n=state.project.nodes.find(n=>n.id===p.id);if(n){n.x=p.x;n.y=p.y;if(n.group!==p.group||n.width!==p.width||n.height!==p.height){n.group=p.group;if(p.width!==undefined)n.width=p.width;if(p.height!==undefined)n.height=p.height;run('graph_edit',{node_id:n.id,group:n.group,width:n.width,height:n.height});}}}view={...snapshot.view};render();persist();}
function undoLayout(redo=false){const from=redo?layoutRedo:layoutUndo,to=redo?layoutUndo:layoutRedo;if(!from.length)return status(redo?'No layout changes to redo':'No layout changes to undo');to.push(layoutState());applyLayout(from.pop());status(redo?'Layout redone':'Layout undone · file contents unchanged');}
function arrangeGraph(){
  if(!state.project)return;rememberLayout(layoutState());
  const files=state.project.nodes.filter(n=>n.type==='blend'&&!n.hidden),ranks=new Map(),visiting=new Set();
  function rank(n){if(ranks.has(n.id))return ranks.get(n.id);if(visiting.has(n.id))return 0;visiting.add(n.id);const sources=files.filter(s=>s.id!==n.id&&(n.scan?.instances||[]).some(i=>normalize(i.source)===normalize(nodeFile(s))));const depth=sources.length?1+Math.max(...sources.map(rank)):0;visiting.delete(n.id);ranks.set(n.id,depth);return depth;}
  files.forEach(rank);let laneY=60;
  const frames=state.project.nodes.filter(n=>n.type==='folder'&&!n.hidden),lanes=[...frames.map(f=>({frame:f,files:files.filter(n=>n.group===f.id)})),{files:files.filter(n=>!frames.some(f=>f.id===n.group))}];
  for(const lane of lanes){const columns=new Map();let bottom=laneY+160,right=340;for(const n of lane.files){const depth=ranks.get(n.id),y=columns.get(depth)||laneY+70;n.x=80+depth*310;n.y=y;const height=document.querySelector(`[data-id="${n.id}"]`)?.offsetHeight||250;columns.set(depth,y+height+38);bottom=Math.max(bottom,y+height+30);right=Math.max(right,n.x+274);}
    if(lane.frame){lane.frame.x=50;lane.frame.y=laneY;lane.frame.width=Math.max(320,right-20);lane.frame.height=bottom-laneY+10;run('graph_edit',{node_id:lane.frame.id,group:null,width:lane.frame.width,height:lane.frame.height});}if(lane.frame||lane.files.length)laneY=bottom+70;
  }render();persist();controls.get('frame').click();status('Arranged by dependency · Ctrl Z undoes layout');
}
viewList.append(button('Arrange by dependency',arrangeGraph),button('Undo layout · Ctrl Z',()=>undoLayout()),button('Redo layout · Ctrl Shift Z',()=>undoLayout(true)));
function showShortcuts(){modal('Keyboard shortcuts',[],()=>{});$('fields').append(muted('Ctrl K — commands / find a file\nF2 — edit selected label\nF5 — refresh selected file\nCtrl D — duplicate selected file\nHome — frame all\nN — toggle details\nCtrl Z / Ctrl Shift Z — undo / redo layout only\nShift-click — add to selection\nShift-drag canvas — box select\nMiddle mouse — pan\nWheel — zoom\nEscape — cancel placement or connection'));$('submit').textContent='Done';}
const uxModal=modal;modal=function(title,fields,callback){$('submit').textContent='Confirm';uxModal(title,fields,callback);requestAnimationFrame(()=>{const input=$('fields').querySelector('input:not([type=checkbox]),select');input?.focus();});};
function openCommands(){
  if($('dialog').open)return;const palette=$('commandPalette');palette.showModal();$('commandQuery').value='';paintCommands('');$('commandQuery').focus();
}
function paintCommands(query){
  const list=$('commandResults');list.replaceChildren();const q=query.toLowerCase();const n=state.project?.nodes.find(n=>n.id===selected);
  const items=[['Add Blend File',()=>startPlacement()],['Add Folder',()=>controls.get('addFolder').click()],['Import Blend File',()=>controls.get('importFile').click()],['Frame all files',()=>controls.get('frame').click()],['Arrange by dependency',arrangeGraph],['Undo layout',()=>undoLayout()],['Backup project',()=>controls.get('backupProject').click()],['Keyboard shortcuts',showShortcuts]];
  if(n?.type==='blend')items.unshift(['Open '+n.name,()=>run('launch',{node_id:n.id})],['Snapshot '+n.name,()=>run('snapshot',{node_id:n.id})],['Refresh '+n.name,()=>run('refresh',{node_id:n.id})]);
  for(const [name,fn] of items.filter(([name])=>name.toLowerCase().includes(q)))list.append(button(name,()=>{$('commandPalette').close();fn();}));
  for(const file of state.project?.nodes.filter(n=>!n.hidden&&(n.name+' '+n.path).toLowerCase().includes(q))||[])list.append(button('▧ '+file.name,()=>{$('commandPalette').close();focusNode(file);}));
  if(!list.children.length)list.append(muted('No matching commands or files.'));list.querySelector('button')?.classList.add('active');
}
const palette=el('dialog');palette.id='commandPalette';const query=el('input');query.id='commandQuery';query.placeholder='Find a command or file…';query.setAttribute('aria-label','Find a command or file');const results=el('div');results.id='commandResults';palette.append(query,results,muted('↑ ↓ navigate · Enter run · Escape close'));document.body.append(palette);query.oninput=()=>paintCommands(query.value);palette.onkeydown=e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const buttons=[...results.querySelectorAll('button')];let index=buttons.findIndex(b=>b.classList.contains('active'));buttons.forEach(b=>b.classList.remove('active'));index=(index+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;buttons[index]?.classList.add('active');buttons[index]?.scrollIntoView({block:'nearest'});}if(e.key==='Enter'){e.preventDefault();results.querySelector('button.active')?.click();}};
document.addEventListener('keydown',e=>{
  const typing=document.activeElement?.matches('input:not([readonly]),textarea,select,[contenteditable=true]');
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommands();return;}
  if(typing||$('dialog').open||palette.open)return;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();undoLayout(e.shiftKey);}
  if(e.key==='Home'){e.preventDefault();controls.get('frame').click();}
  if(e.key==='F2'&&selected){e.preventDefault();labelEdit(state.project.nodes.find(n=>n.id===selected));}
  if(e.key.toLowerCase()==='n'&&!e.ctrlKey&&!e.metaKey)inspectorToggle.click();
});
document.addEventListener('pointerdown',e=>{blankPress=e.button===0&&!e.shiftKey&&!adding&&!wire&&e.target.closest('#workspace')&&emptyCanvas(e)?{x:e.clientX,y:e.clientY}:null;},true);
document.addEventListener('pointerup',e=>{if(blankPress&&Math.hypot(e.clientX-blankPress.x,e.clientY-blankPress.y)<4){selected=null;selectedConnection=null;selection.clear();for(const card of document.querySelectorAll('.node'))card.classList.remove('selected','multiSelected');drawEdges();inspect();paintNavigator();}blankPress=null;});
if(state.project)render();else inspect();

