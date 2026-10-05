/* One compact collection browser for the inspector and the multi-link picker. */
const contentTreeViews=new Map();
function assetTreeView(){return {expanded:new Set(['collections','objects']),query:'',limit:200};}
function savedContentAssets(node){
  const assets=savedAssets(node),known=new Set(assets.map(PipelineAssetTree.key));
  function add(asset){const key=PipelineAssetTree.key(asset);if(!known.has(key)){known.add(key);assets.push(asset);}}
  for(const collection of node.scan?.content_collections||[])add({...collection,kind:'collections'});
  for(const object of node.scan?.objects||[]){
    add({...object,kind:'objects',object_type:object.type,linked:!object.editable});
    for(const slot of object.material_slots||[])if(slot.material)add({name:slot.material,kind:'materials',linked:true});
  }
  return assets;
}
function createAssetBrowser(container,node,assets,view,options={}){
  const tree=PipelineAssetTree.build(node.scan||{},assets);
  container.classList.add('assetTree');
  let visible=[];
  function paint(){
    const rows=PipelineAssetTree.rows(tree,{expanded:view.expanded,query:view.query,kind:options.kind?.()||'all',allowedKinds:options.allowedKinds?.()||null});
    container.replaceChildren();visible=rows.slice(0,view.limit);options.count?.(visible.filter(r=>r.asset&&r.match).length);
    for(const item of visible){
      const row=el('div',undefined,'assetTreeRow'+(!options.onChoose?' contentsItem':''));row.style.paddingLeft=(5+item.depth*13)+'px';
      const d=item.asset,flags=d?(options.flags?.(d)||{}):{};
      row.classList.toggle('treeSection',!d);row.classList.toggle('selected',!!flags.checked);row.classList.toggle('unavailable',!!flags.disabled);row.classList.toggle('context',!!d&&!item.match);
      if(item.expandable){
        const toggle=button(item.open?'▾':'▸',()=>{if(view.expanded.has(item.id))view.expanded.delete(item.id);else view.expanded.add(item.id);paint();},(item.open?'Collapse ':'Expand ')+item.name);
        toggle.className='treeToggle';toggle.setAttribute('aria-label',(item.open?'Collapse ':'Expand ')+item.name);toggle.setAttribute('aria-expanded',String(item.open));toggle.disabled=!!view.query.trim()||(options.kind?.()||'all')!=='all';row.append(toggle);
      }else row.append(el('span',undefined,'treeSpacer'));
      const label=el(options.onChoose&&d?'label':'div',undefined,'treeLabel');
      if(options.onChoose&&d){const check=el('input');check.type='checkbox';check.checked=!!flags.checked;check.disabled=!!flags.disabled||!item.match;check.setAttribute('aria-label',d.name+' · '+assetLabel(d));check.onchange=()=>options.onChoose(d,check.checked);label.append(check);}
      label.append(blenderIcon(d?assetIcon(d):'outliner_collection'),el('span',item.name,'treeName'));row.title=d?assetLabel(d)+' · '+d.name:item.name;
      row.append(label);
      const hint=flags.hint||(d?.kind==='collections'?d.objects+' object'+(d.objects===1?'':'s')+(d.linked?' · linked':''):d?assetLabel(d)+(d.linked?' · linked':''):item.children.length+' item'+(item.children.length===1?'':'s'));
      row.append(el('small',hint));
      if(options.pin&&d?.kind==='collections'&&!d.linked){
        const pinned=(node.pinned_collections||[]).includes(d.name),pin=button(pinned?'★':'☆',()=>options.pin(d,pinned),(pinned?'Unpin ':'Pin ')+d.name);pin.className='treePin';pin.setAttribute('aria-label',(pinned?'Unpin ':'Pin ')+d.name);row.append(pin);
      }
      container.append(row);
    }
    if(rows.length>view.limit){const more=button('Show '+Math.min(200,rows.length-view.limit)+' more · '+(rows.length-view.limit)+' remaining',()=>{view.limit+=200;paint();});more.className='assetTreeMore';container.append(more);}
    if(!rows.length)container.append(el('p','No matching saved contents.','assetTreeEmpty'));
  }
  function tools(){
    const bar=el('div',undefined,'assetTreeTools');bar.append(el('span','Collection hierarchy'),button('Expand all',()=>{function open(nodes){for(const item of nodes){if(item.children.length)view.expanded.add(item.id);open(item.children);}}open(tree);paint();}),button('Collapse all',()=>{view.expanded.clear();view.expanded.add('collections');view.expanded.add('objects');view.limit=200;paint();}));return bar;
  }
  return {paint,tools,visibleAssets:()=>visible.filter(row=>row.asset&&row.match).map(row=>row.asset)};
}
