/* Pure output grouping: stable setup identity, latest saved version and folder scope. */
(function(root){
  function scopedFolders(project,folderId){
    const nodes=project?.nodes||[],folder=nodes.find(n=>n.id===folderId&&n.type==='folder');
    if(!folder)return [];
    const byId=new Map(nodes.map(n=>[n.id,n]));
    return nodes.filter(n=>{
      if(n.type!=='folder')return false;
      if(n.id===folderId||n.path.startsWith(folder.path+'/'))return true;
      let current=n;const seen=new Set();
      while(current.group&&!seen.has(current.id)){seen.add(current.id);current=byId.get(current.group);if(!current)break;if(current.id===folderId)return true;}
      return false;
    });
  }
  function setupKey(run){
    return JSON.stringify(run.operation_id&&run.target_id?['operation',run.operation_id,run.target_id]:['file',run.node_id,run.config?.scene||'',run.config?.view_layer||'']);
  }
  function groups(project,folderId,folderInfo={}){
    const folders=scopedFolders(project,folderId),ids=new Set(folders.map(n=>n.id)),sequences=new Map(),seen=new Set();
    for(const folder of folders)for(const sequence of folderInfo[folder.id]?.sequences||[]){
      const key=folder.path+'/'+sequence.sample;
      if(!sequence.run_id||seen.has(key))continue;seen.add(key);
      if(!sequences.has(sequence.run_id))sequences.set(sequence.run_id,[]);
      sequences.get(sequence.run_id).push(sequence);
    }
    const result=new Map(),nodes=new Map((project?.nodes||[]).map(n=>[n.id,n]));
    for(const run of project?.renders||[]){
      if(run.status==='Deleted'||!folders.some(f=>run.output.startsWith(f.path+'/'))&&!ids.has(run.config?.folder_id))continue;
      const key=setupKey(run),config=run.config||{};
      if(!result.has(key))result.set(key,{key,name:config.setup_label||[config.scene||run.name||'Render',config.view_layer||'All enabled layers'].join(' / '),source:nodes.get(run.node_id)?.name||run.name||'File',versions:[]});
      const media=sequences.get(run.id)||[],final=media.filter(s=>s.kind==='final'),frames=Math.max(0,...final.map(s=>s.frame_count||s.images||s.videos||0)),images=media.reduce((n,s)=>n+(s.images||0)+(s.videos||0),0);
      const expected=config.mode==='STILL'?1:config.start!=null&&config.end!=null?Math.floor((config.end-config.start)/(config.step||1))+1:0;
      result.get(key).versions.push({run,sequences:media,frames,images,hasOutputs:images>0||(run.image_count||0)>0,expected,partial:frames>0&&expected>frames});
    }
    const rows=[...result.values()];
    for(const group of rows){
      group.versions.sort((a,b)=>(b.run.number||0)-(a.run.number||0)||String(b.run.created).localeCompare(String(a.run.created)));
      group.latest=group.versions.find(v=>v.hasOutputs)||group.versions[0];
      group.attempt=group.versions[0];
    }
    return rows.sort((a,b)=>(a.name+' '+a.source).localeCompare(b.name+' '+b.source,undefined,{numeric:true}));
  }
  function hasOutputs(project,folderId,folderInfo={}){
    return groups(project,folderId,folderInfo).length>0||scopedFolders(project,folderId).some(n=>(folderInfo[n.id]?.images||0)>0);
  }
  function signature(rows){
    return JSON.stringify(rows.map(g=>[g.key,g.name,g.source,g.versions.map(v=>[v.run.id,v.run.status,v.run.image_count,v.frames,v.images,v.run.finished])]));
  }
  const model={scopedFolders,setupKey,groups,hasOutputs,signature};
  if(typeof module==='object'&&module.exports)module.exports=model;else root.PipelineUI.outputModel=model;
})(globalThis);
