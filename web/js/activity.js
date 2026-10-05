/* Visible, nonblocking feedback. Blender file operations report no real percentage. */
(function(root){
  const labels={export_start:'Exporting saved content',export_node:'Creating export node',frame:'Creating frame',link_batch:'Linking assets',link:'Updating collection link',link_data:'Linking datablock',prepare_materials:'Preparing material slots',refresh:'Reading saved files',blend:'Creating Blender file',import:'Importing Blender file',duplicate:'Duplicating node',paste_nodes:'Copying saved files',label:'Renaming file',node_colors:'Changing colors',snapshot:'Saving snapshot',backup:'Backing up project',localize:'Collecting dependencies',load:'Opening project',create:'Creating project',render_start:'Preparing render'};
  Object.assign(labels,{render_node:'Creating render node',queue_render_node:'Preparing render batch',locate_render_image:'Copying texture replacement'});
  Object.assign(labels,{render_worker:'Rendering',render_inputs:'Preparing render inputs'});
  const quiet=new Set(['graph_edit','node_colors','layout','project_view','snapshot_note','render_config','render_node_config','export_config','ui_preferences','settings']);
  function jobs(server,pending,now=Date.now()){
    const combined=new Map((server||[]).map(job=>[job.id,job]));
    for(const [id,local] of pending||[])if(!combined.has(id))combined.set(id,{id,...local,node_id:local.args?.node_id||local.args?.target_id,status:'Queued',created:local.created||new Date(now).toISOString()});
    return [...combined.values()].filter(job=>['Queued','Running'].includes(job.status)&&!quiet.has(job.action)).map(job=>({...job,label:job.label||labels[job.action]||'Working',seconds:Math.max(0,Math.floor((now-Date.parse(job.created||new Date(now).toISOString()))/1000))}));
  }
  function elapsed(seconds){return seconds<60?seconds+'s':Math.floor(seconds/60)+'m '+seconds%60+'s';}
  function renderJobs(project){
    if(typeof RenderOverview!=='undefined')return RenderOverview.batches(project).filter(b=>b.active).map(b=>{
      const ids=new Set();for(const {q,config} of b.jobs){[q.node_id,q.operation_id,config.folder_id].filter(Boolean).forEach(id=>ids.add(id));}
      for(const id of [...ids]){let node=project.nodes.find(n=>n.id===id),seen=new Set();while(node?.group&&!seen.has(node.group)){seen.add(node.group);ids.add(node.group);node=project.nodes.find(n=>n.id===node.group);}}
      return {id:'render-batch:'+b.id,action:'render_worker',status:'Running',created:b.created,node_id:b.current.q.operation_id||b.current.q.node_id,args:{node_ids:[...ids]},label:'Rendering · '+b.saved+'/'+b.total+' frames',renderDetail:(b.current.run?.phase||'Starting next setup')+' · '+(b.current.config.scene||b.current.q.name)+' / '+(b.current.config.view_layer||'All layers')+' · '+b.done+'/'+b.jobs.length+' setups complete'};
    });
    return (project?.renders||[]).filter(r=>['Preparing','Rendering'].includes(r.status)).map(r=>({id:'render:'+r.id,action:'render_worker',status:'Running',created:r.started||r.created,node_id:r.operation_id||r.node_id,args:{node_ids:[r.node_id,r.operation_id].filter(Boolean)},renderDetail:[r.name,r.phase,r.current_frame!=null?'frame '+r.current_frame:'',r.render_device?.effective==='GPU'?'GPU · '+r.render_device.backend:r.render_device?.effective==='CPU'?'CPU':''].filter(Boolean).join(' · ')}));
  }
  if(typeof module==='object'&&module.exports){module.exports={jobs,elapsed,renderJobs};return;}
  $('taskMessage').dataset.activityOwner='true';
  let previous=new Set(),finished=null;
  PipelineUI.use('paintTasks','visible-activity',1800,function(next){
    next();const active=jobs([...(state.jobs||[]),...renderJobs(state.project)],pendingJobs),ids=new Set(active.map(job=>job.id)),banner=$('taskMessage');
    if(previous.size&&!active.length&&[...previous].some(id=>(state.jobs||[]).some(job=>job.id===id&&job.status==='Complete')))finished={until:Date.now()+2500};
    previous=ids;
    const showDone=!active.length&&finished&&Date.now()<finished.until;
    banner.hidden=!active.length&&!showDone;banner.classList.toggle('activityDone',!!showDone);
    const job=active.find(job=>job.status==='Running')||active[0];
    const destination=job&&state.project?.nodes.find(node=>node.id===job.node_id);
    const label=job?(job.status==='Queued'?'Queued · ':'')+job.label+(active.length>1?' · '+(active.length-1)+' waiting':''):showDone?'Operation completed':'';
    const detail=job?job.renderDetail||(destination?.name||state.project?.name||'Local workspace')+(job.seconds>=90?' · Large files can take a while.':''):'';
    if(banner.dataset.label!==label||banner.dataset.detail!==detail){
      banner.dataset.label=label;banner.dataset.detail=detail;banner.replaceChildren();
      const icon=el('span',showDone?'✓':undefined,showDone?'activityCheck':'activitySpinner'),text=el('div',undefined,'activityText'),title=el('strong',label);
      title.setAttribute('role','status');title.setAttribute('aria-live','polite');text.append(title,el('small',detail));banner.append(icon,text,el('span',undefined,'activityTime'));
    }
    const time=banner.querySelector('.activityTime');if(time)time.textContent=job?elapsed(job.seconds):'';
    let changed=false;
    for(const node of state.project?.nodes||[]){
      const card=document.querySelector(`[data-id="${node.id}"]`);if(!card)continue;
      const operation=active.find(job=>job.node_id===node.id||job.args?.source_id===node.id||job.args?.node_ids?.includes(node.id));
      card.classList.toggle('activityActive',!!operation);card.setAttribute('aria-busy',String(!!operation));
      let strip=card.querySelector('.nodeActivity');
      if(operation){
        if(!strip){strip=el('div',undefined,'nodeActivity');strip.append(el('span',undefined,'activitySpinner'),el('span',undefined,'activityLabel'),el('span',undefined,'activityTime'));card.querySelector('header').after(strip);changed=true;}
        strip.querySelector('.activityLabel').textContent=operation.args?.source_id===node.id&&operation.action.startsWith('link')?'Link source · '+operation.label:operation.label+(operation.status==='Queued'?' · queued':'…');
        strip.querySelector('.activityTime').textContent=elapsed(operation.seconds);strip.title=operation.renderDetail||'Blender is processing the saved file. You can continue navigating the graph.';
      }else if(strip){strip.remove();changed=true;}
    }
    if(changed)drawEdges();
  });
})(typeof window==='object'?window:globalThis);
