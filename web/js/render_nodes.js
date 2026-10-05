/* Render operations share the existing queue, settings editors and version workspace. */
(function(){
  const {cardFor,field,selectControl,appearance,activeGroup,endpoint,visibleId,removeNode}=PipelineUI.graphNodes;
  const targetPanels=new Set();
  const drafts=new Map();
  const planEditors=new Map();
  function connectedFiles(plan){return plan.source_ids||[...new Set(plan.targets.map(t=>t.source_id))];}
  function defaultSetup(file){
    const scenes=(file?.scan?.scenes||[]).filter(s=>!s.linked),scene=scenes.find(s=>s.name===file.scan?.active_scene)||scenes.find(s=>s.camera)||scenes[0];
    return {id:crypto.randomUUID(),source_id:file.id,scene:scene?.name||'',view_layer:scene?.active_view_layer||'',compositor:'BLENDER',label:'',mode:'ANIMATION',frame:null,camera:'',enabled:true,prefix:null,overrides:{}};
  }
  function setupLabel(target){return target.label||`${target.scene||'Choose scene'} · ${target.view_layer||'All enabled layers'}`;}
  function setupIssues(file,target,shared={}){
    const scenes=file?.scan?.scenes||[],scene=scenes.find(s=>s.name===target.scene&&!s.linked);
    if(!scene)return ['Scene unavailable. Refresh the file or choose another scene.'];
    const layers=scene.view_layers||[];
    if(target.view_layer&&!layers.some(l=>l.name===target.view_layer))return ['View layer unavailable. Refresh the file or choose another layer.'];
    if(!(scene.cameras||[]).includes(target.camera||scene.camera))return ['Camera unavailable. Choose a saved scene camera.'];
    let enabled=new Set(layers.filter(l=>l.enabled).map(l=>l.name)),compositor=scene.use_compositing!==false;
    for(const [key,value] of Object.entries({...target.overrides?.advanced,...shared.advanced})){
      const [scope,prop]=JSON.parse(key);
      if(scope==='render'&&prop==='use_compositing')compositor=value;
      if(scope.startsWith('layer:')&&prop==='use'){
        if(target.view_layer)return ['Use the View layers selector instead of advanced Use for Rendering overrides.'];
        value?enabled.add(scope.slice(6)):enabled.delete(scope.slice(6));
      }
    }
    if(target.view_layer)enabled=new Set([target.view_layer]);
    if(layers.length&&!enabled.size)return ['No enabled view layers. Choose a layer or enable one in Blender.'];
    if(target.compositor==='OFF'||!compositor)return [];
    return (scene.compositor_dependencies||[]).flatMap(d=>{
      const other=scenes.find(s=>s.name===d.scene),layer=other?.view_layers?.find(l=>l.name===d.view_layer);
      if(!layer||other.name===scene.name&&!enabled.has(d.view_layer)||other.name!==scene.name&&!layer.enabled)
        return [`Compositor needs ${d.scene} / ${d.view_layer}. Choose All enabled layers, adjust the compositor in Blender, or bypass it.`];
      return [];
    });
  }
  window.pipelineRenderIssues=(n,overrides={})=>setupIssues(n.source_id?state.project.nodes.find(f=>f.id===n.source_id):n,{...n.render_config,overrides:{advanced:n.render_config?.advanced||{}}},overrides);
  const previousTargets=outputTargets;
  outputTargets=function(folderId=null){const original=previousTargets(folderId),all=state.project?.nodes||[],root=all.find(n=>n.id===folderId);
    if(root?.type==='render')return (state.render_targets||[]).filter(t=>t.operation_id===root.id).map(t=>({...all.find(n=>n.id===t.source_id),...t}));
    return original.concat((state.render_targets||[]).filter(t=>t.operation_id).filter(t=>{const f=all.find(f=>f.id===t.render_config.folder_id);return f&&(!root||f.id===root.id||inFrame(f,root.id)||f.path.startsWith(root.path+'/'));}).map(t=>({...all.find(n=>n.id===t.source_id),...t})));
  };
  const previousCatalog=loadRenderSettings;
  loadRenderSettings=function(n){return previousCatalog(n.source_id?state.project.nodes.find(s=>s.id===n.source_id):n);};
  const previousConfigure=configureRender;
  configureRender=function(n,...args){if(n.operation_id){if(!inspectorOpen)inspectorToggle.click();targetPanels.add(n.target_id);pick(n.operation_id);if(renderManager.open)closeRenderManager();return;}return previousConfigure(n,...args);};
  const previousFocus=focusNode;focusNode=function(n){return previousFocus(n.source_id?state.project.nodes.find(s=>s.id===n.source_id):n);};
  const previousManager=openRenderManager;openRenderManager=function(scope=null,ids=null){if(ids)ids=outputTargets(scope).filter(t=>ids.includes(t.id)||ids.includes(t.source_id)).map(t=>t.id);return previousManager(scope,ids);};

  async function addRender(p,sourceIds=[],adopt=false){return run('render_node',{source_ids:sourceIds,group:activeGroup(p),...p,adopt_existing:adopt});}
  function detailsFor(n){if(!inspectorOpen)inspectorToggle.click();pick(n.id);}
  async function queueOperation(n){
    const key=state.project.id+':'+n.id;let editor=planEditors.get(key);
    if(drafts.has(key)){if(!editor?.root.isConnected){detailsFor(n);editor=planEditors.get(key);}if(!editor||!await editor.save())return;}
    const current=state.project?.nodes.find(o=>o.id===n.id);if(!current)return;
    if(!current.render_plan.folder_id||!current.render_plan.targets.some(t=>t.enabled)){detailsFor(current);return status('Connect files and an output Folder, then Render all.');}
    return run('queue_render_node',{node_id:n.id});
  }
  function renderCard(n){const card=cardFor(n),body=el('div',undefined,'body'),plan=n.render_plan,enabled=plan.targets.filter(t=>t.enabled),files=connectedFiles(plan),source=el('div',`${files.length} ${files.length===1?'file':'files'} · ${enabled.length}/${plan.targets.length} setups`,'renderNodeSource'),input=el('span',undefined,'port renderNodeIn');card.style.zIndex='100';input.dataset.renderNodeTarget=n.id;input.title='Connect a Blend file once, then add scene / view-layer setups';source.prepend(input);body.append(source);
    let previousFile;
    for(const t of plan.targets.slice(0,4)){
      if(previousFile!==t.source_id){body.append(el('div',state.project.nodes.find(f=>f.id===t.source_id)?.name||'Missing file','renderPreviewFile'));previousFile=t.source_id;}
      const file=state.project.nodes.find(f=>f.id===t.source_id),row=el('div',undefined,'renderSetupPreview'),check=el('input');check.type='checkbox';check.checked=t.enabled;check.setAttribute('aria-label','Include '+setupLabel(t)+' in Render all');check.onpointerdown=e=>e.stopPropagation();check.onclick=e=>e.stopPropagation();check.onchange=()=>run('render_node_config',{node_id:n.id,plan:{...plan,targets:plan.targets.map(x=>x.id===t.id?{...x,enabled:check.checked}:x)}});
      const label=button(setupLabel(t),()=>{targetPanels.add(t.id);detailsFor(n);},file?.name||'Missing file'),render=button('▶',()=>run('queue_render_node',{node_id:n.id,target_ids:[t.id]}),'Render this setup');render.classList.add('renderSetupAction');render.dataset.setupAction='render';render.setAttribute('aria-label','Render '+setupLabel(t));const marker=el('small','','renderPreviewState');marker.dataset.targetState=t.id;row.append(check,label,marker,render);body.append(row);
    }
    if(plan.targets.length>4)body.append(button('+'+(plan.targets.length-4)+' more setups',()=>detailsFor(n)));
    const controls=actions(button('Render all',()=>queueOperation(n),'Render enabled setups'),button('Setups',()=>detailsFor(n),'Setups and settings'));controls.classList.add('exportTools');body.append(controls);
    const destination=state.project.nodes.find(f=>f.id===plan.folder_id),output=el('div',destination?'Images → '+destination.name:'Images → choose Folder','exportOutput'),port=el('span',undefined,'port renderNodeOut');port.dataset.renderNodeOutput=n.id;port.title='Drag rendered images to a Folder or empty canvas';port.onpointerdown=e=>{if(e.button!==0||busy)return;e.preventDefault();e.stopPropagation();wire={renderOperation:n.id};status('Drop on an output Folder or empty canvas');};output.append(port);body.append(output);
    const batchSlot=el('div',undefined,'renderBatchSlot');batchSlot.dataset.batchNode=n.id;body.append(batchSlot);card.append(body);return card;
  }

  function renderPlanEditor(n,options={}){
    const key=state.project.id+':'+n.id,base=JSON.stringify(n.render_plan),draft=drafts.get(key),embedded=!!options.context;
    if(draft&&draft.base!==base)drafts.delete(key);
    const plan=draft?.base===base?draft.read():JSON.parse(base),files=state.project.nodes.filter(f=>f.type==='blend'&&!f.external);
    plan.source_ids=connectedFiles(plan);plan.overrides ||= {};
    const form=el('form',undefined,'renderNodeForm'),folder=selectControl('Render output Folder',[{value:'',label:'Connect output Folder'},...folders().filter(f=>f.value)],plan.folder_id||''),list=el('div',undefined,'renderTargetList'),editors=new Map(),notices=new Set();
    form.dataset.renderOperationId=n.id;form.classList.toggle('renderEmbeddedEditor',embedded);
    let nodeEditor,nodeAdvanced={read:()=>plan.overrides.advanced||{}};
    const saveButton=button('Save changes',()=>save()),pending=el('span','Unsaved changes','renderPending');
    saveButton.disabled=!drafts.has(key);pending.hidden=!drafts.has(key);
    function sync(){plan.targets=plan.targets.map(t=>editors.get(t.id)?.()||t);}
    function readDraft(){
      sync();const advanced=nodeAdvanced.read();
      return JSON.parse(JSON.stringify({folder_id:folder.value||null,source_ids:plan.source_ids,targets:plan.targets,overrides:{...nodeEditor.read(),...(Object.keys(advanced).length?{advanced}:{})}}));
    }
    form.oninput=form.onchange=()=>{plan.overrides={...nodeEditor.read(),...(Object.keys(nodeAdvanced.read()).length?{advanced:nodeAdvanced.read()}:{})};for(const update of notices)update();drafts.set(key,{base,read:readDraft});saveButton.disabled=false;pending.hidden=false;};
    async function commit(value,targetIds=null,after=null){
      const before=new Set((state.jobs||[]).map(j=>j.id));
      drafts.delete(key);
      const result=await run('render_node_config',{node_id:n.id,plan:value});
      const failed=!result||result.jobs?.some(j=>!before.has(j.id)&&j.action==='render_node_config'&&j.status==='Failed');
      if(failed){drafts.set(key,{base,read:()=>JSON.parse(JSON.stringify(value))});inspect();return null;}
      if(state.project?.id!==key.split(':')[0])return null;
      if(targetIds!==null)await run('queue_render_node',{node_id:n.id,...(targetIds==='all'?{}:{target_ids:targetIds}),overrides:options.queueOverrides?.()||{},label:options.versionLabel?.()||''});
      if(after&&state.project?.id===key.split(':')[0])after();
      return result;
    }
    function save(targetIds=null){
      const invalid=[...form.querySelectorAll('input,select')].find(e=>!e.checkValidity());
      if(invalid){for(let p=invalid.parentElement;p&&p!==form;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;invalid.reportValidity();return;}
      return commit(readDraft(),targetIds);
    }
    function removeSetup(target){
      const before=readDraft(),value={...before,targets:before.targets.filter(t=>t.id!==target.id)};
      commit(value,null,()=>{
        const undo=el('div',undefined,'renderSetupUndo');
        undo.append(muted('Setup removed. Rendered versions are kept.'),button('Undo',()=>commit(before)));
        const host=options.context==='workspace'?renderManager:$('inspector');host.querySelector(`[data-render-operation-id="${CSS.escape(n.id)}"]`)?.prepend(undo);
      });
    }
    function disconnect(id){
      const before=readDraft(),count=before.targets.filter(t=>t.source_id===id).length,file=files.find(f=>f.id===id);
      modal('Disconnect '+(file?.name||'missing file')+'?',[],()=>commit({...before,source_ids:before.source_ids.filter(i=>i!==id),targets:before.targets.filter(t=>t.source_id!==id)}));
      $('fields').append(muted('Removes the connection and '+count+' setups. The Blend file and rendered versions are kept.'));$('submit').textContent='Disconnect';
    }
    function addSetups(preferred){
      sync();
      if(!files.length)return status('Create or import a Blend file first.');
      const chosen=[];
      const initialFile=files.find(f=>f.id===preferred)||files.find(f=>plan.source_ids.includes(f.id))||files[0];
      modal('Add render setups',[{key:'file',label:'Blend file',type:'select',options:files.map(f=>({value:f.id,label:f.name})),value:initialFile.id}],()=>{
        if(!chosen.some(c=>c.check.checked))return status('No new setups selected.');
        const file=files.find(f=>f.id===$('field-file').value);
        if(!plan.source_ids.includes(file.id))plan.source_ids.push(file.id);
        for(const c of chosen.filter(c=>c.check.checked))plan.targets.push({...defaultSetup(file),scene:c.scene,view_layer:c.layer});
        paintTargets();form.oninput();
        save();
      });
      const host=el('div',undefined,'renderSetupPicker');
      const tools=actions(button('Select all enabled layers',()=>{for(const c of chosen)if(!c.check.disabled)c.check.checked=c.enabled;}),button('Clear',()=>{for(const c of chosen)if(!c.check.disabled)c.check.checked=false;}));
      $('fields').append(muted('Each checked combination becomes one setup. Existing combinations are marked; use Duplicate for a settings variant.'),tools,host);
      $('submit').textContent='Add selected setups';
      function draw(){
        chosen.length=0;host.replaceChildren();
        const file=files.find(f=>f.id===$('field-file').value),initial=defaultSetup(file),scenes=(file.scan?.scenes||[]).filter(s=>!s.linked);
        for(const scene of scenes){
          const group=el('section',undefined,'renderPickerScene');group.append(el('strong',scene.name));
          for(const layer of [{name:'',label:'All enabled view layers',enabled:false},...(scene.view_layers||[]).map(l=>({...l,label:l.name+(l.enabled?'':' · disabled in Blender')}))]){
            const exists=plan.targets.some(t=>t.source_id===file.id&&t.scene===scene.name&&(t.view_layer||'')===layer.name),row=el('label'),check=el('input');
            check.type='checkbox';check.disabled=exists;check.checked=!exists&&scene.name===initial.scene&&layer.name===initial.view_layer;
            check.setAttribute('aria-label','Add '+scene.name+' / '+(layer.name||'All enabled layers'));
            row.append(check,el('span',layer.label),...(exists?[muted('Already added')]:[]));group.append(row);
            chosen.push({scene:scene.name,layer:layer.name,enabled:layer.enabled,check});
          }
          host.append(group);
        }
        if(!scenes.length)host.append(muted('Refresh this file to read its saved scenes and view layers.'),button('Refresh file',async()=>{$('dialog').close();await run('refresh',{node_id:file.id});}));
      }
      $('field-file').onchange=draw;draw();
    }
    function paintTargets(){
      list.replaceChildren();editors.clear();notices.clear();
      for(const id of plan.source_ids){
        if(options.targetIds&&!plan.targets.some(t=>t.source_id===id&&options.targetIds.includes(t.id)))continue;
        const file=files.find(f=>f.id===id),group=renderPanel(file?.name||'Missing file','file:'+n.id+':'+id,true),head=el('div',undefined,'renderFileHeading');
        if(!embedded){head.append(el('strong',file?.name||'Missing file'),button('Add setup',()=>addSetups(id)),button('Disconnect',()=>disconnect(id)));group.append(head);}list.append(group);
        const targets=plan.targets.filter(t=>t.source_id===id&&(!options.targetIds||options.targetIds.includes(t.id)));
        for(const sceneName of [...new Set(targets.map(t=>t.scene))]){
          const sceneGroup=renderPanel(sceneName||'Choose scene','scene:'+n.id+':'+id+':'+sceneName,true);sceneGroup.classList.add('renderSceneGroup');group.append(sceneGroup);
          for(const target of targets.filter(t=>t.scene===sceneName)){
            const savedScenes=(file?.scan?.scenes||[]).filter(s=>!s.linked),box=el('details',undefined,'renderTargetSettings'),summary=el('summary'),check=el('input'),title=el('span',undefined,'renderSetupTitle'),label=el('strong',target.label||target.view_layer||'All enabled layers'),metrics=el('small',undefined,'renderSetupMetrics');title.append(label,metrics);
            box.dataset.setupId=target.id;check.type='checkbox';check.checked=options.selection?options.selection.has(target,n.id):target.enabled;check.setAttribute('aria-label',(options.selection?'Select ':'Include ')+setupLabel(target)+(options.selection?' for batch':' in Render all'));check.onclick=e=>e.stopPropagation();check.oninput=e=>{if(options.selection)e.stopPropagation();};check.onchange=e=>{if(options.selection){e.stopPropagation();options.selection.change(target,check.checked,n.id);}else target.enabled=check.checked;};
            const render=button('▶',()=>save([target.id]),'Save settings and render this setup'),remove=button('×',()=>removeSetup(target),'Remove setup; keep file and rendered versions');
            render.classList.add('renderSetupAction');render.dataset.setupAction='render';remove.classList.add('renderSetupAction');remove.dataset.setupAction='remove';
            render.setAttribute('aria-label','Render '+setupLabel(target));remove.setAttribute('aria-label','Remove '+setupLabel(target));
            summary.append(check,title,render,remove);box.open=targetPanels.has(target.id);box.ontoggle=()=>{if(box.isConnected)box.open?targetPanels.add(target.id):targetPanels.delete(target.id);};box.append(summary);sceneGroup.append(box);
            const scene=selectControl('Scene for '+setupLabel(target),[{value:'',label:'Choose scene'},...savedScenes.map(s=>({value:s.name,label:s.name})),...(target.scene&&!savedScenes.some(s=>s.name===target.scene)?[{value:target.scene,label:'Missing scene: '+target.scene}]:[])],target.scene);
            const layer=selectControl('View layers for '+setupLabel(target),[],target.view_layer||''),camera=selectControl('Camera for '+setupLabel(target),[],'');
            const compositor=selectControl('Compositor for '+setupLabel(target),[{value:'BLENDER',label:'Follow Blender file'},{value:'OFF',label:'Bypass compositor · raw layer'}],target.compositor||'BLENDER'),name=el('input'),prefix=el('input'),settings=el('div'),notice=el('div',undefined,'renderSetupNotice');
            const mode=selectControl('Render mode for '+setupLabel(target),[{value:'ANIMATION',label:'Animation / frame range'},{value:'STILL',label:'Single frame'}],target.mode||'ANIMATION'),frame=el('input');frame.type='number';frame.step='1';frame.min='-1048574';frame.max='1048574';frame.value=target.frame??'';frame.placeholder='Saved current frame';frame.disabled=mode.value!=='STILL';frame.setAttribute('aria-label','Still frame for '+setupLabel(target));
            name.value=target.label||'';name.placeholder='Automatic scene · view layer';name.maxLength=256;name.setAttribute('aria-label','Setup name for '+setupLabel(target));
            prefix.value=target.prefix||'';prefix.placeholder='Automatic date_scene_layer_';prefix.setAttribute('aria-label','Filename prefix for '+setupLabel(target));
            let common,advanced={read:()=>target.overrides.advanced||{}};
            function saved(){return savedScenes.find(s=>s.name===scene.value)||{};}
            function capture(){return {...target,label:name.value.trim(),scene:scene.value,view_layer:layer.value,camera:camera.value,compositor:compositor.value,mode:mode.value,frame:frame.value===''?null:Number(frame.value),prefix:prefix.value.trim()||null,overrides:{...common.read(),...(Object.keys(advanced.read()).length?{advanced:advanced.read()}:{})}};}
            function paintNotice(){
              const current=capture(),batch=options.queueOverrides?.()||{},issues=setupIssues(file,current,{...plan.overrides,...batch,advanced:{...plan.overrides.advanced,...batch.advanced}});notice.replaceChildren();
              for(const issue of [...new Set(issues)])notice.append(el('p',issue,'warning'));
              notice.title=current.compositor==='OFF'?'Bypasses compositor effects and File Output nodes. Multilayer EXR retains enabled passes.':'Uses the saved compositor scene and layer inputs.';
              const effective={...savedSetupSettings(saved(),current.view_layer),...current.overrides,...plan.overrides,...batch},scale=effective.percentage??100,start=current.mode==='STILL'?(current.frame??saved().current_frame):effective.start,end=current.mode==='STILL'?start:effective.end;
              metrics.textContent=Math.floor((effective.width||0)*scale/100)+' × '+Math.floor((effective.height||0)*scale/100)+' · '+(effective.samples??'Per-layer')+' sample'+(effective.samples===1?'':'s')+' · '+(current.mode==='STILL'?'Frame '+start:start+'–'+end);metrics.title='Effective render settings after shared and batch overrides';notice.hidden=!issues.length;
              if(target.output_subfolder)notice.title+='\nOutput: '+target.output_subfolder;
              render.disabled=issues.length>0;
              for(const [key,label] of renderSettings){const row=settings.querySelector(`[aria-label="${label}"]`)?.closest('.rmSetting');if(row){const inherited=common.read()[key]==null?'Saved in Blender':'Setup override';const hint=row.querySelector('.rmOrigin');hint.textContent=batch[key]!=null?'Batch':plan.overrides[key]!=null?'Shared':inherited==='Setup override'?'Setup':'Saved';hint.title=batch[key]!=null?'Batch override → '+batch[key]:plan.overrides[key]!=null?'Shared override → '+plan.overrides[key]:inherited;}}
            }
            function paintSettings(){
              const s=saved();layer.replaceChildren();
              for(const l of [{value:'',label:'All enabled view layers'},...(s.view_layers||[]).map(l=>({value:l.name,label:l.name+(l.enabled?'':' · enabled for this setup')})),...(target.view_layer&&!(s.view_layers||[]).some(l=>l.name===target.view_layer)?[{value:target.view_layer,label:'Missing layer: '+target.view_layer}]:[])]){
                const o=el('option',l.label);o.value=l.value;layer.append(o);
              }
              layer.value=target.view_layer||'';
              camera.replaceChildren();for(const c of [{value:'',label:'Saved active camera'},...(s.cameras||[]).map(c=>({value:c,label:c})),...(target.camera&&!(s.cameras||[]).includes(target.camera)?[{value:target.camera,label:'Missing camera: '+target.camera}]:[])]){
                const o=el('option',c.label);o.value=c.value;camera.append(o);
              }camera.value=target.camera||'';
              settings.replaceChildren();common=settingEditor(settings,target.overrides,savedSetupSettings(s,target.view_layer),()=>{paintNotice();form.oninput();},n.id+':'+target.id);advanced={read:()=>target.overrides.advanced||{}};
              advanced=renderSettingsCatalogue(settings,target.overrides.advanced,async()=>{const catalog=await loadRenderSettings(file);return catalog[scene.value]||[];},n.id+':'+target.id+':'+scene.value,()=>{paintNotice();form.oninput();});
              paintNotice();
            }
            function regroup(control){sync();form.oninput();paintTargets();form.querySelector(`[data-setup-id="${CSS.escape(target.id)}"] [aria-label^="${control}"]`)?.focus({preventScroll:true});}
            scene.onchange=()=>{target.overrides=capture().overrides;target.scene=scene.value;target.camera='';target.view_layer=saved().active_view_layer||'';paintSettings();regroup('Scene for ');};
            layer.onchange=()=>{target.overrides=capture().overrides;target.view_layer=layer.value;paintSettings();regroup('View layers for ');};
            camera.onchange=()=>{target.camera=camera.value;paintNotice();};compositor.onchange=()=>{target.compositor=compositor.value;paintNotice();};
            const stillField=field('Frame',frame);stillField.hidden=mode.value!=='STILL';
            mode.onchange=()=>{frame.disabled=mode.value!=='STILL';stillField.hidden=mode.value!=='STILL';};
            name.oninput=()=>{target.label=name.value;label.textContent=name.value||layer.value||'All enabled layers';};
            const identity=el('div',undefined,'renderSetupIdentity');identity.append(field('Scene',scene),field('View layer',layer),field('Mode',mode),stillField);
            const setupOptions=renderPanel('Setup options',n.id+':'+target.id+':options',false);setupOptions.append(field('Name',name),field('Camera',camera),field('Compositor',compositor),field('Filename',prefix));
            box.append(identity,notice,settings,setupOptions);
            paintSettings();editors.set(target.id,capture);notices.add(paintNotice);
            setupOptions.append(button('Duplicate setup',()=>{
              sync();const copy={...plan.targets.find(t=>t.id===target.id),id:crypto.randomUUID(),label:setupLabel(capture())+' copy'};
              delete copy.output_subfolder;plan.targets.push(copy);targetPanels.add(copy.id);paintTargets();form.oninput();
            }));
          }
        }
        if(!targets.length)group.append(muted('File connected. Add a setup to choose a scene and view layer.'));
      }
      if(!plan.source_ids.length)list.append(muted('Drag a Blend file output here, or use Add setup to choose a file.'));
    }
    const shared=renderPanel(embedded?'Shared settings · '+n.name:'Shared settings · all setups','shared:'+n.id,false);shared.classList.add('renderNodeOverrides');shared.title='Overrides from '+n.name+' apply to every setup in this render node, including other output folders. Unchecked values stay per setup.';
    nodeEditor=settingEditor(shared,plan.overrides,{},values=>{plan.overrides={...values,...(Object.keys(nodeAdvanced.read()).length?{advanced:nodeAdvanced.read()}:{})};},n.id+':shared');
    nodeAdvanced=renderSettingsCatalogue(shared,plan.overrides.advanced,async()=>{
      sync();const enabled=plan.targets.filter(t=>t.enabled),scenes=await Promise.all(enabled.map(async t=>{const file=files.find(f=>f.id===t.source_id);if(!file)return [];const catalog=await loadRenderSettings(file);return catalog[t.scene]||[];}));
      return scenes.length?scenes[0].filter(e=>scenes.every(items=>items.some(x=>x.key===e.key&&x.type===e.type&&x.editable===e.editable&&x.array===e.array))):[];
    },n.id+':shared',()=>form.oninput());
    paintTargets();
    form.onsubmit=e=>{e.preventDefault();save();};
    const setups=renderPanel('Render setups · '+plan.targets.length,'setups:'+n.id,true);setups.append(list,button('Add setup…',()=>addSetups()));
    const controls=actions(saveButton,pending);controls.classList.add('renderEditorActions');
    if(!embedded)controls.append(button('Render all',()=>save('all'),'Save pending changes and render enabled setups'));
    if(embedded)form.append(list,shared,controls);else form.append(field('Output Folder',folder),setups,shared,controls);
    const editor={root:form,read:readDraft,save,dirty:()=>drafts.has(key)};planEditors.set(key,editor);return editor;
  }
  window.pipelineRenderPlanEditor=renderPlanEditor;
  function renderDetails(n){
    const pane=$('inspector');pane.replaceChildren(el('div',n.name,'renderInspectorHeading'));pane.append(renderPlanEditor(n).root);
    const jobsPanel=renderPanel('Render activity','jobs:'+n.id,true);jobsPanel.dataset.renderJobsNode=n.id;pane.append(jobsPanel);paintRenderNodeActivity(jobsPanel,n.id);
    const records=(state.project.renders||[]).filter(r=>r.operation_id===n.id&&r.status!=='Deleted'),versions=renderPanel('Versions · '+records.length,'versions:'+n.id,false);
    versions.append(button('Open versions',()=>{openRenderManager(n.id);rm.tab='versions';paintRenderManager();}));
    for(const r of records.slice(-5).reverse()){const row=el('div',undefined,'renderVersionBrief');row.append(el('span',(r.config?.scene||'Scene')+' / '+(r.config?.view_layer||'All layers')),badge('r'+String(r.number).padStart(3,'0')),button('Details',()=>versionDetails(r)));versions.append(row);}pane.append(versions);
    if(n.last_error)pane.append(section('Operation failed',el('p',n.last_error.message,'warning'),button('Dismiss',()=>run('dismiss_error',{node_id:n.id}))));
    const organization=renderPanel('Organization','organization:'+n.id,false);organization.append(appearance(n));pane.append(organization);
  }
  function paintRenderNodeActivity(panel,nodeId){
    const groups=RenderOverview.batches(state.project,q=>q.operation_id===nodeId),current=groups.find(b=>b.active),body=panel.querySelector('.renderActivityBody')||el('div',undefined,'renderActivityBody');
    if(!body.parentElement)panel.append(body);const signature=JSON.stringify(current||null);if(body.dataset.signature===signature)return;body.dataset.signature=signature;body.replaceChildren();
    panel.querySelector('summary').textContent=current?'Render activity · '+current.saved+'/'+current.total+' frames':'Render activity';
    if(current)body.append(renderBatchCard(current,true),...current.jobs.map(j=>renderQueueRow(j.q)));else body.append(muted('No active batch'));
  }
  PipelineUI.use('paintTasks','render-batches',2110,function(next){next();
    for(const n of state.project?.nodes.filter(n=>n.type==='render')||[]){
      const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;
      const batches=RenderOverview.batches(state.project,q=>q.operation_id===n.id),current=batches.find(b=>b.active),latest=current||batches.at(-1),slot=card.querySelector('.renderBatchSlot'),signature=JSON.stringify(current||null);
      if(slot&&slot.dataset.signature!==signature){slot.dataset.signature=signature;slot.replaceChildren();if(current)slot.append(renderBatchCard(current,true));}
      for(const marker of card.querySelectorAll('[data-target-state]')){const job=latest?.jobs.find(j=>j.q.target_id===marker.dataset.targetState),status=job?.q.status||'';marker.textContent=status==='Complete'?'✓':status==='Rendering'||status==='Preparing'?'●':status==='Queued'?'◷':status==='Failed'?'!':'';marker.title=status;marker.classList.toggle('running',['Rendering','Preparing'].includes(status));}
    }
    for(const panel of $('inspector').querySelectorAll('[data-render-jobs-node]'))paintRenderNodeActivity(panel,panel.dataset.renderJobsNode);
  });
  PipelineUI.use('render','render-operation-nodes',2100,function(next){next();for(const n of visibleNodes().filter(n=>n.type==='render'))$('nodes').append(renderCard(n));polishInterface();drawEdges();paintTasks();inspect();});
  PipelineUI.use('inspect','render-operation-details',2100,function(next){next();const n=state.project?.nodes.find(n=>n.id===selected);if(n?.type==='render')renderDetails(n);});
  const previousEdges=drawEdges;drawEdges=function(){previousEdges();if(!state.project)return;for(const n of state.project.nodes.filter(n=>n.type==='render'&&!n.hidden&&!frameAncestors(n).some(f=>f.hidden))){const inputs=connectedFiles(n.render_plan);for(const [id,direction] of [...inputs.map(id=>[id,'input']),[n.render_plan.folder_id,'output']]){if(!id||visibleId(id)===visibleId(n.id))continue;const a=endpoint(direction==='input'?id:n.id,document.querySelector(direction==='input'?`[data-render="${id}"]`:`[data-render-node-output="${n.id}"]`),'out'),b=endpoint(direction==='input'?n.id:id,document.querySelector(direction==='input'?`[data-render-node-target="${n.id}"]`:`[data-folder="${id}"]`),'in');if(!a||!b)continue;const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.dataset.renderOperation=n.id;path.style.stroke='#73aaca';curve(path,a,b);const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=n.name+' · '+direction+' · click for settings';path.append(title);path.onclick=e=>{e.stopPropagation();detailsFor(n);};$('edges').append(path);}}};
  addList.append(button('Render',()=>addRender(placement(),[...selection].filter(id=>state.project.nodes.some(n=>n.id===id&&n.type==='blend'&&!n.external)))));
  window.pipelineRenderDrop=function(sourceId,hit){
    const target=hit?.closest('.node.render')?.dataset.id;if(!target)return false;
    const n=state.project.nodes.find(n=>n.id===target),source=state.project.nodes.find(n=>n.id===sourceId);
    if(!source||source.type!=='blend'||source.external)return false;
    const sources=connectedFiles(n.render_plan);
    if(sources.includes(sourceId)){status('File already connected. Use Add setup to choose more scenes / view layers.');return true;}
    run('render_node_config',{node_id:n.id,plan:{...n.render_plan,source_ids:[...sources,sourceId],targets:[...n.render_plan.targets,defaultSetup(source)]}});return true;
  };
  const exportDrop=window.pipelineExportDrop;window.pipelineExportDrop=function(source,hit,preset){return window.pipelineRenderDrop(source,hit)||exportDrop(source,hit,preset);};
  const previousCreateFolder=window.pipelineCreateRenderFolder;window.pipelineCreateRenderFolder=function(n,p){modal('Create Render node here?',[],()=>addRender(p,[n.id]));$('fields').append(muted('Connect this saved file to a Render node, then wire its Images output to a Folder.'),button('Connect directly to an output folder',()=>{$('dialog').close();previousCreateFolder(n,p);}));$('submit').textContent='Create + connect';};
  const previousMove=$('workspace').onpointermove;$('workspace').onpointermove=e=>{if(!wire?.renderOperation)return previousMove(e);lastPoint=worldPoint(e.clientX,e.clientY);let preview=$('wirePreview');if(!preview){preview=document.createElementNS('http://www.w3.org/2000/svg','path');preview.id='wirePreview';preview.style.stroke='#73aaca';preview.style.pointerEvents='none';$('edges').append(preview);}curve(preview,point(document.querySelector(`[data-render-node-output="${wire.renderOperation}"]`)),lastPoint);};
  document.addEventListener('pointerup',e=>{if(!wire?.renderOperation)return;e.stopImmediatePropagation();const n=state.project.nodes.find(n=>n.id===wire.renderOperation),hit=document.elementFromPoint(e.clientX,e.clientY),folder=hit?.closest('.node.folder')?.dataset.id;wire=null;$('wirePreview')?.remove();if(folder)run('render_node_config',{node_id:n.id,plan:{...n.render_plan,folder_id:folder}});else if(hit&&$('workspace').contains(hit)&&emptyCanvas({target:hit})){const p=worldPoint(e.clientX,e.clientY),group=activeGroup(p),project=state.project.id;modal('Create render output Folder here?',[],async()=>{const before=new Set(state.project.nodes.map(n=>n.id)),result=await run('folder',{folder_id:group,...p,width:350,height:200});if(result?.project?.id!==project)return;const f=result.project.nodes.find(f=>f.type==='folder'&&!before.has(f.id));if(f)run('render_node_config',{node_id:n.id,plan:{...n.render_plan,folder_id:f.id}});});$('fields').append(muted('Creates a regular Folder. Per-scene output directories and render versions are created when queued.'));$('submit').textContent='Create + connect';}else status('Output connection cancelled');},true);
})();
