/* On-demand output workspace. Navigation is client-only; saved render paths stay intact. */
(function(){
  const model=PipelineUI.outputModel,workspace=el('dialog',undefined,'obWorkspace'),filesCache=new Map(),mediaCache=new Map(),expanded=new Set();
  workspace.id='outputBrowser';workspace.setAttribute('aria-label','Outputs browser');document.body.append(workspace);
  let current=null,viewTicket=0,frameTicket=0,mediaController=null,playTimer=null,playing=false,sidebarSignature='';
  const rows=id=>model.groups(state.project,id,state.folder_info),revision=r=>'r'+String(r.number||0).padStart(3,'0');
  function info(version){
    const run=version.run,first=version.sequences.find(s=>s.kind==='final');
    return first?.ranges?.length?sequenceFrames(first):version.frames?version.frames+' saved frames':version.hasOutputs?(run.image_count||version.images)+' images':'No saved images';
  }
  function iconButton(icon,label,click,cls='obFolderAction'){
    const b=button('',click,label);b.className=cls;b.dataset.menuIcon=icon;b.setAttribute('aria-label',label);b.append(blenderIcon(icon));return b;
  }
  function versionStatus(version){
    const text=version.partial||version.hasOutputs&&['Failed','Cancelled','Interrupted'].includes(version.run.status)?'Partial':version.run.status;
    const note=el('span',text,text==='Partial'?'obPartial':'');note.title=version.run.status+(version.expected?' · '+version.frames+'/'+version.expected+' frames saved':'');return note;
  }
  function versionRow(group,version,folderId){
    const row=el('div',undefined,'obVersionRow'),run=version.run;
    row.dataset.runId=run.id;
    row.classList.toggle('active',current?.folderId===folderId&&current.version?.run.id===run.id);
    const view=button(revision(run)+' · '+info(version)+' · '+run.status,()=>open(folderId,group.key,run.id),'View this saved version');view.dataset.menuIcon='none';
    row.append(view,
      iconButton('file_folder','Open folder for '+revision(run),()=>runAction(run)),
      iconButton('cancel','Delete version '+revision(run),()=>deleteRenderVersion(run),'obDelete'));
    return row;
  }
  function runAction(run){return window.PipelineUI.call('run','render_open',{run_id:run.id});}
  function resultRow(group,folderId,selectedKey){
    const row=el('div',undefined,'obResult'),latest=group.latest,main=button('',()=>open(folderId,group.key),'View latest saved output');
    row.classList.toggle('selected',group.key===selectedKey);row.dataset.setupKey=group.key;
    main.className='obResultMain';main.dataset.menuIcon='none';main.append(el('strong',group.name),el('span',group.source,'obSource'));
    const top=el('div',undefined,'obResultTop');top.append(main,iconButton('file_folder','Open latest output folder for '+group.name,()=>runAction(latest.run)));row.append(top);
    const meta=el('div',undefined,'obMeta');meta.append(el('span',revision(latest.run),'obRevision'),el('span',info(latest)),versionStatus(latest));
    if(group.attempt!==latest){const note=el('span','⚠','obPartial');note.title='Newest attempt '+revision(group.attempt.run)+' · '+group.attempt.run.status+' has no saved images. Showing the latest version with outputs.';meta.append(note);}
    row.append(meta);
    const others=group.versions.filter(v=>v!==latest);
    if(others.length){
      const disclosure=el('details',undefined,'obVersions'),key=[state.project.id,folderId,group.key].join(':');
      disclosure.append(el('summary','Other versions · '+others.length));disclosure.open=expanded.has(key);
      disclosure.ontoggle=()=>{if(disclosure.isConnected)disclosure.open?expanded.add(key):expanded.delete(key);};
      // Construct version actions only when their disclosure is opened.
      const populate=()=>{if(disclosure.children.length===1)for(const version of others)disclosure.append(versionRow(group,version,folderId));};
      disclosure.addEventListener('toggle',()=>{if(disclosure.open)populate();});if(disclosure.open)populate();row.append(disclosure);
    }
    return row;
  }
  function drawList(list,folderId,query='',selectedKey=null){
    list.replaceChildren();const groups=rows(folderId),filtered=groups.filter(g=>(g.name+' '+g.source).toLowerCase().includes(query.toLowerCase()));
    for(const group of filtered)list.append(resultRow(group,folderId,selectedKey));
    if(!filtered.length)list.append(el('div',groups.length?'No setups match this search.':'No saved render versions in this folder.','obEmpty'));
  }
  function folderDetails(pane,n){
    const box=el('div',undefined,'obSidebar'),head=el('div',undefined,'obSidebarHead'),groups=rows(n.id);
    head.append(el('span',groups.length+' setups · latest saved versions'),button('Browse outputs',()=>open(n.id)));box.append(head);
    const search=el('input');search.type='search';search.className='obSearch';search.placeholder='Find scene, layer or file…';search.setAttribute('aria-label','Find folder outputs');
    const list=el('div',undefined,'obSidebarList');search.oninput=()=>drawList(list,n.id,search.value);box.append(search,list);drawList(list,n.id);
    box.dataset.folderId=n.id;pane.append(box);sidebarSignature=model.signature(groups);
  }
  function stopPlayback(){playing=false;clearTimeout(playTimer);playTimer=null;if(current?.play){current.play.textContent='▶';current.play.setAttribute('aria-label','Play saved frames');current.play.setAttribute('aria-pressed','false');}}
  function clearMedia(){mediaController?.abort();mediaController=null;for(const entry of mediaCache.values())URL.revokeObjectURL(entry.url);mediaCache.clear();}
  function close(){
    stopPlayback();viewTicket++;frameTicket++;clearMedia();filesCache.clear();current=null;workspace.close();document.body.classList.remove('outputWorkspace');
  }
  function isOpen(){return workspace.open;}
  function getGroup(){return rows(current.folderId).find(g=>g.key===current.groupKey);}
  function mediaMessage(text,failure=false){
    if(!current)return;current.message.textContent=text;current.message.hidden=!text;current.message.classList.toggle('error',failure);
  }
  function paintViewer(){
    const viewer=el('div',undefined,'obViewer'),head=el('div',undefined,'obViewerHead'),title=el('strong','Select an output'),version=el('span','','obRevision'),passes=el('select');
    passes.setAttribute('aria-label','Output pass');passes.disabled=true;passes.onchange=()=>{stopPlayback();current.passId=passes.value;current.frameIndex=0;showFrame(0);};
    const fit=button('Fit',()=>{current.actualSize=!current.actualSize;current.stage.classList.toggle('actual',current.actualSize);fit.textContent=current.actualSize?'100%':'Fit';fit.setAttribute('aria-pressed',String(!current.actualSize));},'Toggle fit / actual image size');
    fit.setAttribute('aria-pressed','true');
    head.append(title,version,passes,fit,button('Open folder',()=>current.version&&runAction(current.version.run)),iconButton('cancel','Delete viewed version',()=>current.version&&deleteRenderVersion(current.version.run),'obDelete'));
    const stage=el('div',undefined,'obImageStage'),message=el('div','','obMediaMessage');message.setAttribute('role','status');message.hidden=true;stage.append(el('p','Select a setup to view its latest saved output.','obViewerHint'),message);
    const transport=el('div',undefined,'obTransport'),previous=button('‹',()=>{stopPlayback();showFrame(current.frameIndex-1);},'Previous saved frame · Left arrow'),play=button('▶',()=>togglePlayback(),'Play / pause saved frames · Space'),next=button('›',()=>{stopPlayback();showFrame(current.frameIndex+1);},'Next saved frame · Right arrow'),slider=el('input'),frameInfo=el('span','','obFrameInfo'),fps=el('select');
    slider.type='range';slider.min=0;slider.max=0;slider.value=0;slider.disabled=true;slider.setAttribute('aria-label','Saved frame');slider.title='Scrub saved frames · loads on release';
    slider.oninput=stopPlayback;slider.onchange=()=>{stopPlayback();showFrame(Number(slider.value));};
    fps.setAttribute('aria-label','Playback speed');for(const rate of [6,12,24]){const option=el('option',rate+' fps');option.value=rate;fps.append(option);}fps.value='12';
    for(const [b,label] of [[previous,'Previous saved frame'],[play,'Play saved frames'],[next,'Next saved frame']]){b.dataset.menuIcon='none';b.setAttribute('aria-label',label);}
    previous.disabled=true;next.disabled=true;play.disabled=true;
    transport.append(previous,play,next,slider,frameInfo,fps);viewer.append(head,stage,transport);
    Object.assign(current,{viewer,title,revision:version,passes,stage,message,slider,frameInfo,play,previous,next,fps,actualSize:false});return viewer;
  }
  function paintWorkspace(){
    const folder=state.project.nodes.find(n=>n.id===current.folderId),head=el('div',undefined,'obHead'),scope=el('select');scope.setAttribute('aria-label','Output folder');
    for(const n of state.project.nodes.filter(n=>n.type==='folder'&&!n.hidden)){const option=el('option',n.name);option.value=n.id;scope.append(option);}scope.value=current.folderId;scope.onchange=()=>open(scope.value);
    const back=button('Back to graph',close);back.className='obBack';head.append(el('strong','Outputs'),scope,button('Refresh',()=>refresh(),'Refresh saved outputs on disk'),button('Open folder',()=>run('launch',{node_id:folder.id})),back);
    const split=el('div',undefined,'obSplit'),pane=el('div',undefined,'obListPane'),search=el('input'),list=el('div',undefined,'obList');
    search.type='search';search.placeholder='Find scene, layer or file…';search.className='obSearch';search.setAttribute('aria-label','Find rendered setup');
    search.oninput=()=>{current.query=search.value;drawList(list,current.folderId,current.query,current.groupKey);};pane.append(search,list);split.append(pane,paintViewer());workspace.replaceChildren(head,split);current.list=list;
    drawList(list,current.folderId,'',current.groupKey);current.signature=model.signature(rows(current.folderId));
  }
  function open(folderId,key=null,runId=null){
    if(!state.project?.nodes.some(n=>n.id===folderId&&n.type==='folder'))return;
    const groups=rows(folderId),group=groups.find(g=>g.key===key)||groups[0];
    if(isOpen()&&current.folderId===folderId&&current.projectId===state.project.id){
      current.groupKey=group?.key||null;drawList(current.list,folderId,current.query,current.groupKey);
      if(group)loadVersion(group.versions.find(v=>v.run.id===runId)||group.latest);return;
    }
    if(renderManager.open)closeRenderManager();
    stopPlayback();viewTicket++;frameTicket++;clearMedia();
    pick(folderId);
    current={projectId:state.project.id,folderId,groupKey:group?.key||null,query:'',frameIndex:0,passId:null,version:null,files:null};
    paintWorkspace();document.body.classList.add('outputWorkspace');if(!workspace.open)workspace.show();
    if(group)loadVersion(group.versions.find(v=>v.run.id===runId)||group.latest);
  }
  async function loadVersion(version,keep={}){
    stopPlayback();mediaController?.abort();frameTicket++;const ticket=++viewTicket,owner=current,group=getGroup();current.version=version;current.files=null;
    current.title.textContent=(group?.name||version.run.name)+' · '+(group?.source||'');current.revision.textContent=revision(version.run)+' · '+versionStatus(version).textContent;current.revision.title=version.run.output;current.passes.disabled=true;current.slider.disabled=true;mediaMessage('Loading saved outputs…');
    for(const row of workspace.querySelectorAll('.obVersionRow'))row.classList.toggle('active',row.dataset.runId===version.run.id);
    current.stage.replaceChildren(el('p','Loading saved outputs…','obViewerHint'),current.message);current.frameInfo.textContent='';current.previous.disabled=true;current.next.disabled=true;current.play.disabled=true;
    const key=owner.projectId+':'+version.run.id,signature=JSON.stringify([version.run.status,version.run.image_count,version.images,version.frames,version.run.finished]);
    let entry=filesCache.get(key);
    if(!entry||entry.signature!==signature){
      if(filesCache.size>=12)filesCache.delete(filesCache.keys().next().value);
      entry={signature,promise:api('output_files',{project_id:owner.projectId,run_id:version.run.id})};filesCache.set(key,entry);
      entry.promise.catch(()=>{if(filesCache.get(key)===entry)filesCache.delete(key);});
    }
    try{
      const data=await entry.promise;if(current!==owner||ticket!==viewTicket)return;
      current.files=data;current.passes.replaceChildren();const categories=new Map();
      for(const sequence of data.sequences){
        const category=sequence.kind==='final'?'Final':'Compositor';if(!categories.has(category)){const group=el('optgroup');group.label=category;categories.set(category,group);current.passes.append(group);}
        const option=el('option',sequence.name+' · '+sequence.format);option.value=sequence.id;categories.get(category).append(option);
      }
      current.passId=data.sequences.find(s=>s.id===keep.passId)?.id||data.sequences[0]?.id||null;current.passes.value=current.passId||'';current.passes.disabled=!data.sequences.length;
      if(!data.sequences.length){current.stage.replaceChildren(el('p',data.missing?'This version folder is missing.':'This version has no saved images yet.','obViewerHint'),current.message);mediaMessage('');current.frameInfo.textContent='';current.play.disabled=true;return;}
      const sequence=data.sequences.find(s=>s.id===current.passId),index=sequence.frames.findIndex(f=>f.path===keep.framePath);await showFrame(index<0?0:index);
      if(data.truncated)mediaMessage('Showing the first 20,000 entries. Open folder for all outputs.');
    }catch(failure){if(current===owner&&ticket===viewTicket)mediaMessage(failure.message,true);}
  }
  function mediaKey(frame,version,owner){return [owner.projectId,version.run.id,frame.path,frame.modified].join(':');}
  async function fetchMedia(frame,version,owner,signal){
    const key=mediaKey(frame,version,owner);
    if(mediaCache.has(key)){const cached=mediaCache.get(key);mediaCache.delete(key);mediaCache.set(key,cached);return cached;}
    const response=await fetch('/output_image',{method:'POST',signal,headers:{'Content-Type':'application/json','X-Pipeline-Token':window.PIPELINE_TOKEN},body:JSON.stringify({project_id:owner.projectId,run_id:version.run.id,path:frame.path})});
    if(!response.ok){const data=await response.json();throw Error(data.error||'This preview is unavailable.');}
    const blob=await response.blob();if(signal.aborted)throw new DOMException('Preview cancelled','AbortError');
    const entry={url:URL.createObjectURL(blob),size:blob.size};mediaCache.set(key,entry);
    let bytes=[...mediaCache.values()].reduce((n,e)=>n+e.size,0);
    while(mediaCache.size>6||bytes>64*1024*1024&&mediaCache.size>1){const oldest=mediaCache.keys().next().value,item=mediaCache.get(oldest);bytes-=item.size;URL.revokeObjectURL(item.url);mediaCache.delete(oldest);}
    return entry;
  }
  async function showFrame(index){
    const owner=current,sequence=owner?.files?.sequences.find(s=>s.id===owner.passId);if(!sequence?.frames.length)return;
    index=Math.max(0,Math.min(sequence.frames.length-1,index));owner.frameIndex=index;owner.slider.max=sequence.frames.length-1;owner.slider.value=index;owner.slider.disabled=sequence.frames.length===1||sequence.video;
    owner.previous.disabled=sequence.video||index===0;owner.next.disabled=sequence.video||index===sequence.frames.length-1;owner.play.disabled=sequence.video||sequence.frames.length===1;owner.fps.hidden=sequence.video||sequence.frames.length===1;
    const frame=sequence.frames[index],ticket=++frameTicket;mediaController?.abort();const controller=new AbortController();mediaController=controller;
    owner.frameInfo.textContent=(frame.frame===null?'Image':'Frame '+frame.frame)+' · '+(index+1)+'/'+sequence.frames.length;owner.frameInfo.title=frame.name;mediaMessage(mediaCache.has(mediaKey(frame,owner.version,owner))?'':'Loading '+frame.name+'…');
    try{
      const entry=await fetchMedia(frame,owner.version,owner,controller.signal);if(current!==owner||ticket!==frameTicket)return;
      const media=el(sequence.video?'video':'img');media.setAttribute('aria-label',frame.name);
      if(sequence.video){media.controls=true;media.preload='metadata';media.src=entry.url;media.onerror=()=>mediaMessage('The browser cannot play this video format. Use Open folder.',true);}
      else {media.alt=frame.name;media.src=entry.url;await media.decode();}
      if(current!==owner||ticket!==frameTicket)return;owner.stage.replaceChildren(media,owner.message);mediaMessage('');
    }catch(failure){if(current===owner&&ticket===frameTicket&&failure.name!=='AbortError'){stopPlayback();mediaMessage(failure.message,true);}}
  }
  function togglePlayback(){
    if(playing){stopPlayback();return;}const sequence=current?.files?.sequences.find(s=>s.id===current.passId);if(!sequence||sequence.video||sequence.frames.length<2)return;
    playing=true;current.play.textContent='❚❚';current.play.setAttribute('aria-label','Pause saved frames');current.play.setAttribute('aria-pressed','true');const owner=current;
    const tick=async()=>{if(!playing||current!==owner)return;const started=performance.now();await showFrame((owner.frameIndex+1)%sequence.frames.length);if(playing&&current===owner)playTimer=setTimeout(tick,Math.max(0,1000/Number(owner.fps.value)-(performance.now()-started)));};
    playTimer=setTimeout(tick,1000/Number(owner.fps.value));
  }
  async function refresh(){
    if(!current)return;const owner=current,project=owner.projectId;filesCache.clear();clearMedia();
    try{const next=await api('state');if(current!==owner||next.project?.id!==project)return;state=keepLocalLayout(next);owner.signature=model.signature(rows(owner.folderId));paintTasks();drawList(owner.list,owner.folderId,owner.query,owner.groupKey);const group=getGroup();if(group)await loadVersion(group.versions.find(v=>v.run.id===owner.version?.run.id)||group.latest);}
    catch(failure){if(current===owner)mediaMessage(failure.message,true);}
  }
  function update(){
    if(workspace.open){
      if(state.project?.id!==current?.projectId||!state.project.nodes.some(n=>n.id===current.folderId)){close();return;}
      const groups=rows(current.folderId),signature=model.signature(groups);
      if(signature!==current.signature){
        current.signature=signature;drawList(current.list,current.folderId,current.query,current.groupKey);
        const group=groups.find(g=>g.key===current.groupKey),version=group?.versions.find(v=>v.run.id===current.version?.run.id);
        if(!group){
          current.groupKey=groups[0]?.key||null;
          if(groups[0])loadVersion(groups[0].latest);
          else {
            stopPlayback();viewTicket++;frameTicket++;clearMedia();current.files=null;current.version=null;
            current.title.textContent='No saved outputs';current.revision.textContent='';current.frameInfo.textContent='';current.passes.replaceChildren();current.passes.disabled=true;
            current.stage.replaceChildren(el('p','No saved render versions in this folder.','obViewerHint'),current.message);mediaMessage('');
            current.play.disabled=true;current.previous.disabled=true;current.next.disabled=true;current.slider.disabled=true;
          }
        }
        else if(!version)loadVersion(group.latest);
        else if(version.images!==current.version.images||version.run.status!==current.version.run.status){
          const sequence=current.files?.sequences.find(s=>s.id===current.passId);loadVersion(version,{passId:current.passId,framePath:sequence?.frames[current.frameIndex]?.path});
        }
      }
    }
    const box=$('inspector').querySelector('.obSidebar');
    if(box){const groups=rows(box.dataset.folderId),signature=model.signature(groups);if(signature!==sidebarSignature){sidebarSignature=signature;drawList(box.querySelector('.obSidebarList'),box.dataset.folderId,box.querySelector('input').value);}}
  }
  workspace.addEventListener('cancel',e=>{e.preventDefault();close();});
  document.addEventListener('keydown',e=>{
    if(!workspace.open||document.querySelector('dialog[open]:modal'))return;
    if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();close();}
    else if(e.target.matches('input,select,textarea'))return;
    else if(['ArrowLeft','ArrowRight','Home','End',' '].includes(e.key)){
      e.preventDefault();e.stopImmediatePropagation();if(e.key===' ')togglePlayback();else {stopPlayback();const sequence=current.files?.sequences.find(s=>s.id===current.passId);showFrame(e.key==='Home'?0:e.key==='End'?(sequence?.frames.length||1)-1:current.frameIndex+(e.key==='ArrowRight'?1:-1));}
    }
  },true);
  PipelineUI.use('paintTasks','output-browser',2400,function(next){next();update();});
  PipelineUI.outputs={open,close,isOpen,folderDetails};
})();
