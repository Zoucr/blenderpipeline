/* Shared saved-file hierarchy. Selection uses datablock identity, expansion uses paths. */
(function(root){
  const key=d=>JSON.stringify([d.kind,d.name]);
  const sort=(a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true,sensitivity:'base'});
  function build(scan,assets){
    const collections=new Map(assets.filter(d=>d.kind==='collections').map(d=>[d.name,d]));
    const objects=new Map(assets.filter(d=>d.kind==='objects').map(d=>[d.name,d]));
    const objectInfo=new Map();
    for(const o of scan.objects||[])if(!objectInfo.has(o.name)||o.editable)objectInfo.set(o.name,o);
    const usedObjects=new Set(),usedCollections=new Set();
    function objectRows(names,path){
      const available=new Set(names.filter(name=>objects.has(name))),children=new Map(),visited=new Set();
      for(const name of available){const parent=objectInfo.get(name)?.parent;if(parent&&parent!==name&&available.has(parent)){if(!children.has(parent))children.set(parent,[]);children.get(parent).push(name);}}
      function visit(name,ancestors){
        if(ancestors.has(name))return null;
        visited.add(name);const next=new Set(ancestors);next.add(name);const asset=objects.get(name);
        return {id:path+'/'+key(asset),name,asset,children:(children.get(name)||[]).sort((a,b)=>sort(objects.get(a),objects.get(b))).map(child=>visit(child,next)).filter(Boolean)};
      }
      const roots=[...available].filter(name=>{const parent=objectInfo.get(name)?.parent;return !available.has(parent)||parent===name;}).sort((a,b)=>sort(objects.get(a),objects.get(b)));
      const rows=roots.map(name=>visit(name,new Set()));
      for(const name of available)if(!visited.has(name))rows.push(visit(name,new Set()));
      return rows.filter(Boolean);
    }
    function collectionRow(name,path,ancestors){
      if(ancestors.has(name)||!collections.has(name))return null;
      usedCollections.add(name);const next=new Set(ancestors);next.add(name);const asset=collections.get(name),id=path+'/'+key(asset);
      const children=(asset.children||[]).filter(child=>collections.has(child));
      // Older scans have recursive members only. Fresh scans preserve multi-membership.
      const nested=new Set(children.flatMap(child=>collections.get(child).members||[]));
      const members=asset.direct_members||((asset.members||[]).filter(member=>!nested.has(member)));
      members.forEach(member=>usedObjects.add(member));
      return {id,name,asset,children:[...children.sort((a,b)=>sort(collections.get(a),collections.get(b))).map(child=>collectionRow(child,id,next)).filter(Boolean),...objectRows(members,id)]};
    }
    const nested=new Set([...collections.values()].flatMap(c=>c.children||[]));
    const roots=[...collections.values()].filter(c=>!nested.has(c.name)).sort(sort).map(c=>collectionRow(c.name,'collections',new Set()));
    for(const c of [...collections.values()].sort(sort))if(!usedCollections.has(c.name))roots.push(collectionRow(c.name,'collections',new Set()));
    const sections=[];
    if(roots.length)sections.push({id:'collections',name:'Collections',children:roots.filter(Boolean)});
    const loose=objectRows([...objects.keys()].filter(name=>!usedObjects.has(name)),'objects');
    if(loose.length)sections.push({id:'objects',name:'Scene / ungrouped objects',children:loose});
    const labels={materials:'Materials',node_groups:'Node groups',worlds:'Worlds',actions:'Actions'};
    for(const kind of [...new Set(assets.filter(d=>!['collections','objects'].includes(d.kind)).map(d=>d.kind))]){
      const id='data:'+kind;sections.push({id,name:labels[kind]||kind.replaceAll('_',' '),children:assets.filter(d=>d.kind===kind).sort(sort).map(asset=>({id:id+'/'+key(asset),name:asset.name,asset,children:[]}))});
    }
    return sections;
  }
  function rows(tree,{expanded=new Set(['collections','objects']),query='',kind='all',allowedKinds=null}={}){
    const q=query.trim().toLowerCase(),filtering=!!q||kind!=='all';
    function prune(node,parentMatch=false){
      const textMatch=!q||node.name.toLowerCase().includes(q)||parentMatch;
      const allowed=!node.asset||!allowedKinds||allowedKinds.has(node.asset.kind);
      const match=!!node.asset&&allowed&&textMatch&&(kind==='all'||node.asset.kind===kind);
      const children=node.children.map(child=>prune(child,!!q&&textMatch)).filter(Boolean);
      if(!node.asset&&!children.length)return null;
      if((filtering||!allowed)&&!match&&!children.length)return null;
      return {...node,match,children};
    }
    const output=[];
    function visit(node,depth){const open=filtering||expanded.has(node.id);output.push({...node,depth,open,expandable:!!node.children.length});if(open)for(const child of node.children)visit(child,depth+1);}
    for(const node of tree){const filtered=prune(node);if(filtered)visit(filtered,0);}
    return output;
  }
  const api={key,build,rows};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.PipelineAssetTree=api;
})(typeof window==='object'?window:globalThis);
