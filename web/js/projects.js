/* Full searchable library; compact recents remain in the Project menu. */
const libraryDialog=el('dialog');libraryDialog.id='projectLibrary';document.body.append(libraryDialog);
projectList.insertBefore(button('Manage projects',openProjectLibrary),recentList);
let libraryQuery='',librarySort='recent',removedProject=null;
const archiveMenu=nodeMenu;
nodeMenu=function(n,anchor){
  archiveMenu(n,anchor);
  if(n.type==='blend'&&!n.external)$('contextMenu').append(button('Delete file → archive',()=>{
    modal('Archive '+n.name+'?',[{key:'closed',type:'checkbox',required:true,label:'I saved and closed this file in every Blender window'}],v=>run('archive_blend',{node_id:n.id,...v}));
    $('fields').append(muted('Delete this node and move its working file into the project archive? You can restore it later from Project → Archived files. Snapshot history is kept.'));
    $('submit').textContent='Archive file';
  }));
  polishInterface();
};
projectList.insertBefore(button('Archived files',openArchivedFiles),recentList);
function openArchivedFiles(){modal('Archived files',[],()=>{});$('submit').textContent='Close';const records=state.project?.archived_files||[];if(!records.length){$('fields').append(muted('No archived files in this project.'));return;}$('fields').append(muted('Restores the file to its original path with its node and snapshot history. The original path must be free.'));for(const record of [...records].reverse()){const row=section(record.node.name,el('p',record.node.path,'uxPath'),muted(new Date(record.archived_at).toLocaleString()),button('Restore file',()=>{$('dialog').close();run('restore_archived',{archive_id:record.id});}));$('fields').append(row);}}
async function openProjectLibrary(){
  libraryDialog.replaceChildren();const head=el('h3','Projects');libraryDialog.append(head);
  const toolbar=actions(button('New project',()=>{libraryDialog.close();controls.get('newProject').click();}),button('Open existing folder',()=>{libraryDialog.close();controls.get('openProject').click();}));
  const search=el('input');search.placeholder='Find project by name or location';search.setAttribute('aria-label','Find project');search.value=libraryQuery;
  const sort=el('select');sort.setAttribute('aria-label','Project sort');for(const [value,label] of [['recent','Recently opened'],['name','Name']]){const o=el('option',label);o.value=value;sort.append(o);}sort.value=librarySort;
  const filters=el('div',undefined,'libraryFilters');filters.append(search,sort);const list=el('div',undefined,'libraryEntries'),feedback=el('p',undefined,'muted');feedback.setAttribute('role','status');libraryDialog.append(toolbar,filters,list,feedback,actions(button('Close',()=>libraryDialog.close())));
  let entries=[];
  async function refresh(){try{entries=(await api('projects')).projects;state.recent=entries;paint();}catch(e){feedback.textContent=e.message;}}
  function paint(){libraryQuery=search.value;librarySort=sort.value;list.replaceChildren();const query=libraryQuery.toLowerCase(),found=entries.filter(r=>(r.name+' '+r.path).toLowerCase().includes(query));found.sort((a,b)=>Number(!!b.pinned)-Number(!!a.pinned)||(librarySort==='name'?a.name.localeCompare(b.name):entries.indexOf(a)-entries.indexOf(b)));
    for(const r of found){const row=el('div',undefined,'libraryEntry'),info=el('div',undefined,'libraryInfo'),name=el('strong',r.name);info.append(name,el('p',r.path,'uxPath'));if(r.path===state.root)info.append(badge('Current','good'));if(!r.available)info.append(badge('Folder missing','danger'));const pin=button(r.pinned?'Unpin':'Pin',async()=>{await change('pin',r);},r.pinned?'Unpin project':'Pin project');row.append(info,actions(pin,button('Open',()=>{libraryDialog.close();run('load',{path:r.path});}),button('Remove',async()=>{await change('remove',r);},'Remove from library; files stay on disk')));row.querySelectorAll('button')[1].disabled=!r.available;list.append(row);}
    feedback.replaceChildren(el('span',found.length+' of '+entries.length+' projects · pinned projects appear first. Removing an entry keeps its files on disk.'));if(removedProject)feedback.append(button('Undo removal',async()=>{try{await api('projects',{mode:'restore',entry:removedProject});removedProject=null;await refresh();render();}catch(e){feedback.textContent=e.message;}}));if(!found.length)list.append(muted(entries.length?'No matching projects.':'Create a project or open an existing project folder.'));polishInterface();
  }
  async function change(mode,r){try{await api('projects',{mode,path:r.path});if(mode==='remove')removedProject=r;await refresh();render();}catch(e){feedback.textContent=e.message;}}
  search.oninput=paint;sort.onchange=paint;if(!libraryDialog.open)libraryDialog.showModal();await refresh();search.focus();
}
