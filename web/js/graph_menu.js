/* One owner for canvas, node-action and output-creation menus. */
(function(){
  const {addFrame,addExport,activeGroup,removeNode}=PipelineUI.graphNodes;
  const colors={default:'#62676d',blue:'#405f79',green:'#486454',purple:'#625271',orange:'#796144',red:'#754e52'};
  let dropClick=null;
  function item(label,icon,action,shortcut=''){
    const b=button('',action);b.className='graphMenuItem';b.dataset.menuIcon=icon;b.setAttribute('role','menuitem');b.setAttribute('aria-label',label);
    b.append(blenderIcon(icon),el('span',label,'graphMenuLabel'));if(shortcut)b.append(el('small',shortcut,'graphMenuShortcut'));return b;
  }
  function begin(){dropClick=null;const menu=$('contextMenu');menu.replaceChildren();menu.removeAttribute('aria-label');menu.setAttribute('role','menu');return menu;}
  function show(menu,clientX,clientY){
    menu.hidden=false;menu.classList.remove('openLeft');
    const left=Math.max(8,Math.min(clientX,innerWidth-menu.offsetWidth-8));
    menu.style.left=left+'px';menu.style.top=Math.max(40,Math.min(clientY,innerHeight-menu.offsetHeight-12))+'px';
    menu.classList.toggle('openLeft',left+menu.offsetWidth+160>innerWidth);
  }
  function separator(menu){menu.append(el('div',undefined,'graphMenuSeparator'));}
  function details(n){if(!inspectorOpen)inspectorToggle.click();inspectorTab='overview';pick(n.id);}
  function colorMenu(menu,n){
    const group=el('div',undefined,'graphSubmenu'),trigger=item('Change Color','preferences',()=>{panel.hidden=false;panel.querySelector('button')?.focus();}),panel=el('div',undefined,'graphSubmenuPanel');
    trigger.dataset.submenuTrigger='true';trigger.setAttribute('aria-haspopup','menu');trigger.append(el('span','›','graphMenuArrow'));panel.setAttribute('role','menu');panel.setAttribute('aria-label','Node colors');
    for(const [value,hex] of Object.entries(colors)){
      const label=value[0].toUpperCase()+value.slice(1),b=item(label,'checkmark',()=>run('node_colors',{node_ids:selection.has(n.id)?[...selection]:[n.id],color:value}));
      const swatch=el('span',undefined,'graphColorSwatch');swatch.style.background=hex;b.querySelector('.blIcon').replaceWith(swatch);b.classList.toggle('currentColor',(n.color||'default')===value);panel.append(b);
    }
    trigger.onkeydown=e=>{if(e.key==='ArrowRight'){e.preventDefault();panel.querySelector('button').focus();}};
    panel.onkeydown=e=>{if(e.key==='ArrowLeft'){e.preventDefault();trigger.focus();}};
    group.append(trigger,panel);menu.append(group);
  }
  async function outputFolder(n,p){
    const projectId=state.project.id,scene=(n.scan?.scenes||[]).find(s=>s.name===n.scan.active_scene&&!s.linked)||(n.scan?.scenes||[]).find(s=>!s.linked);
    const base='Out_'+(scene?.name||n.name).replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/[. ]+$/g,'');
    let title=base,i=1;const parent=activeGroup(p);let physical=state.project.nodes.find(f=>f.id===parent);
    while(physical&&physical.type!=='folder')physical=state.project.nodes.find(f=>f.id===physical.group);
    const prefix=physical?physical.path+'/':'';while(state.project.nodes.some(f=>f.type==='folder'&&f.path.toLowerCase()===(prefix+title).toLowerCase()))title=base+'_'+String(i++).padStart(2,'0');
    const before=new Set(state.project.nodes.map(f=>f.id)),result=await run('folder',{title,folder_id:parent,...p,width:350,height:220});
    if(!result||result.project?.id!==projectId)return;const folder=result.project.nodes.find(f=>!before.has(f.id));if(!folder)return;
    if(!scene?.camera)return configureRender(n,folder.id);
    await run('render_config',{node_id:n.id,...(n.render_config||{scene:scene.name,camera:'',auto_prefix:true}),folder_id:folder.id});
  }
  function creationMenu(p,clientX,clientY){
    const menu=begin(),chosen=topSelection(),group=activeGroup(p);
    menu.append(item('Blend node','file_blend',()=>run('blend',{folder_id:group,...p})),
      item('Render node','render_animation',()=>run('render_node',{group,...p})),
      item('Export node','file_archive',()=>addExport(p)),
      item('Folder node','file_folder',()=>createFolderHere(p,group,chosen.length>0),chosen.length?'Around selection':''),
      item('Frame','nodetree',()=>addFrame(p,chosen.length>0),chosen.length?'Around selection':''));
    if(window.PipelineClipboard.canPaste()){separator(menu);menu.append(item('Paste','duplicate',()=>window.PipelineClipboard.pasteSelection(p),'Ctrl V'));}
    show(menu,clientX,clientY);
  }
  nodeMenu=function(n,anchor){
    if(!state.project||busy||window.pipelineBusy())return;
    if(!selection.has(n.id))pick(n.id);
    const menu=begin();menu.append(item('Details','preferences',()=>details(n)));colorMenu(menu,n);
    if(!n.external){separator(menu);menu.append(item('Copy','duplicate',()=>window.PipelineClipboard.copySelection(),'Ctrl C'),item('Duplicate','duplicate',()=>run('paste_nodes',{node_ids:[...selection],clipboard_project_id:state.project.id}),'Ctrl D'));}
    if(n.type==='render')menu.append(item('Rendering workspace','render_still',()=>openRenderManager(n.id)));
    if(n.type==='folder'||n.type==='frame')menu.append(item(n.collapsed?'Expand':'Collapse','nodetree',()=>editGraph(n,{collapsed:!n.collapsed})));
    if(n.external)menu.append(item('Collect into project','linked',()=>collectLibrary(n)));
    separator(menu);
    const remove=item(n.type==='blend'&&!n.external?'Delete file…':n.type==='folder'?'Delete folder…':'Remove node…','trash',()=>{
      if(n.type==='folder')return deleteFolder(n);
      if(n.type==='blend'&&!n.external){modal('Archive '+n.name+'?',[{key:'closed',type:'checkbox',required:true,label:'I saved and closed this file in every Blender window'}],v=>run('archive_blend',{node_id:n.id,...v}));$('fields').append(muted('Moves the working file into the project archive. Restore it later through Project → Archived files. Snapshot history is kept.'));$('submit').textContent='Archive file';return;}
      if(n.external)return editGraph(n,{hidden:true});
      removeNode(n);
    });remove.classList.add('graphMenuDanger');if(n.type==='blend'&&reportedOpen(n)){remove.disabled=true;remove.title='Close the file in Blender before archiving.';}menu.append(remove);
    const r=anchor.getBoundingClientRect();show(menu,r.left,r.bottom+4);
  };
  $('workspace').oncontextmenu=e=>{
    e.preventDefault();if(!state.project||busy||window.pipelineBusy())return;
    const hit=e.target.closest('.node'),isCanvas=emptyCanvas(e);
    if(!isCanvas&&hit){const n=state.project.nodes.find(n=>n.id===hit.dataset.id);if(!n)return;nodeMenu(n,hit.querySelector('header'));show($('contextMenu'),e.clientX,e.clientY);}
    else creationMenu(worldPoint(e.clientX,e.clientY),e.clientX,e.clientY);
  };
  window.pipelineOfferOutputNodes=function(n,p,event){
    const menu=begin(),projectId=state.project.id;
    const guarded=fn=>()=>{if(state.project?.id===projectId)fn();};
    menu.setAttribute('aria-label','Create connected output');
    menu.append(item('Folder','file_folder',guarded(()=>outputFolder(n,p))),item('Render','render_animation',guarded(()=>run('render_node',{source_ids:[n.id],group:activeGroup(p),...p}))),item('Export','file_archive',guarded(()=>addExport(p,n.id))));
    show(menu,event.clientX,event.clientY);menu.querySelector('button').focus();
    dropClick={x:event.clientX,y:event.clientY,time:event.timeStamp};
  };
  document.addEventListener('click',e=>{
    // The release that opens a drag picker can also emit a canvas click.
    // Consume that one click, then preserve normal outside-click dismissal.
    const inside=e.target.closest('#contextMenu');
    if(dropClick){const drop=dropClick;dropClick=null;if(!inside&&Math.abs(e.clientX-drop.x)<3&&Math.abs(e.clientY-drop.y)<3&&e.timeStamp-drop.time<500)return;}
    if(!inside||e.target.closest('#contextMenu button:not([data-submenu-trigger])'))$('contextMenu').hidden=true;
  },true);
})();
