/* Batch progress stays alive during preparation and transitions between setups. */
(function(root){
  const active=new Set(['Queued','Preparing','Rendering']);
  function frameCount(config={}){
    if(config.mode==='STILL')return 1;
    if(config.start==null||config.end==null)return 0;
    return Math.max(0,Math.floor((config.end-config.start)/(config.step||1))+1);
  }
  function batches(project,predicate=()=>true){
    const runs=new Map((project?.renders||[]).map(r=>[r.id,r])),groups=new Map();
    const queue=[...(project?.render_queue||[])];
    const sameSetup=(q,r)=>q.batch_id&&q.batch_id===r.batch_id&&q.node_id===r.node_id&&q.target_id===r.target_id;
    for(const run of runs.values())if(active.has(run.status)&&!queue.some(q=>q.run_id===run.id||!q.run_id&&active.has(q.status)&&sameSetup(q,run)))queue.push({...run,id:'direct:'+run.id,run_id:run.id,effective_settings:run.config});
    for(const q of queue.filter(predicate)){
      const key=q.batch_id||q.id;if(!groups.has(key))groups.set(key,{id:key,jobs:[],created:q.created,label:q.label});
      const run=runs.get(q.run_id)||(!q.run_id&&[...runs.values()].find(r=>active.has(r.status)&&sameSetup(q,r))),config=run?.config||q.effective_settings||q.settings||{},total=frameCount(config),saved=Math.min(total,run?.written_frames?.length||(q.status==='Complete'?total:0));
      groups.get(key).jobs.push({q,run,config,total,saved});
    }
    return [...groups.values()].map(batch=>{
      const jobs=batch.jobs,done=jobs.filter(j=>j.q.status==='Complete').length,failed=jobs.filter(j=>['Failed','Interrupted'].includes(j.q.status)).length,cancelled=jobs.filter(j=>j.q.status==='Cancelled').length,
        current=jobs.find(j=>['Preparing','Rendering'].includes(j.q.status))||jobs.find(j=>j.q.status==='Queued'),total=jobs.reduce((n,j)=>n+j.total,0),saved=jobs.reduce((n,j)=>n+j.saved,0);
      return {...batch,active:!!current,current,done,failed,cancelled,total,saved,progress:total?Math.floor(100*saved/total):0,status:current?'Rendering':failed?'Failed':cancelled?'Cancelled':'Complete'};
    });
  }
  function rangeLabel(ranges=[],step=1){return ranges.slice(0,3).map(([a,b])=>a===b?String(a):a+'–'+b).join(', ')+(ranges.length>3?' …':'')+(step>1?' · step '+step:'');}
  function latestSequences(info={}){
    const groups=new Map();
    for(const s of info.sequences||[]){
      if(s.kind!=='final')continue;
      const key=s.operation_id&&s.target_id?JSON.stringify([s.operation_id,s.target_id]):s.scene?[s.node_id||'',s.directory.replace(/(^|\/)[^/]+_r\d+$/,''),s.scene,s.view_layer].join(':'):s.directory+':'+s.prefix;
      const previous=groups.get(key);if(!previous||(s.version||0)>(previous.version||0))groups.set(key,s);
    }
    return [...groups.values()];
  }
  function sceneSummaries(info={}){
    const groups=new Map();
    for(const sequence of latestSequences(info)){
      const key=[sequence.node_id||sequence.directory.split('/')[0],sequence.scene||sequence.prefix].join(':');
      if(!groups.has(key))groups.set(key,[]);groups.get(key).push(sequence);
    }
    return [...groups.values()].map(sequences=>{
      const first=sequences[0],same=sequences.every(s=>JSON.stringify(s.ranges)===JSON.stringify(first.ranges)&&s.step===first.step&&!!s.videos===!!first.videos);
      return {name:first.scene||first.prefix.replace(/_$/,''),sequences,layers:new Set(sequences.map(s=>s.view_layer).filter(Boolean)).size,
        images:sequences.reduce((n,s)=>n+s.images,0),videos:sequences.reduce((n,s)=>n+(s.videos||0),0),same,
        partial:sequences.some(s=>s.images>0&&s.expected_frames&&s.frame_count<s.expected_frames)};
    });
  }
  const api={batches,frameCount,rangeLabel,latestSequences,sceneSummaries,active};
  if(typeof module==='object'&&module.exports){module.exports=api;return;}
  root.RenderOverview=api;
})(typeof window==='object'?window:globalThis);

const renderPanelState=new Map();
function renderPanel(title,key,open=false){
  const box=el('details',undefined,'renderPanel'),summary=el('summary',title);box.append(summary);
  const fullKey=(state.project?.id||'')+':'+key;box.open=renderPanelState.get(fullKey)??open;
  box.ontoggle=()=>{if(box.isConnected)renderPanelState.set(fullKey,box.open);};return box;
}
function renderBatchCard(batch,compact=false){
  const box=el('div',undefined,'renderBatch'+(compact?' compact':'')),heading=el('div',undefined,'renderBatchHeading'),progress=el('progress');
  heading.append(el('strong',batch.active?'Rendering':batch.status),el('span',batch.saved+' / '+batch.total+' frames','renderBatchCount'));
  progress.max=100;progress.value=batch.progress;progress.setAttribute('aria-label','Batch frames saved');
  const current=batch.current,phase=current?(current.run?.phase||(current.q.status==='Queued'?'Starting next setup':'Preparing')):'Finished';
  const detail=current?(current.config.scene||current.q.name)+' / '+(current.config.view_layer||'All layers')+' · '+phase:'';
  box.append(heading,progress,el('div',batch.done+' / '+batch.jobs.length+' setups complete'+(batch.failed?' · '+batch.failed+' failed':'')+(batch.cancelled?' · '+batch.cancelled+' cancelled':''),'renderBatchMeta'));
  if(detail){const line=el('div',detail,'renderBatchCurrent');line.title=detail;box.append(line);}
  box.classList.toggle('running',batch.active);return box;
}
function renderQueueRow(q){
  const run=state.project.renders?.find(r=>r.id===q.run_id),config=run?.config||q.effective_settings||q.settings||{},box=renderPanel('','job:'+q.id,false),summary=box.querySelector('summary'),title=el('span',undefined,'renderQueueTitle'),meta=el('small'),total=RenderOverview.frameCount(config),saved=run?.written_frames?.length||(q.status==='Complete'?total:0);
  title.append(el('strong',config.setup_label||[config.scene,config.view_layer||'All layers'].filter(Boolean).join(' / ')||q.name));
  const file=state.project.nodes.find(n=>n.id===q.node_id),scene=file?.scan?.scenes?.find(s=>s.name===config.scene)||{},percentage=config.percentage??scene.percentage??100,width=config.width??scene.width,height=config.height??scene.height;
  const sampling=savedSetupSettings(scene,config.view_layer),samples=config.samples??run?.actual_settings?.layer_samples?.[config.view_layer]??sampling.samples;
  meta.textContent=[file?.name||q.name,config.mode==='STILL'?'Frame '+config.start:`${config.start??'?'}–${config.end??'?'}${config.step>1?' · step '+config.step:''}`,width&&height?Math.floor(width*percentage/100)+' × '+Math.floor(height*percentage/100):'',samples!=null?samples+' sample'+(samples===1?'':'s'):sampling.per_layer_samples?'Samples per layer':''].filter(Boolean).join(' · ');
  title.append(meta);summary.append(title,badge(q.status,q.status==='Complete'?'good':['Failed','Interrupted'].includes(q.status)?'danger':''),el('span',saved+' / '+total,'renderQueueCount'));
  if(RenderOverview.active.has(q.status)){const cancel=button('×',()=>window.pipelineCancelRenderQueue(q),'Cancel this setup');cancel.setAttribute('aria-label','Cancel '+q.name);summary.append(cancel);}
  else if(['Failed','Cancelled','Interrupted'].includes(q.status))summary.append(button('↻',()=>runRetry(q),'Retry this setup'));
  box.classList.add('renderQueueRow');box.classList.toggle('running',['Rendering','Preparing'].includes(q.status));
  if(run&&RenderOverview.active.has(run.status)){const p=el('progress');p.max=total||1;p.value=saved;box.append(p);}
  if(run)box.append(renderRunEntry(run));else if(q.error)box.append(el('p',q.error,'warning'));
  return box;
}
if(typeof window==='object')window.pipelineCancelRenderQueue=q=>q.id.startsWith('direct:')?run('render_cancel',{run_id:q.run_id}):run('cancel_queue',{queue_id:q.id});

if(typeof window==='object')PipelineUI.use('inspect','render-scroll-position',2600,function(next){
  const pane=$('inspector'),id=selected,same=pane.dataset.renderOwner===id,scroll=pane.scrollTop,active=document.activeElement,
    focused=same&&pane.contains(active)&&active.matches('input,select'),label=focused?active.getAttribute('aria-label'):null,
    target=focused?active.closest('[data-setup-id]')?.dataset.setupId:null,owner=focused?active.closest('[data-render-operation-id]')?.dataset.renderOperationId:null,shared=focused&&!!active.closest('.renderNodeOverrides');
  next();pane.dataset.renderOwner=id||'';if(same)pane.scrollTop=scroll;
  if(label){const editor=owner?pane.querySelector(`[data-render-operation-id="${CSS.escape(owner)}"]`):pane,scope=target?editor?.querySelector(`[data-setup-id="${CSS.escape(target)}"]`):shared?editor?.querySelector('.renderNodeOverrides'):editor,control=scope?.querySelector(`[aria-label="${CSS.escape(label)}"]`);control?.focus({preventScroll:true});}
});
if(typeof window==='object')PipelineUI.use('paintTasks','folder-batch-progress',2120,function(next){next();
  for(const panel of $('inspector').querySelectorAll('[data-render-folder-jobs]')){const folder=state.project.nodes.find(n=>n.id===panel.dataset.renderFolderJobs);if(!folder)continue;const batches=RenderOverview.batches(state.project,q=>queueInFolder(q,folder)).filter(b=>b.active),signature=JSON.stringify(batches);if(panel.dataset.signature===signature)continue;panel.dataset.signature=signature;for(const child of [...panel.children])if(child.tagName!=='SUMMARY')child.remove();for(const batch of batches)panel.append(renderBatchCard(batch,true),...batch.jobs.map(j=>renderQueueRow(j.q)));if(!batches.length)panel.append(muted('No active batch'));}
});
