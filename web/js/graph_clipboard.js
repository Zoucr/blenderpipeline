/* Graph clipboard owns selection; the backend copies saved files and remaps IDs. */
(function(){
  const kind='blender-pipeline/nodes',storageKey='pipeline.graphClipboard';
  let clipboard;
  try{clipboard=JSON.parse(sessionStorage.getItem(storageKey)||'null');}catch{}
  function available(){return !!state.project&&!busy&&!window.pipelineBusy()&&!document.querySelector('dialog[open]')&&!document.activeElement?.matches('textarea,select,input:not([readonly]),[contenteditable=true]');}
  function manifest(){const ids=[...selection].filter(id=>state.project.nodes.some(n=>n.id===id&&!n.hidden));return ids.length?{kind,version:1,project_id:state.project.id,node_ids:ids}:null;}
  function remember(value){clipboard=value;sessionStorage.setItem(storageKey,JSON.stringify(value));}
  function decode(text){try{const value=JSON.parse(text);return value.kind===kind&&value.version===1&&Array.isArray(value.node_ids)&&value.node_ids.length<=200?value:null;}catch{return null;}}
  async function copySelection(){
    if(!available())return;
    const value=manifest();if(!value)return;
    remember(value);
    try{await navigator.clipboard.writeText(JSON.stringify(value));}catch{/* The local clipboard still supports keyboard/menu paste. */}
    status('Copied '+value.node_ids.length+' node'+(value.node_ids.length===1?'':'s')+' · paste copies the saved files');
  }
  async function pasteSelection(p=null,value=null){
    if(!available())return;
    if(!value){try{value=decode(await navigator.clipboard.readText());}catch{value=clipboard;}}
    if(!value)return error('Copy nodes from this project first.');
    if(value.project_id!==state.project.id)return error('Copied nodes belong to another project. Copy nodes from this project first.');
    return run('paste_nodes',{node_ids:value.node_ids,clipboard_project_id:value.project_id,...(p||lastPoint||placement())});
  }
  document.addEventListener('copy',e=>{if(!available())return;const value=manifest();if(!value)return;e.preventDefault();remember(value);e.clipboardData.setData('text/plain',JSON.stringify(value));status('Copied '+value.node_ids.length+' nodes');});
  document.addEventListener('paste',e=>{if(!available())return;const value=decode(e.clipboardData.getData('text/plain'));if(!value)return;e.preventDefault();remember(value);pasteSelection(null,value);});
  document.addEventListener('keydown',e=>{
    if(!(e.ctrlKey||e.metaKey)||e.altKey||!available())return;
    const key=e.key.toLowerCase();
    if(key==='c'){e.preventDefault();e.stopImmediatePropagation();copySelection();}
    if(key==='v'){e.preventDefault();e.stopImmediatePropagation();pasteSelection();}
    if(key==='d'&&selection.size){e.preventDefault();e.stopImmediatePropagation();run('paste_nodes',{node_ids:[...selection],clipboard_project_id:state.project.id});}
  },true);
  PipelineUI.use('run','pasted-node-selection',2400,async function(next,action,args){
    const before=new Set((state.project?.nodes||[]).map(n=>n.id)),result=await next(action,args);
    if(['paste_nodes','duplicate'].includes(action)&&result?.project?.id===state.project?.id){
      const added=result.project.nodes.filter(n=>!before.has(n.id));
      if(added.length){selection.clear();for(const n of added)selection.add(n.id);selected=added[0].id;render();reveal(added[0]);}
    }
    return result;
  });
  window.PipelineClipboard={copySelection,pasteSelection,canPaste:()=>clipboard?.project_id===state.project?.id};
})();
