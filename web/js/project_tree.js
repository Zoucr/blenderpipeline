/* Project-files tree controller. Folder creation and graph gestures live elsewhere. */
const ProjectTree=(function(){
  function create({store,navigator,controls,isOpen,el,button,muted,blenderIcon,problem,pick,focusNode,selection,repaint}){
    // Sidebar folds are independent of graph-frame collapse and never move files on disk.
    const navigatorFolds=new Map();let navigatorSelectionContext='';
    function paint(next){
      const {state,selected}=store;const navigatorOpen=isOpen();
      const scroll=navigator.scrollTop,focused=document.activeElement?.closest('.uxTreeLine')?.dataset.nodeId;
      next();if(!navigatorOpen||!state.project)return;
      const tree=navigator.querySelector('.uxTree');tree.replaceChildren();
      const project=state.project,query=controls.get('search').value.trim().toLowerCase(),nodes=project.nodes.filter(n=>!n.hidden),lookup=new Map(nodes.map(n=>[n.id,n])),children=new Map(),parents=new Map();
      if(!navigatorFolds.has(project.id))navigatorFolds.set(project.id,new Set());const folded=navigatorFolds.get(project.id);
      for(const n of nodes){const parent=lookup.get(n.group),key=parent?.type==='folder'&&parent.id!==n.id?parent.id:null;parents.set(n.id,key);if(!children.has(key))children.set(key,[]);children.get(key).push(n);}
      for(const siblings of children.values())siblings.sort((a,b)=>(b.type==='folder')-(a.type==='folder')||a.name.localeCompare(b.name,undefined,{numeric:true,sensitivity:'base'}));
      function ancestors(id){const result=[],seen=new Set([id]);for(let p=parents.get(id);p&&!seen.has(p);p=parents.get(p)){seen.add(p);result.push(p);}return result;}
      const context=project.id+':'+selected;
      if(context!==navigatorSelectionContext){ancestors(selected).forEach(id=>folded.delete(id));navigatorSelectionContext=context;}
      const included=new Set();
      function includeChildren(id){const pending=[id],seen=new Set();while(pending.length){const next=pending.pop();if(seen.has(next))continue;seen.add(next);included.add(next);for(const child of children.get(next)||[])pending.push(child.id);}}
      if(query)for(const n of nodes)if((n.name+' '+n.path+' '+(n.notes||'')).toLowerCase().includes(query)){
        if(n.type==='folder')includeChildren(n.id);else included.add(n.id);ancestors(n.id).forEach(id=>included.add(id));
      }
      function focusRow(id){[...tree.querySelectorAll('.uxFileRow')].find(row=>row.dataset.nodeId===id)?.focus({preventScroll:true});}
      function toggleFolder(id){if(query)return;folded.has(id)?folded.delete(id):folded.add(id);repaint();focusRow(id);}
      const root=el('ul',undefined,'uxTreeList'),shown=new Set();root.setAttribute('aria-label','Project node folders');tree.append(root);
      function add(n,list){
        if(shown.has(n.id)||query&&!included.has(n.id))return;shown.add(n.id);
        const item=el('li',undefined,'uxTreeItem'),line=el('div',undefined,'uxTreeLine'),kids=children.get(n.id)||[],folder=n.type==='folder',open=!!query||!folded.has(n.id);line.dataset.nodeId=n.id;
        if(folder&&kids.length){const toggle=button(open?'▾':'▸',()=>toggleFolder(n.id));toggle.className='uxTreeToggle';toggle.setAttribute('aria-label',(open?'Collapse ':'Expand ')+n.name);toggle.setAttribute('aria-expanded',String(open));toggle.title=query?'Search shows matching branches':(open?'Collapse folder list':'Expand folder list');toggle.disabled=!!query;line.append(toggle);}else line.append(el('span',undefined,'uxTreeToggleSpace'));
        const row=button('',e=>{ancestors(n.id).forEach(id=>folded.delete(id));if(e.shiftKey||e.ctrlKey||e.metaKey){pick(n.id,true);repaint();}else focusNode(n);});row.className='uxFileRow'+(selected===n.id?' active':'')+(selection.has(n.id)&&selection.size>1?' multiSelected':'');row.dataset.nodeId=n.id;row.dataset.color=n.color||'default';row.dataset.kind=n.type;row.setAttribute('aria-label',n.name);row.setAttribute('aria-current',selected===n.id?'true':'false');
        const trail=ancestors(n.id).reverse().map(id=>lookup.get(id).name);row.title='Graph: '+[project.name,...trail,n.name].join(' / ')+'\nDisk: '+n.path;
        // Folder headers currently use their fixed folder theme, independent of file colors.
        if(folder)row.dataset.color='default';
        const swatch=el('span',undefined,'uxTreeColor');swatch.setAttribute('aria-hidden','true');const icon=el('span',undefined,'uxFileIcon');icon.append(blenderIcon(folder?'file_folder':'file_blend'));row.append(swatch,icon,el('span',n.name,'uxTreeName'));
        if(folder){const count=el('span',String(kids.length),'uxTreeCount');count.title=`${kids.filter(c=>c.type==='folder').length} folders · ${kids.filter(c=>c.type==='blend').length} files directly inside`;row.append(count);}
        else if(problem(n)!=='Ready'){const alert=el('span','•','uxFileAlert');alert.title=problem(n);row.append(alert);}
        row.onkeydown=e=>{
          if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const rows=[...tree.querySelectorAll('.uxFileRow')],index=rows.indexOf(row);
          if(e.key==='ArrowLeft'){if(folder&&kids.length&&open&&!query)toggleFolder(n.id);else focusRow(parents.get(n.id));}
          else if(e.key==='ArrowRight'){if(folder&&kids.length&&!open)toggleFolder(n.id);else if(folder&&kids.length)focusRow(kids.find(c=>!query||included.has(c.id))?.id);}
          else rows[e.key==='Home'?0:e.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,index+(e.key==='ArrowDown'?1:-1)))]?.focus();
        };
        line.append(row);item.append(line);list.append(item);
        if(folder&&kids.length&&open){const branch=el('ul',undefined,'uxTreeBranch');branch.setAttribute('aria-label','Inside '+n.name);item.append(branch);for(const child of kids)add(child,branch);}
      }
      for(const n of children.get(null)||[])add(n,root);
      // Legacy orphan/cycle data must stay reachable, even if its graph grouping is invalid.
      const reachable=new Set();function visit(id){if(reachable.has(id))return;reachable.add(id);for(const child of children.get(id)||[])visit(child.id);}for(const n of children.get(null)||[])visit(n.id);
      for(const n of nodes)if(!reachable.has(n.id))add(n,root);
      if(!root.children.length)tree.append(muted(query?'No matching files or folders.':'Add a Blend File or folder to begin.'));
      const foot=navigator.querySelector('.uxNavigatorFoot');foot.append(el('div','Graph folders · disk paths in tooltips','uxTreeHint'));
      navigator.scrollTop=scroll;if(focused)focusRow(focused);
    }
  return {paint};
  }
  return {create};
})();
const projectTreeController=ProjectTree.create({
  store:PipelineUI.store,navigator,controls,isOpen:()=>navigatorOpen,
  el,button,muted,blenderIcon,problem,pick,focusNode,selection,repaint:paintNavigator
});
PipelineUI.use('paintNavigator','project-tree',1303,projectTreeController.paint);
