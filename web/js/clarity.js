/* Common actions first; optional guidance and details never obstruct the graph. */
const clarityDisclosure=new Map();
function disclosure(key,title,...items){const box=el('details',undefined,'cgDisclosure'),summary=el('summary',title),context=[state.project?.id,selected,inspectorTab,key].join(':');box.append(summary,...items);box.open=clarityDisclosure.get(context)||false;box.addEventListener('toggle',()=>clarityDisclosure.set(context,box.open));return box;}
function quickGuide(){
  modal('Quick guide',[],()=>{});$('submit').textContent='Back to work';
  const list=el('ol',undefined,'cgSteps');
  for(const [title,text] of [
    ['Create a file','Add → Blend File, then click the graph to place it. Double-click its name to rename it.'],
    ['Work in Blender','Open Blender from the node. Save there, then Refresh the node here to read its saved contents.'],
    ['Link assets','Drag the purple socket from a source file onto another file. Choose collections, objects or materials together, then link.'],
    ['Render','Add a Render node. Connect file outputs to it, then its Images output to a Folder. Settings contains per-scene values and shared overrides. Rendering shows the queue and versions.']
  ]){const item=el('li');item.append(el('strong',title),muted(text));list.append(item);}$('fields').append(list);
  const legend=el('div',undefined,'cgConnectionGuide');legend.append(el('span','Purple · assets between files','cgAssets'),el('span','Blue · renders into folders','cgOutput'));$('fields').append(legend);
  $('fields').append(disclosure('guide-details','Folders, saved states and render versions',muted('Folders organize files. Only blue output connections make them render destinations.'),muted('Save snapshot keeps a copy of the last saved Blend File. History lets you restore it. Each render creates a separate version; Versions manages those outputs.')),
    muted('Middle-drag to pan · wheel to zoom · left-drag to select · right-click for actions.'),actions(button('Keyboard shortcuts',showShortcuts),button('Blender companion setup',showCompanionGuide)));
}
const helpButton=button('?',quickGuide,'Help · Quick guide');helpButton.id='quickGuide';helpButton.setAttribute('aria-label','Help');toolbar.insertBefore(helpButton,inspectorToggle);

function heading(n){const title=el('div',undefined,'uxInspectorHeading');title.append(el('span',n.type==='folder'?'FOLDER':'PROJECT','uxEyebrow'),el('h3',n.name));return title;}
function projectOverview(){const pane=$('inspector'),nodes=state.project.nodes,files=nodes.filter(n=>n.type==='blend'&&!n.hidden),outputs=outputTargets(),active=(state.project.render_queue||[]).filter(q=>['Queued','Preparing','Rendering'].includes(q.status));pane.replaceChildren(heading({type:'project',name:state.project.name}));
  const next=!files.length?'Create your first Blend File, then place it on the graph.':files.every(n=>!savedAssets(n).length)?'Open a file in Blender and save your work. The graph refreshes saved contents.':'Drag purple sockets to link assets. Connect file outputs → Render → Folder to render scenes.';
  const fileCount=files.length+' file'+(files.length===1?'':'s'),folderCount=nodes.filter(n=>n.type==='folder'&&!n.hidden).length,workspace=renderPanel('Workspace · '+fileCount,'project-workspace',true);workspace.title=next;workspace.append(muted(`${fileCount} · ${folderCount} folder${folderCount===1?'':'s'}`),actions(button('Add Blend File',()=>startPlacement()),button('Import file',()=>controls.get('importFile').click()),button('Quick guide',quickGuide)));pane.append(workspace);
  const issues=files.filter(n=>n.last_error||n.scan?.error||state.files?.[n.id]?.missing);if(issues.length){const attention=renderPanel('Needs attention · '+issues.length,'project-attention',true);attention.append(...issues.slice(0,3).map(n=>button(n.name+' · '+problem(n),()=>focusNode(n))));pane.append(attention);}
  if(outputs.length||active.length||state.project.renders?.some(r=>r.status!=='Deleted')){const setupCount=outputs.length+' setup'+(outputs.length===1?'':'s'),sourceCount=new Set(outputs.map(n=>n.source_id||n.id)).size,rendering=renderPanel('Rendering · '+setupCount+(active.length?' · '+active.length+' active':''),'project-rendering',false);rendering.append(muted(`${setupCount} from ${sourceCount} file${sourceCount===1?'':'s'}`),button('Open rendering',()=>openRenderManager()));pane.append(rendering);}
  for(const job of (state.jobs||[]).filter(j=>j.status==='Failed'&&!j.node_id).slice(-2)){const failure=renderPanel('Operation failed','project-failed:'+job.id,true);failure.append(el('p',job.error,'warning'),button('Retry',()=>run(job.action,job.args)));pane.append(failure);}
  const tools=renderPanel('Project tools','project-tools',false);tools.append(el('p',state.root,'uxPath'),actions(button('Backup project',()=>controls.get('backupProject').click()),button('Archived files',openArchivedFiles)),button('Startup templates',templateManager),button('Check project',()=>showPreflight()),button('Blender companion setup',showCompanionGuide));pane.append(tools);
  const hidden=nodes.filter(n=>n.hidden);if(hidden.length){const hiddenPanel=renderPanel('Hidden nodes · '+hidden.length,'project-hidden',false);hiddenPanel.append(...hidden.map(n=>button('Show '+n.name,()=>focusNode(n))));pane.append(hiddenPanel);}
  if(state.desktop_warning){const desktop=renderPanel('Desktop launch','project-desktop',false);desktop.title=state.desktop_warning;desktop.append(el('p',state.desktop_warning,'warning'));pane.append(desktop);}
}
function folderOverview(n){const pane=$('inspector'),children=state.project.nodes.filter(c=>c.group===n.id&&!c.hidden),info=state.folder_info?.[n.id]||{};pane.replaceChildren(heading(n));
  if(selection.size>1)pane.append(section(`${selection.size} selected`,actions(button('Align left',()=>alignSelection('left')),button('Align top',()=>alignSelection('top')),button('Distribute',()=>alignSelection('distribute')))));
  pane.append(folderDetailTabs(n));
  if(folderRenderingTab?.id===n.id&&folderRenderingTab.key==='outputs'){PipelineUI.outputs.folderDetails(pane,n);return;}
  pane.append(section('Folder',el('p',n.path,'uxPath'),actions(button('Open folder',()=>run('launch',{node_id:n.id})),button('Add file',()=>startPlacement(n.id)),button('Add folder',()=>createFolderHere({x:n.x+28,y:n.y+125},n.id))),muted(`${children.length} grouped nodes · ${info.files||0} files on disk`)));
  if(info.error||info.missing)pane.append(el('p',info.error||'Folder is missing on disk.','warning'));
  if(children.length){const list=el('div',undefined,'cgChildren');for(const child of children.slice(0,8))list.append(button(child.name,()=>focusNode(child)));pane.append(section('Inside this frame',list));if(children.length>8)pane.append(disclosure('folder-members','More grouped nodes · '+(children.length-8),...children.slice(8).map(child=>button(child.name,()=>focusNode(child)))));}
  pane.append(disclosure('folder-disk','Files on disk · '+(info.files||0),folderListing(n),button('Open folder',()=>run('launch',{node_id:n.id}))));
  const parent=el('select');parent.setAttribute('aria-label','Parent folder frame');for(const item of [{value:'',label:'No parent frame'},...state.project.nodes.filter(f=>f.type==='folder'&&f.id!==n.id&&!f.hidden&&!inFrame(f,n.id)).map(f=>({value:f.id,label:f.name}))]){const option=el('option',item.label);option.value=item.value;parent.append(option);}parent.value=n.group||'';parent.onchange=()=>run('group_nodes',{groups:{[n.id]:parent.value||null}});
  pane.append(disclosure('folder-tools','Organization / folder actions',parent,muted('Grouping existing nodes keeps their disk paths. Add folder creates a real directory inside this folder.'),actions(button('Edit name',()=>labelEdit(n)),button(n.collapsed?'Expand frame':'Collapse frame',()=>editGraph(n,{collapsed:!n.collapsed}))),button('Delete folder…',()=>deleteFolder(n))));
}
PipelineUI.use('inspect','details-disclosure',1600,function(next){next();if(selectedConnection||selectedDataConnection)return;const n=state.project?.nodes.find(n=>n.id===selected);if(!state.project)return;
  if(!n)projectOverview();
  else if(n.type==='folder'&&!(folderRenderingTab?.id===n.id&&folderRenderingTab.key==='render'&&folderHasRendering(n)))folderOverview(n);
  else if(n.type==='blend'){
    const content=$('inspector').querySelector('.uxTabContent');if(content&&inspectorTab==='overview')for(const box of [...content.querySelectorAll(':scope>.uxSection')]){const title=box.querySelector('h4')?.textContent.trim();if(['File management','Organization','Workflow stage'].includes(title)){const fold=disclosure('file-'+title,title==='File management'?'File actions':title==='Organization'?'Notes / color / grouping':'Workflow label',...[...box.children].slice(1));box.replaceWith(fold);}}
    if(content&&inspectorTab==='render'){const runs=[...content.querySelectorAll(':scope>.rmVersion')];if(runs.length>2){const older=disclosure('file-render-history','Earlier render versions · '+(runs.length-2),...runs.slice(2));content.append(older);}}
  }
  for(const group of $('inspector').querySelectorAll('.uxTabs')){group.setAttribute('role','tablist');for(const tab of group.querySelectorAll('button')){tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(tab.classList.contains('active')));tab.tabIndex=tab.classList.contains('active')?0:-1;}}
  for(const tab of $('inspector').querySelectorAll('[role=tab]'))tab.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const tabs=[...tab.parentElement.querySelectorAll('[role=tab]')],i=tabs.indexOf(tab),next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length,label=tabs[next].textContent;tabs[next].click();[...$('inspector').querySelectorAll('[role=tab]')].find(t=>t.textContent===label)?.focus();};
  polishInterface();
});

const clarityConfigure=configureRender;configureRender=async function(...args){await clarityConfigure(...args);if(!$('dialog').open||!$('fields').querySelector('.rmSettingsWrap'))return;
  function foldSettings(){for(const old of $('fields').querySelectorAll('.cgSceneSettings'))if(!old.querySelector('.rmSettingsWrap'))old.remove();const grid=$('fields').querySelector('.rmSettingsWrap');if(!grid||grid.closest('.cgSceneSettings'))return;const details=el('details',undefined,'cgDisclosure cgSceneSettings');grid.before(details);details.append(el('summary','Scene settings · optional changes'),grid);details.open=!!grid.querySelector('.rmSetting.enabled');const note=[...$('fields').querySelectorAll('p')].find(p=>p.textContent.startsWith('Unchecked settings'));if(note)note.textContent='Uses the saved Blender settings unless you enable a change below.';}
  const prefix=$('field-prefix'),auto=$('field-auto_prefix'),prefixLabel=$('fields').querySelector('label[for=field-prefix]'),preview=el('p',undefined,'cgFilename');prefix.after(preview);function naming(){prefix.hidden=auto.checked;if(prefixLabel)prefixLabel.hidden=auto.checked;preview.textContent=auto.checked?'Automatic name: '+prefix.value+'0001':'Custom filename prefix';}
  const change=auto.onchange;auto.onchange=e=>{change?.(e);naming();};const scene=$('field-scene'),sceneChange=scene.onchange;scene.onchange=e=>{sceneChange?.(e);foldSettings();naming();};foldSettings();naming();
};


const firstSteps=el('div');firstSteps.id='firstSteps';firstSteps.hidden=true;$('workspace').append(firstSteps);
function paintFirstSteps(){const empty=state.project&&!state.project.nodes.some(n=>n.type==='blend'&&!n.hidden);firstSteps.hidden=!empty;if(!empty)return;if(firstSteps.children.length)return;firstSteps.append(el('strong','Start with a Blend File'),muted('Create a file, place it on the graph, then open it in Blender.'),actions(button('Add Blend File',()=>startPlacement()),button('Quick guide',quickGuide)));}
PipelineUI.use('render','onboarding',1601,function(next){next();paintFirstSteps();for(const port of document.querySelectorAll('[data-render]')){port.title='Output · drag to Render, Export, Folder or empty canvas';port.setAttribute('aria-label','Render output');}for(const port of document.querySelectorAll('[data-bundle]'))port.title='Link assets · drag onto another Blend File';});
const clarityEmpty=emptyCanvas;emptyCanvas=function(e){return !e.target.closest('#firstSteps')&&clarityEmpty(e);};
if(state.project)render();else inspect();

/* Outside-click cancels a popup; dragging out of a control never dismisses it. */
let popupBackdropPress=null;
function outsidePopup(dialog,event){const box=dialog.getBoundingClientRect();return event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom;}
document.addEventListener('pointerdown',event=>{
  popupBackdropPress=null;
  const dialog=event.target.closest?.('dialog');
  if(event.button===0&&!busy&&dialog?.open&&!['renderManager','outputBrowser'].includes(dialog.id)&&event.target===dialog&&outsidePopup(dialog,event))popupBackdropPress={dialog,pointer:event.pointerId};
},true);
document.addEventListener('pointerup',event=>{
  const press=popupBackdropPress;popupBackdropPress=null;
  if(press&&!busy&&press.pointer===event.pointerId&&press.dialog.open&&event.target===press.dialog&&outsidePopup(press.dialog,event)){
    event.preventDefault();event.stopImmediatePropagation();press.dialog.close();
  }
},true);
document.addEventListener('pointercancel',()=>{popupBackdropPress=null;},true);
document.addEventListener('keydown',event=>{
  if(event.key!=='Escape'||busy||document.querySelector('dialog[open]:modal'))return;
  const menus=[...toolbar.querySelectorAll('details[open]')];
  if(menus.length||!$('contextMenu').hidden){event.preventDefault();event.stopImmediatePropagation();menus.forEach(menu=>menu.open=false);$('contextMenu').hidden=true;return;}
  if(renderManager.open){event.preventDefault();event.stopImmediatePropagation();closeRenderManager();}
},true);

/* Give every popup a consistent, accessible close control, including refreshed lists. */
function polishPopups(){for(const dialog of document.querySelectorAll('dialog:not(#renderManager):not(#outputBrowser)')){
  const title=dialog.querySelector(':scope>h3,:scope>form>h3');
  if(title){if(!title.id)title.id=dialog.id+'-title';dialog.setAttribute('aria-labelledby',title.id);}
  else if(dialog.id==='commandPalette')dialog.setAttribute('aria-label','Commands and files');
  if(!dialog.querySelector(':scope>.dialogDismiss')){
    const close=button('×',()=>dialog.close(),'Close · Escape');close.className='dialogDismiss';close.setAttribute('aria-label','Close popup');dialog.append(close);
  }
}}
polishPopups();new MutationObserver(polishPopups).observe(document.body,{childList:true,subtree:true});
