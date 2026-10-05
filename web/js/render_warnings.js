/* Image warnings need consent per submission and stay visible on its versions. */
(function(){
  const renderActions=new Set(['queue_render','queue_batch','queue_render_node','render_start','companion_render']);
  function warningList(warnings,onLocate){
    const box=el('div',undefined,'renderImageWarnings');
    for(const w of warnings){const row=el('div',undefined,'renderImageWarning');row.append(el('strong',w.name||'Image'),muted(w.source_name+' · '+(w.usage==='used'?'Used by saved nodes · ':w.usage==='unused'?'Unused in saved nodes · ':'')+w.reason),el('div',w.path,'uxPath'));if(onLocate&&w.can_locate!==false)row.append(button('Locate file…',()=>onLocate(w),'Copy a replacement into the project for rendering; working Blend files stay unchanged'));box.append(row);}
    return box;
  }
  PipelineUI.use('run','render-image-consent',2500,async function(next,action,args={}){
    if(!renderActions.has(action))return next(action,args);
    const before=new Set((state.jobs||[]).map(j=>j.id)),result=await next(action,args);
    const job=result?.jobs?.find(j=>!before.has(j.id)&&j.action===action&&j.error_code==='render_image_warnings');
    if(!job?.dependency_warnings?.length)return result;
    if(job.project_id!==state.project?.id)return;
    return new Promise(resolve=>{
      let accepted=false,locating=false;
      async function locate(w){
        if(locating||state.project?.id!==job.project_id)return;
        locating=true;$('submit').disabled=true;
        try{
          const chosen=await api('choose_system_path',{mode:'file',extension:'',initial:w.path});
          if(!chosen.path||!$('dialog').open||state.project?.id!==job.project_id)return;
          const before=new Set((state.jobs||[]).map(j=>j.id));
          const result=await run('locate_render_image',{source_id:w.source_id,path:w.path,replacement:chosen.path});
          if(!result||result.jobs?.some(j=>!before.has(j.id)&&j.action==='locate_render_image'&&j.status==='Failed'))return;
          if(state.project?.id!==job.project_id||!$('dialog').open)return;
          accepted=true;$('dialog').close();
          const retry={...args};delete retry.allow_image_warnings;delete retry.accepted_image_warnings;
          resolve(await run(action,retry));
        }catch(e){error(e);}finally{locating=false;if(!accepted&&$('dialog').open)$('submit').disabled=false;}
      }
      modal('Image dependency warnings',[],async()=>{
        accepted=true;
        if(state.project?.id!==job.project_id){error('The project changed. Submit a new render from this project.');resolve();return;}
        const retry={...args,allow_image_warnings:true};
        if(['queue_render','queue_batch','queue_render_node'].includes(action))retry.accepted_image_warnings=job.dependency_warnings;
        resolve(await run(action,retry));
      });
      $('dialog').addEventListener('close',()=>{if(!accepted){status('Render cancelled · image dependencies kept unchanged');resolve();}},{once:true});
      $('fields').append(muted('These images are missing or could not be safely collected. They are used by saved nodes or their use is uncertain. Available textures are collected automatically.'),warningList(job.dependency_warnings,locate),muted('Locate a replacement for rendering, or continue for this submission with these images unresolved. Warnings stay on the render version. Missing Blend libraries still block rendering.'));
      $('submit').textContent='Render anyway';
    });
  });
  const originalEntry=renderRunEntry;
  renderRunEntry=function(r){const entry=originalEntry(r);if(r.image_inputs?.length){const detail=el('details',undefined,'renderImageNotices');detail.append(el('summary','Collected textures · '+new Set(r.image_inputs.map(i=>i.original_path)).size));for(const image of new Map(r.image_inputs.map(i=>[i.original_path,i])).values())detail.append(muted((image.replacement?'Replacement · ':'')+image.name),el('div',image.original_path,'uxPath'));entry.prepend(detail);}if(r.image_notices?.length){const details=el('details',undefined,'renderImageNotices');details.append(el('summary','Unused image notices · '+r.image_notices.length),warningList(r.image_notices));entry.prepend(details);}if(r.dependency_warnings?.length){const details=el('details',undefined,'renderImageWarnings');details.append(el('summary','Rendered with image warnings · '+r.dependency_warnings.length),warningList(r.dependency_warnings));entry.prepend(details);}return entry;};
  const originalQueueEntry=queueEntry;
  queueEntry=function(q){const entry=originalQueueEntry(q);if(q.dependency_warnings?.length)entry.append(muted('Image warnings acknowledged · '+q.dependency_warnings.length));if(q.image_notices?.length)entry.append(muted('Unused missing images · '+q.image_notices.length));return entry;};
})();
