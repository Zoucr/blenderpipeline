/* Visible reported Blender sessions, independent of scan warnings or node stage. */
function reportedOpen(n){return n.type==='blend'&&((state.open||[]).includes(n.id)||liveSessions(n).length>0);}
function paintOpenFiles(){
  let geometryChanged=false;
  for(const n of state.project?.nodes||[]){const card=document.querySelector(`[data-id="${n.id}"]`);if(!card||n.type!=='blend')continue;const sessions=liveSessions(n),open=reportedOpen(n),dirty=sessions.some(s=>s.dirty);let marker=card.querySelector('.blenderSessionBadge');card.classList.toggle('blenderOpen',open);card.classList.toggle('blenderDirty',dirty);
    const snapshot=card.querySelector('.uxNodeActions [aria-label="Save snapshot"]');if(snapshot){snapshot.disabled=dirty;snapshot.title=dirty?'Save in Blender first; snapshots capture disk contents.':'Save snapshot';}
    if(!open){if(marker){marker.remove();geometryChanged=true;}continue;}
    if(!marker){marker=el('div',undefined,'blenderSessionBadge');marker.setAttribute('role','status');card.querySelector('header').after(marker);geometryChanged=true;}
    const text=(dirty?'Unsaved in Blender':'Open in Blender')+(sessions.length>1?' · '+sessions.length+' windows':'');if(marker.textContent!==text)marker.replaceChildren(blenderIcon(dirty?'status_warning':'file_blend'),el('span',text));marker.title=(sessions.length?'Reported by the Blender companion.':'Tracked window launched by this tool. Unsaved state requires the companion.')+' Close the file before changing it from this interface.';
  }
  if(geometryChanged){drawEdges();paintNavigator();}
}
PipelineUI.use('paintTasks','open-files',1100,function(next){next();paintOpenFiles();});
PipelineUI.use('render','open-files',1101,function(next){if(selected&&!state.project?.nodes.some(n=>n.id===selected)){selected=null;selectedConnection=null;selectedDataConnection=null;selection.clear();}next();paintOpenFiles();});

PipelineUI.use('run','protect-open-files',1102,function(next, action,args={}){const writes=['archive_blend','restore','relocate','adopt','organize','link','link_data','link_batch','prepare_materials','refresh_dependencies'];if(writes.includes(action)){const n=state.project?.nodes.find(n=>n.id===(args.target_id||args.node_id));if(n&&reportedOpen(n)){error('Close '+n.name+' in Blender before changing its saved file. The node is marked open.');return Promise.resolve();}}return next(action,args);});
const sessionMenu=nodeMenu;
nodeMenu=function(n,anchor){sessionMenu(n,anchor);if(reportedOpen(n)){const menu=$('contextMenu');for(const b of menu.querySelectorAll('button'))if(/Delete file|Move.*file|Locate.*file/i.test(b.textContent)){b.disabled=true;b.title='Close this file in Blender first.';}menu.append(muted('Open in Blender · saved-file edits are protected.'));}};
paintOpenFiles();

