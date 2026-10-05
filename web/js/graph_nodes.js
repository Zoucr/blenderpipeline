/* Visual frames and saved-file exports. Settings stay inside each operation. */
(function(){
  const containers=n=>['folder','frame'].includes(n?.type);
  const outputFormats=[{value:'GLB',label:'glTF binary · .glb'},{value:'FBX',label:'FBX · .fbx'},
    {value:'USD',label:'USD binary · .usdc'},{value:'ALEMBIC',label:'Alembic · .abc'}];
  const formatHelp={GLB:'Portable mesh / PBR assets. Procedural Blender shaders need baking.',
    FBX:'Objects, rigs and animation. Blender shader graphs are not preserved.',
    USD:'Scene interchange with supported materials and separate texture files.',
    ALEMBIC:'Evaluated geometry and animation cache. Material shader graphs are not included.'};
  const exportViews=new Map();
  const exportOptionsOpen=new Map();
  function activeGroup(p){return visibleNodes().filter(n=>containers(n)&&!n.collapsed&&p.x>n.x&&p.x<n.x+(n.width||650)&&p.y>n.y+28&&p.y<n.y+(n.height||420)).sort((a,b)=>frameAncestors(b).length-frameAncestors(a).length)[0]?.id||null;}
  async function addFrame(p,around=false){
    if(!state.project)return error('Open a project first.');
    const nodes=around?topSelection():[],shared=nodes[0]?.group||null;
    let width=500,height=300,group=activeGroup(p);
    if(nodes.length){const bounds=nodes.map(n=>{const card=document.querySelector(`[data-id="${n.id}"]`);return {x:n.x,y:n.y,w:card?.offsetWidth||260,h:card?.offsetHeight||260};});
      p={x:Math.min(...bounds.map(b=>b.x))-28,y:Math.min(...bounds.map(b=>b.y))-62};
      width=Math.max(...bounds.map(b=>b.x+b.w))-p.x+28;height=Math.max(...bounds.map(b=>b.y+b.h))-p.y+28;
      group=nodes.every(n=>(n.group||null)===shared)?shared:null;
    }
    const number=(state.project.nodes.filter(n=>n.type==='frame').length+1).toString().padStart(3,'0');
    return run('frame',{title:'Frame '+number,node_ids:nodes.map(n=>n.id),group,...p,width,height});
  }
  async function addExport(p,source=null){
    if(!state.project)return error('Open a project first.');
    const n=state.project.nodes.find(n=>n.id===source);
    return run('export_node',{source_id:n?.type==='blend'?n.id:null,group:activeGroup(p),...p});
  }
  function removeNode(n){modal('Remove '+n.name+'?',[],()=>run('remove_graph_node',{node_id:n.id,confirmed:true}));
    $('fields').append(muted(n.type==='frame'?'Removes the visual frame. Its nodes and all files stay intact.':'Removes this operation and its connections. Existing output files stay on disk.'),muted('You can restore this node from Project → Archived files.'));$('submit').textContent='Remove node';}
  function appearance(n){
    const colors=selectControl('Node color',[{value:'default',label:'Default'},...['blue','green','purple','orange','red'].map(value=>({value,label:typeLabel(value)}))],n.color||'default');
    colors.onchange=()=>editGraph(n,{color:colors.value});
    const groups=selectControl('Parent frame or folder',[{value:'',label:'No container'},...state.project.nodes.filter(f=>containers(f)&&f.id!==n.id&&!f.hidden&&!inFrame(f,n.id)).map(f=>({value:f.id,label:f.name}))],n.group||'');
    groups.onchange=()=>run('group_nodes',{groups:{[n.id]:groups.value||null}});
    return section('Organization',field('Parent',groups),field('Color',colors),actions(button('Rename',()=>labelEdit(n)),button('Remove…',()=>removeNode(n))));
  }
  function selectControl(label,options,value){const s=el('select');s.setAttribute('aria-label',label);for(const item of options){const o=el('option',item.label);o.value=item.value;s.append(o);}s.value=value;return s;}
  function field(label,control){const row=el('label',undefined,'graphField');row.append(el('span',label),control);return row;}
  function cardFor(n){const card=el('div',undefined,'node '+n.type);card.dataset.id=n.id;card.dataset.color=n.color||'default';card.style.left=n.x+'px';card.style.top=n.y+'px';card.classList.toggle('selected',selected===n.id);card.classList.toggle('multiSelected',selection.has(n.id)&&selection.size>1);
    card.onclick=e=>{if(!e.target.closest('header,button,input,select,.port,.frameResize'))pick(n.id,e.shiftKey);};
    const head=nodeHeader(n),baseDown=head.onpointerdown;head.onpointerdown=e=>{if(e.shiftKey){e.stopPropagation();pick(n.id,true);return;}baseDown(e);};
    const menu=button('⋯',e=>nodeMenu(n,e.currentTarget),'Node actions');menu.className='uxNodeMenu';menu.onpointerdown=e=>e.stopPropagation();head.append(menu);card.append(head);return card;
  }
  function frameCard(n){const card=cardFor(n);card.style.width=(n.width||650)+'px';card.style.height=(n.collapsed?60:n.height||420)+'px';card.style.zIndex=String(frameAncestors(n).length+1);
    const toggle=button(n.collapsed?'▸':'▾',()=>editGraph(n,{collapsed:!n.collapsed}),n.collapsed?'Expand frame':'Collapse frame');toggle.onpointerdown=e=>e.stopPropagation();toggle.setAttribute('aria-expanded',String(!n.collapsed));card.querySelector('header').prepend(toggle);
    card.append(el('div',state.project.nodes.filter(c=>c.group===n.id&&!c.hidden).length+' nodes · visual only','frameLabel'));
    if(!n.collapsed){const resize=el('div','◢','frameResize');resize.onpointerdown=e=>{if(e.button!==0)return;e.stopPropagation();move={type:'resize',id:n.id,x:e.clientX,y:e.clientY,width:n.width||650,height:n.height||420};resize.setPointerCapture(e.pointerId);};resize.onpointermove=e=>drag(e);resize.onpointerup=()=>{move=null;run('graph_edit',{node_id:n.id,group:n.group||null,width:n.width,height:n.height});};card.append(resize);}
    return card;
  }
  function exportCard(n){const card=cardFor(n),config=n.export_config||{},source=state.project.nodes.find(s=>s.id===config.source_id),folder=state.project.nodes.find(f=>f.id===config.folder_id);card.style.zIndex='100';
    const body=el('div',undefined,'body'),input=el('div',source?.name||'Connect a Blend file','exportSource'),socket=el('span',undefined,'port exportIn');socket.dataset.exportTarget=n.id;socket.title='Drop a Blend file contents socket here';input.prepend(socket);body.append(input);
    body.append(el('div',config.format+' · '+(config.scope==='COLLECTIONS'?config.collections.length+' collections':config.scene||'Choose scene'),'exportSummary'));
    const row=actions(button('Export',()=>startExport(n)),button('Settings',()=>{if(!inspectorOpen)inspectorToggle.click();pick(n.id);}));row.classList.add('exportTools');body.append(row);
    const output=el('div',folder?'Files → '+folder.name:'Files → choose folder','exportOutput'),port=el('span',undefined,'port exportOut');port.dataset.exportOutput=n.id;port.title='Drag exported files to a Folder or empty canvas';port.onpointerdown=e=>{if(e.button!==0||busy)return;e.preventDefault();e.stopPropagation();wire={export:n.id};status('Drop onto a Folder or empty canvas');};output.append(port);body.append(output);
    const last=(state.project.exports||[]).filter(r=>r.node_id===n.id).at(-1);if(last)body.append(el('div',`e${String(last.number).padStart(3,'0')} · ${last.status}`,'exportStatus'+(last.status==='Failed'?' warning':'')));
    card.append(body);return card;
  }
  function exportDetails(n){const pane=$('inspector'),config=JSON.parse(JSON.stringify(n.export_config)),drafts=config.options||{},files=state.project.nodes.filter(f=>f.type==='blend'&&!f.hidden),destinations=folders().filter(f=>f.value);
    pane.replaceChildren(section(n.name,muted('Export saved content. Your working Blend file stays unchanged.')));
    const form=el('form',undefined,'exportForm'),source=selectControl('Source Blend file',[{value:'',label:'Choose Blend file'},...files.map(f=>({value:f.id,label:f.name}))],config.source_id||''),scene=selectControl('Scene',[],''),format=selectControl('Export format',outputFormats,config.format),folder=selectControl('Output folder',[{value:'',label:'Choose output folder'},...destinations],config.folder_id||''),scope=selectControl('Export content',[{value:'SCENE',label:'Whole scene'},{value:'COLLECTIONS',label:'Selected collections'}],config.scope),timing=selectControl('Export timing',[{value:'FRAME',label:'Saved current frame'},{value:'ANIMATION',label:'Animation range'}],config.animation?'ANIMATION':'FRAME');
    const help=muted(formatHelp[format.value]),tree=el('div',undefined,'exportCollections'),chosen=new Set(config.collections),start=el('input'),end=el('input');start.type=end.type='number';start.step=end.step='1';start.min=end.min='-1048574';start.max=end.max='1048574';start.value=config.start??'';end.value=config.end??'';
    const range=el('div',undefined,'exportRange'),rangeInfo=muted(''),useScene=button('Use scene range',()=>{start.value=end.value='';updateTiming();});useScene.type='button';range.append(field('First frame',start),field('Last frame',end));
    const optionPanel=el('details',undefined,'exportOptions'),optionTitle=el('summary','Format options'),optionBody=el('div'),animationControls=[];optionPanel.open=exportOptionsOpen.get(n.id)||false;optionPanel.ontoggle=()=>exportOptionsOpen.set(n.id,optionPanel.open);optionPanel.append(optionTitle,optionBody);
    function paintOptions(){optionBody.replaceChildren();animationControls.length=0;const mode=format.value,preset=drafts[mode]||(drafts[mode]={}),schema=state.export_settings?.[mode]||[];let group='';
      for(const setting of schema){if(group!==setting.group){group=setting.group;optionBody.append(el('div',group,'exportOptionGroup'));}let control;
        const value=preset[setting.key]??setting.default;
        if(setting.type==='enum')control=selectControl(setting.label,setting.values,value);
        else{control=el('input');if(setting.type==='boolean'){control.type='checkbox';control.checked=value;}else{control.type='number';control.value=value;control.min=setting.min;control.max=setting.max;control.step=setting.type==='integer'?'1':'any';control.required=true;}}
        if(setting.help)control.title=setting.help;
        control.oninput=control.onchange=()=>{preset[setting.key]=setting.type==='boolean'?control.checked:['number','integer'].includes(setting.type)?Number(control.value):control.value;};
        optionBody.append(field(setting.label,control));if(setting.animation)animationControls.push(control);
      }
      const reset=button('Reset '+mode+' options',()=>{drafts[mode]={};paintOptions();visibility();});reset.type='button';optionBody.append(reset);
    }
    function updateTiming(){const saved=files.find(f=>f.id===source.value)?.scan?.scenes?.find(s=>s.name===scene.value),animation=timing.value==='ANIMATION';range.hidden=useScene.hidden=!animation;start.disabled=end.disabled=!animation;start.placeholder=saved?.start??'Scene';end.placeholder=saved?.end??'Scene';
      const first=start.value===''?saved?.start:Number(start.value),last=end.value===''?saved?.end:Number(end.value),invalid=animation&&Number.isFinite(first)&&Number.isFinite(last)&&last<first;
      end.setCustomValidity(invalid?'Last frame must not precede first frame.':'');rangeInfo.classList.toggle('warning',invalid);
      if(!saved)rangeInfo.textContent='Refresh the source to read saved timing.';
      else if(!animation)rangeInfo.textContent=saved.current_frame==null?'Refresh the source to read its saved current frame.':'Frame '+saved.current_frame+' · saved in Blender';
      else rangeInfo.textContent=invalid?'Last frame must not precede first frame.':`${first}–${last} · ${last-first+1} frames · ${Number(saved.fps||24).toFixed(2).replace(/\.00$/,'')} fps${start.value===''&&end.value===''?' · saved scene range':' · custom range'}`;
      for(const control of animationControls)control.disabled=!animation;
    }
    function content(){const file=files.find(f=>f.id===source.value),scenes=(file?.scan?.scenes||[]).filter(s=>!s.linked);scene.replaceChildren();for(const item of scenes){const o=el('option',item.name);o.value=item.name;scene.append(o);}scene.value=scenes.some(s=>s.name===config.scene)?config.scene:scenes[0]?.name||'';
      tree.replaceChildren();if(!file){tree.append(muted('Connect a Blend file to choose content.'));return;}
      if(!scenes.length)tree.append(muted('Save in Blender and refresh the source to read its scenes.'));
      if(!exportViews.has(n.id))exportViews.set(n.id,assetTreeView());
      const view=exportViews.get(n.id),search=el('input');search.type='search';search.placeholder='Find collection…';search.value=view.query;search.setAttribute('aria-label','Find export collection');
      const browser=el('div');tree.append(search,browser);const painter=createAssetBrowser(browser,file,savedContentAssets(file).filter(d=>d.kind==='collections'&&(!scenes.find(s=>s.name===scene.value)?.collections||scenes.find(s=>s.name===scene.value).collections.includes(d.name))),view,{allowedKinds:()=>new Set(['collections']),flags:d=>({checked:chosen.has(d.name)}),onChoose:(d,on)=>{if(on)chosen.add(d.name);else chosen.delete(d.name);painter.paint();}});search.oninput=()=>{view.query=search.value;painter.paint();};painter.paint();
    }
    function visibility(){tree.hidden=scope.value!=='COLLECTIONS';help.textContent=formatHelp[format.value];updateTiming();}
    source.onchange=()=>{config.scene='';chosen.clear();content();updateTiming();};scene.onchange=()=>{config.scene=scene.value;chosen.clear();content();updateTiming();};scope.onchange=timing.onchange=visibility;start.oninput=end.oninput=updateTiming;
    format.onchange=()=>{if(format.value==='ALEMBIC'&&!Object.hasOwn(drafts,'ALEMBIC'))timing.value='ANIMATION';paintOptions();visibility();};content();paintOptions();visibility();
    function values(){return {source_id:source.value||null,folder_id:folder.value||null,format:format.value,scene:scene.value,scope:scope.value,collections:[...chosen],animation:timing.value==='ANIMATION',start:start.value===''?null:Number(start.value),end:end.value===''?null:Number(end.value),options:drafts};}
    async function saveAndRun(exportNow){if(optionBody.querySelector(':invalid'))optionPanel.open=true;if(!form.reportValidity())return;const submitted=values(),before=new Set((state.jobs||[]).map(j=>j.id));const result=await run('export_config',{node_id:n.id,config:submitted});if(result&&!(result.jobs||[]).some(j=>!before.has(j.id)&&j.action==='export_config'&&j.node_id===n.id&&j.status==='Failed'&&j.args?.config&&JSON.stringify(j.args.config)===JSON.stringify(submitted)))if(exportNow)run('export_start',{node_id:n.id});}
    form.onsubmit=e=>{e.preventDefault();saveAndRun(false);};
    const save=button('Save settings',()=>saveAndRun(false)),execute=button('Save + Export',()=>saveAndRun(true));save.type=execute.type='button';
    form.append(field('Source',source),field('Scene',scene),field('Format',format),help,field('Content',scope),tree,field('Output folder',folder),field('Timing',timing),range,rangeInfo,useScene,optionPanel,muted('Each run creates a new e001, e002… directory. Blank frame limits use the saved scene range.'),actions(save,execute));pane.append(section('Export settings',form));
    if(n.last_error)pane.append(section('Operation failed',el('p',n.last_error.message,'warning'),button('Dismiss',()=>run('dismiss_error',{node_id:n.id}))));
    const versions=(state.project.exports||[]).filter(r=>r.node_id===n.id).slice().reverse();pane.append(section('Versions · '+versions.length,...versions.slice(0,15).map(r=>section('e'+String(r.number).padStart(3,'0')+' · '+r.status,el('p',r.output,'uxPath'),muted(r.settings.format+' · '+r.settings.scene+' · '+new Date(r.created).toLocaleString()),...(r.timing?[muted(r.timing.mode==='ANIMATION'?`${r.timing.start}–${r.timing.end} · ${r.timing.frames} frames · ${r.timing.fps} fps`:'Frame '+r.timing.start)]:[]),button('Open output',()=>run('export_open',{run_id:r.id})),...(r.error?[el('p',r.error,'warning')]:[])))));
    pane.append(appearance(n));
  }
  function startExport(n){const c=n.export_config;if(!c?.source_id||!c.folder_id||!c.scene){if(!inspectorOpen)inspectorToggle.click();pick(n.id);return status('Choose source, scene and output folder, then Save + Export.');}return run('export_start',{node_id:n.id});}
  PipelineUI.use('render','graph-only-nodes',2000,function(next){next();for(const n of visibleNodes().filter(n=>['frame','export'].includes(n.type)))$('nodes').append(n.type==='frame'?frameCard(n):exportCard(n));polishInterface();drawEdges();paintTasks();inspect();});
  PipelineUI.use('inspect','graph-only-details',1900,function(next){next();const n=state.project?.nodes.find(n=>n.id===selected);if(n?.type==='export')exportDetails(n);else if(n?.type==='frame'){
    const pane=$('inspector'),children=state.project.nodes.filter(c=>c.group===n.id&&!c.hidden);pane.replaceChildren(section(n.name,muted('Visual grouping only. This frame creates no directory and never moves files.')),section('Members · '+children.length,...children.map(c=>button(c.name,()=>focusNode(c))),button(n.collapsed?'Expand frame':'Collapse frame',()=>editGraph(n,{collapsed:!n.collapsed}))),appearance(n));}});
  function visibleId(id){const node=state.project.nodes.find(n=>n.id===id);return node?(frameAncestors(node).filter(f=>f.collapsed).at(-1)||node).id:null;}
  function endpoint(id,port,side){const node=state.project.nodes.find(n=>n.id===id&&!n.hidden);if(!node)return null;if(port)return point(port);const visible=frameAncestors(node).filter(f=>f.collapsed).at(-1)||node;return nodeAnchor(visible,side);}
  const previousEdges=drawEdges;drawEdges=function(){previousEdges();if(!state.project)return;for(const n of state.project.nodes.filter(n=>n.type==='export'&&!n.hidden&&!frameAncestors(n).some(f=>f.hidden))){const c=n.export_config;
    for(const [id,from,to,label] of [[c.source_id,document.querySelector(`[data-asset="${c.source_id}"]`),document.querySelector(`[data-export-target="${n.id}"]`),'content'],[c.folder_id,document.querySelector(`[data-export-output="${n.id}"]`),document.querySelector(`[data-folder="${c.folder_id}"]`),'files']]){if(!id||visibleId(id)===visibleId(n.id))continue;const a=endpoint(label==='content'?id:n.id,from,'out'),b=endpoint(label==='content'?n.id:id,to,'in');if(!a||!b)continue;const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.dataset.exportEdge=n.id;path.style.stroke=label==='content'?'#b49bc9':'#7bb59c';curve(path,a,b);const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=n.name+' · '+label+' · click for settings';path.append(title);path.onclick=e=>{e.stopPropagation();pick(n.id);};$('edges').append(path);}}};
  addList.append(button('Frame',()=>addFrame(placement(),selection.size>0)),button('Export',()=>addExport(placement(),selected)));
  window.pipelineExportDrop=function(sourceId,hit,preset){const target=hit?.closest('.node.export')?.dataset.id;if(!target)return false;const n=state.project.nodes.find(n=>n.id===target),source=state.project.nodes.find(n=>n.id===sourceId);if(!n||source?.type!=='blend')return false;
    const config={...n.export_config,source_id:sourceId};if(n.export_config.source_id!==sourceId){config.scene='';config.collections=[];config.scope='SCENE';}
    if(!config.scene)config.scene=(source.scan?.scenes||[]).find(s=>!s.linked)?.name||'';
    if(preset?.kind==='collections'){config.scope='COLLECTIONS';config.collections=[...new Set([...config.collections,preset.name])];}
    run('export_config',{node_id:n.id,config});return true;};
  const previousMove=$('workspace').onpointermove;$('workspace').onpointermove=e=>{if(!wire?.export)return previousMove(e);lastPoint=worldPoint(e.clientX,e.clientY);let preview=$('wirePreview');if(!preview){preview=document.createElementNS('http://www.w3.org/2000/svg','path');preview.id='wirePreview';preview.style.stroke='#7bb59c';preview.style.pointerEvents='none';$('edges').append(preview);}curve(preview,point(document.querySelector(`[data-export-output="${wire.export}"]`)),lastPoint);};
  document.addEventListener('pointerup',e=>{if(!wire?.export)return;e.stopImmediatePropagation();const n=state.project.nodes.find(n=>n.id===wire.export),hit=document.elementFromPoint(e.clientX,e.clientY),folder=hit?.closest('.node.folder')?.dataset.id;wire=null;$('wirePreview')?.remove();if(folder)run('export_config',{node_id:n.id,config:{...n.export_config,folder_id:folder}});else if(hit&&$('workspace').contains(hit)&&emptyCanvas({target:hit})){
    const p=worldPoint(e.clientX,e.clientY),group=activeGroup(p),projectId=state.project.id;
    modal('Create an export folder here?',[],async()=>{if(state.project?.id!==projectId)return;const before=new Set(state.project.nodes.map(n=>n.id)),result=await run('folder',{folder_id:group,...p,width:350,height:180});if(!result||result.project?.id!==projectId)return;const f=result.project.nodes.find(n=>n.type==='folder'&&!before.has(n.id));if(f)run('export_config',{node_id:n.id,config:{...n.export_config,folder_id:f.id}});});$('fields').append(muted('Creates a physical folder and connects this export output.'));$('submit').textContent='Create + connect';
  }else status('Export connection cancelled');},true);
  const archives=openArchivedFiles;openArchivedFiles=function(){archives();const records=state.project?.archived_graph_nodes||[];if(records.length)for(const p of $('fields').querySelectorAll('p'))if(p.textContent==='No archived files in this project.')p.remove();for(const r of [...records].reverse())$('fields').append(section(typeLabel(r.node.type)+' · '+r.node.name,button('Restore node',()=>{$('dialog').close();run('restore_graph_node',{archive_id:r.id});})));};
  for(const b of projectList.querySelectorAll('button'))if(b.textContent.trim()==='Archived files')b.onclick=openArchivedFiles;
  PipelineUI.graphNodes={cardFor,field,selectControl,appearance,activeGroup,endpoint,visibleId,removeNode,addFrame,addExport};
})();
