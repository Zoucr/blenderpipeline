/* Dependency warnings describe saved observations; they never mutate Blender libraries. */
(function(){
  const expanded=new Set();
  const labels={image_dependency:'Image dependency warnings',image_notice:'Unused image notices',unsaved:'Unsaved changes',unsaved_upstream:'Unsaved source edits',saved_change:'Saved changes · refreshing',source_updated:'Source updated',missing:'File unavailable',missing_upstream:'Source unavailable',asset_missing:'Asset renamed / removed',missing_scene:'Scene renamed / removed',missing_layer:'View layer renamed / removed',missing_camera:'Camera unavailable'};
  const messages={image_dependency:'These images are missing or could not be collected. Locate a replacement or review them when rendering.',image_notice:'Missing images are disconnected or unreferenced in the saved file. Rendering continues and records these notices.',unsaved:'Save in Blender to include these edits.',unsaved_upstream:'Save this source in Blender before submitting work.',saved_change:'The saved file changed. Auto refresh will read its contents.',source_updated:'The source differs from this file’s last saved / refreshed dependency state. Review linked assets in Blender.',missing:'Locate the file or resolve its scan error.',missing_upstream:'Restore the missing source before submitting work.',asset_missing:'An expected linked asset is no longer in the source. Review its new contents and relink in Blender.',missing_scene:'Choose an existing saved scene in the operation settings.',missing_layer:'Choose an existing saved view layer in the Render setup.',missing_camera:'Save a scene camera in Blender, or choose an existing camera in the Render settings.'};
  function completed(n){const renders=(state.project?.renders||[]).filter(r=>r.status==='Complete'&&(n.type==='folder'?r.output.startsWith(n.path+'/'):n.type==='render'?r.operation_id===n.id:r.node_id===n.id)),exports=(state.project?.exports||[]).filter(r=>r.status==='Complete'&&(n.type==='folder'?r.output.startsWith(n.path+'/'):n.type==='export'?r.node_id===n.id:r.source_id===n.id)),latest=new Map();
    for(const [field,runs] of [['renders',renders],['exports',exports]])for(const run of runs){const key=field+':'+(field==='exports'?run.node_id:run.operation_id?run.operation_id+':'+run.target_id:run.node_id+':'+run.config.scene);latest.set(key,{field,run});}return [...latest.values()];
  }
  function outdated(n){return completed(n).filter(({field,run})=>state.health?.outputs?.[field]?.[run.id]?.outdated);}
  function unverified(n){return completed(n).filter(({field,run})=>state.health?.outputs?.[field]?.[run.id]?.unverified_inputs?.length);}
  function headline(n){const reasons=state.health?.nodes?.[n.id]?.reasons||[];for(const key of ['missing','asset_missing','missing_scene','missing_layer','missing_camera','missing_upstream','unsaved','unsaved_upstream','source_updated','saved_change','image_dependency','image_notice'])if(reasons.some(r=>r.kind===key))return labels[key];return outdated(n).length?'Outputs outdated':unverified(n).length?'Output freshness unknown':'';}
  function noticeInfo(n){
    const reasons=[...new Map((state.health?.nodes?.[n.id]?.reasons||[]).map(r=>[r.kind+':'+r.source_id,r])).values()],parts=[];
    for(const r of reasons.slice(0,6)){const source=state.project.nodes.find(s=>s.id===r.source_id),description=[r.message,messages[r.kind]].filter(Boolean);parts.push((labels[r.kind]||r.kind)+(source&&source.id!==n.id?' · '+source.name:'')+'\n'+[...new Set(description)].join('\n'));}
    if(reasons.length>6)parts.push('+'+(reasons.length-6)+' more notices');
    const old=outdated(n),unknown=unverified(n);
    if(old.length)parts.push('Outputs outdated · '+old.length+' setups\nChanged inputs: '+[...new Set(old.flatMap(({field,run})=>state.health.outputs[field][run.id].changed_inputs))].slice(0,6).join(', '));
    if(unknown.length)parts.push('Output freshness unknown · '+unknown.length+' setups');
    const danger=reasons.some(r=>['missing','missing_upstream','asset_missing','missing_scene','missing_layer','missing_camera'].includes(r.kind)),notice=reasons.length&&reasons.every(r=>r.kind==='image_notice')&&!old.length&&!unknown.length;
    return {label:headline(n),title:parts.join('\n\n')+'\n\nClick to inspect dependencies.',severity:danger?'danger':notice?'notice':'warning'};
  }
  const previousProblem=problem;problem=function(n){return n.last_error?'Operation failed':headline(n)||previousProblem(n);};
  function healthDetails(n){const h=state.health?.nodes?.[n.id]||{reasons:[],upstream:[],affected:[]},details=el('details',undefined,'healthDetails'),summary=el('summary',headline(n)||'Dependencies · current');summary.classList.toggle('warning',!!headline(n));details.append(summary);
    const key=state.project.id+':'+n.id;details.open=expanded.has(key);summary.onclick=()=>{details.open?expanded.delete(key):expanded.add(key);};details.ontoggle=()=>{if(details.isConnected)details.open?expanded.add(key):expanded.delete(key);};
    const reasons=[...new Map(h.reasons.map(r=>[r.kind+':'+r.source_id,r])).values()];
    for(const r of reasons){const file=state.project.nodes.find(f=>f.id===r.source_id),row=section(labels[r.kind]||r.kind,muted(messages[r.kind]||r.message||''));if(file)row.append(button(file.name,()=>focusNode(file)));if(r.message)row.append(muted(r.message));for(const asset of r.assets||[])row.append(muted(asset.kind+' · '+asset.name));details.append(row);}
    for(const {field,run} of outdated(n)){const h=state.health.outputs[field][run.id];details.append(section('Older saved version',muted(run.output),muted('Changed inputs: '+h.changed_inputs.join(', '))));}
    for(const {field,run} of unverified(n))details.append(section('Output freshness unknown',muted(run.output),muted('This older version did not record file signatures for: '+state.health.outputs[field][run.id].unverified_inputs.join(', '))));
    if(h.upstream.length)details.append(section('Sources',...h.upstream.map(id=>state.project.nodes.find(s=>s.id===id)).filter(Boolean).map(s=>button(s.name,()=>focusNode(s)))));
    const affected=new Set(h.affected),operations=state.project.nodes.filter(o=>o.type==='render'?o.render_plan.targets.some(t=>t.source_id===n.id||affected.has(t.source_id)):o.type==='export'&&(o.export_config.source_id===n.id||affected.has(o.export_config.source_id)));
    if(affected.size||operations.length)details.append(section('Used downstream',...state.project.nodes.filter(s=>affected.has(s.id)).concat(operations).map(s=>button(s.name,()=>focusNode(s)))));
    const changes=n.content_changes;if(changes&&changes.hash===n.scan?.hash&&(changes.added.length||changes.removed.length)){details.append(section('Latest saved content changes',...changes.removed.map(d=>muted('Removed / renamed: '+d.kind+' · '+d.name)),...changes.added.map(d=>muted('Added: '+d.kind+' · '+d.name))));}
    if(!reasons.length&&!outdated(n).length&&!unverified(n).length)details.append(muted('No pending saved-source changes detected. Blender edits must be saved before rendering or exporting.'));
    if(n.type==='blend')details.append(button('Refresh saved contents',()=>run('refresh',{node_id:n.id})));return details;
  }
  PipelineUI.use('inspect','dependency-impact',2200,function(next){next();const n=state.project?.nodes.find(n=>n.id===selected);if(n&&n.type!=='frame')$('inspector').append(healthDetails(n));});
  PipelineUI.use('paintTasks','dependency-badges',2200,function(next){next();for(const n of state.project?.nodes||[]){
    const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;const info=noticeInfo(n),footer=card.querySelector('.nodeStatus');if(footer)footer.hidden=!!info.label&&footer.textContent.includes(info.label);
    card.classList.toggle('hasDependencyNotice',!!info.label);let notice=card.querySelector('.dependencyBadge');
    if(!info.label){notice?.remove();continue;}
    if(!notice){notice=button('',()=>{if(!inspectorOpen)inspectorToggle.click();pick(n.id);const details=$('inspector').querySelector('.healthDetails');if(details){details.open=true;details.scrollIntoView({block:'nearest'});}});notice.className='dependencyBadge iconControl iconOnly';notice.dataset.menuIcon='warning_shield';notice.append(blenderIcon('warning_shield'));card.append(notice);}
    notice.setAttribute('aria-label',info.label+' · Open dependencies');notice.title=info.title;notice.dataset.severity=info.severity;
  }});
  const entry=renderRunEntry;renderRunEntry=function(r){const row=entry(r),health=state.health?.outputs?.renders?.[r.id];if(health?.outdated){const note=el('p','Older saved version · inputs changed','healthOutputNote');note.title=health.changed_inputs.join('\n');row.prepend(note);}if(health?.unverified_inputs?.length){const note=muted('Freshness unknown for: '+health.unverified_inputs.join(', '));row.append(note);}return row;};
  const versions=paintVersionList;paintVersionList=function(body){versions(body);const runs=scopeRuns().filter(r=>state.health?.outputs?.renders?.[r.id]?.outdated);if(runs.length)body.prepend(muted(runs.length+' versions use older saved inputs. Open Details to see which files changed.'));};
})();
