/* Folder organization and output browsing use graph coordinates, never guessed paths. */
function frameAncestors(n){const out=[],seen=new Set([n.id]);while(n.group){const f=state.project.nodes.find(f=>f.id===n.group);if(!f||seen.has(f.id))break;seen.add(f.id);out.push(f);n=f;}return out;}
function inFrame(n,id){return frameAncestors(n).some(f=>f.id===id);}
function topSelection(){return state.project.nodes.filter(n=>selection.has(n.id)&&!n.hidden&&!frameAncestors(n).some(f=>selection.has(f.id)));}
visibleNodes=function(){return (state.project?.nodes||[]).filter(n=>!n.hidden&&!frameAncestors(n).some(f=>f.hidden||f.collapsed));};
emptyCanvas=function(e){const card=e.target.closest('.node');return !e.target.closest('path,#welcome')&&(!card||((card.classList.contains('folder')||card.classList.contains('frame'))&&!e.target.closest('header,button,.port,.frameResize,.folderContents')));};
const folderFocus=focusNode;focusNode=function(n){for(const f of frameAncestors(n))if(f.collapsed||f.hidden)editGraph(f,{collapsed:false,hidden:false});folderFocus(n);};

function createFolderHere(p,parent=null,around=false){
  const chosen=around?topSelection():[];
  if(parent&&!chosen.length){const f=state.project.nodes.find(n=>n.id===parent),children=state.project.nodes.filter(n=>n.group===parent&&!n.hidden);p={x:f.x+28,y:Math.max(f.y+125,...children.map(n=>n.y+(document.querySelector(`[data-id="${n.id}"]`)?.offsetHeight||n.height||260)+35))};var width=350,height=240;}
  if(chosen.length){
    const shared=chosen[0].group||null;parent=chosen.every(n=>(n.group||null)===shared)?shared:null;
    const bounds=chosen.map(n=>{const c=document.querySelector(`[data-id="${n.id}"]`);return {x:n.x,y:n.y,w:c?.offsetWidth||260,h:c?.offsetHeight||260};});
    p={x:Math.min(...bounds.map(b=>b.x))-28,y:Math.min(...bounds.map(b=>b.y))-125};
    var width=Math.max(...bounds.map(b=>b.x+b.w))-p.x+28,height=Math.max(...bounds.map(b=>b.y+b.h))-p.y+40;
  }
  modal(chosen.length?'Add Folder Around Selected Nodes':'Add Folder',[
    {key:'title',label:'Folder name',value:'',help:'Leave blank for an automatic Folder 001 name.'},
    {...folderField(),label:'Create physical folder inside',value:parent||'',options:folders().filter(f=>!chosen.some(n=>n.id===f.value||inFrame(state.project.nodes.find(n=>n.id===f.value)||{},n.id)))}
  ],v=>run('folder',{title:v.title||null,folder_id:v.folder_id||null,node_ids:chosen.map(n=>n.id),...p,width:width||650,height:height||420}));
  $('fields').append(muted(chosen.length?'Groups the selected nodes automatically. Existing files keep their current disk paths.':'Creates a real directory and an organizational frame.'));
}
controls.get('addFolder').onclick=()=>{const n=state.project?.nodes.find(n=>n.id===selected);createFolderHere(placement(),n?.type==='folder'?n.id:null,selection.size>1);};
function deleteFolder(n){modal('Delete folder '+n.name+'?',[],()=>run('archive_folder',{node_id:n.id,confirmed:true}));$('fields').append(muted('Remove this folder frame? Empty folders move to the archive. Existing files, subfolders and renders stay on disk. Grouped nodes move out of the frame and render output connections to it are cleared. Restore through Project → Archived files.'));$('submit').textContent='Delete folder';}
window.pipelineGroupDrop=function(e){
  if(move?.type!=='node'||Math.hypot(e.clientX-move.x,e.clientY-move.y)<4)return;
  const roots=topSelection(),groups={};
  for(const n of roots){
    const anchorX=n.x+(['folder','frame'].includes(n.type)?(n.width||650)/2:119);
    const candidate=visibleNodes().filter(f=>['folder','frame'].includes(f.type)&&f.id!==n.id&&!inFrame(f,n.id)&&!roots.some(r=>r.id===f.id||inFrame(f,r.id))&&!f.collapsed&&anchorX>f.x&&anchorX<f.x+(f.width||650)&&n.y+15>f.y+28&&n.y+15<f.y+(f.height||420)).sort((a,b)=>frameAncestors(b).length-frameAncestors(a).length||((a.width||650)*(a.height||420)-(b.width||650)*(b.height||420)))[0];
    const group=candidate?.id||null;if(group!==(n.group||null))groups[n.id]=group;
  }
  if(Object.keys(groups).length){for(const n of state.project.nodes)if(n.id in groups)n.group=groups[n.id];run('group_nodes',{groups});}
};
function renderPrefix(scene){const d=new Date(),pad=n=>String(n).padStart(2,'0');return pad(d.getFullYear()%100)+pad(d.getMonth()+1)+pad(d.getDate())+'_'+scene.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/[ .]+$/g,'')+'_';}
configureRender=function(n,folderId){
  const scenes=(n.scan?.scenes||[]).filter(s=>!s.linked);if(!scenes.length)return error('Refresh this file before configuring renders.');
  const config=n.render_config||{},scene=scenes.find(s=>s.name===config.scene)||scenes[0],options=folders().filter(f=>f.value);if(!options.length)return error('Add an output Folder first.');
  const automatic=config.auto_prefix??(!config.prefix||config.prefix==='render');
  modal('Render output',[
    {key:'folder_id',label:'Output folder',type:'select',options,value:folderId||config.folder_id||options[0].value},
    {key:'scene',label:'Scene',type:'select',options:scenes.map(s=>({label:s.name,value:s.name})),value:scene.name},
    {key:'camera',label:'Camera',type:'select',options:scene.cameras.map(c=>({label:c,value:c})),value:config.camera||scene.camera||scene.cameras[0]||''},
    {key:'start',label:'First frame',type:'number',value:config.start??scene.start,required:true},
    {key:'end',label:'Last frame',type:'number',value:config.end??scene.start,required:true},
    {key:'percentage',label:'Resolution percentage',type:'number',value:config.percentage||100,required:true},
    {key:'auto_prefix',label:'Use current date and scene name automatically',type:'checkbox',value:automatic},
    {key:'prefix',label:'Filename prefix',value:automatic?renderPrefix(scene.name):config.prefix,required:true}
  ],v=>run('render_config',{node_id:n.id,...v}));
  const preview=el('p',undefined,'renderPathPreview');$('fields').append(preview);
  const update=()=>{const s=scenes.find(s=>s.name===$('field-scene').value);if($('field-auto_prefix').checked)$('field-prefix').value=renderPrefix(s.name);$('field-prefix').readOnly=$('field-auto_prefix').checked;const f=state.project.nodes.find(f=>f.id===$('field-folder_id').value),frame=String($('field-start').value).padStart(4,'0'),stem=n.path.split('/').pop().replace(/\.blend$/i,''),runs=(state.project.renders||[]).filter(r=>r.node_id===n.id&&r.output.startsWith((f?.path||'')+'/')),number=Math.max(0,...runs.map(r=>r.number))+1;preview.textContent=`Example: ${f?.path||''}/${stem}_r${String(number).padStart(3,'0')}/${$('field-prefix').value}${frame}.png\nEach run gets its own numbered directory. The date updates when a render starts.`;};
  $('field-scene').onchange=()=>{const s=scenes.find(s=>s.name===$('field-scene').value);$('field-camera').replaceChildren();for(const c of s.cameras){const o=el('option',c);o.value=c;$('field-camera').append(o);}$('field-camera').value=s.camera||s.cameras[0]||'';update();};
  for(const id of ['folder_id','auto_prefix','prefix','start'])$('field-'+id).addEventListener('input',update);update();$('submit').textContent='Save output settings';
};
function folderRuns(n){return [...(state.project?.renders||[])].reverse().filter(r=>r.output===n.path||r.output.startsWith(n.path+'/'));}
function sequenceLabel(s){return (s.scene||s.prefix.replace(/_$/,''))+(s.view_layer?' / '+s.view_layer:'');}
function sequenceFrames(s){return s.videos?s.videos+' video'+(s.videos===1?'':'s'):s.ranges?.length?(s.frame_count===1?'Frame ':'Frames ')+RenderOverview.rangeLabel(s.ranges,s.step):s.images+' image'+(s.images===1?'':'s');}
function paintFolderContents(){
  for(const n of state.project?.nodes.filter(n=>n.type==='folder')||[]){
    const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;const info=state.folder_info?.[n.id]||{},sequences=RenderOverview.latestSequences(info),label=card.querySelector('.folderLabel'),children=state.project.nodes.filter(c=>c.group===n.id&&!c.hidden).length;
    if(label)label.textContent=[children?children+' nodes':'',sequences.length?sequences.length+' rendered setups':'',info.images?info.images+(info.truncated?'+':'')+' images':''].filter(Boolean).join(' · ')||(info.missing?'Folder missing':'Empty folder');
    const imageFolder=!!(info.images||info.videos||folderRuns(n).length||(typeof folderHasRendering==='function'&&folderHasRendering(n)));
    let panel=card.querySelector('.folderContents');if(!panel){panel=el('div',undefined,'folderContents');card.append(panel);}const signature=JSON.stringify([n.collapsed,imageFolder,info]);if(panel.dataset.signature===signature)continue;panel.dataset.signature=signature;panel.replaceChildren();
    let browse=card.querySelector('.folderImagesButton');
    if(n.collapsed||!imageFolder)browse?.remove();
    else if(!browse){browse=button('Outputs',()=>showFolderContents(n),'View latest renders, frames and older versions');browse.classList.add('folderImagesButton');const tools=card.querySelector('.folderTools');tools.insertBefore(browse,tools.querySelector('.rmFolderButton'));}
    if(!n.collapsed){
      if(info.missing||info.error)panel.append(el('div',info.error||'Folder missing','warning'));
      else if(sequences.length){
        const scenes=RenderOverview.sceneSummaries(info),visible=scenes.length>2?scenes.slice(0,1):scenes;
        for(const scene of visible){const first=scene.sequences[0],row=el('div',undefined,'folderSceneRow'),meta=(scene.same?sequenceFrames(first):[scene.images?scene.images+' images':'',scene.videos?scene.videos+' videos':''].filter(Boolean).join(' · '))+(scene.layers>1?' · '+scene.layers+' layers':'');row.append(el('span',scene.name,'folderSceneName'),el('span',meta,'folderSceneMeta'));if(scene.partial){row.classList.add('partial');row.append(el('small','Partial','folderSceneState'));}row.title=scene.sequences.map(s=>sequenceLabel(s)+' · '+sequenceFrames(s)+(s.expected_frames&&s.frame_count<s.expected_frames?' · '+s.frame_count+'/'+s.expected_frames+' frames saved':'')+'\n'+s.directory).join('\n');panel.append(row);}
        if(scenes.length>2)panel.append(button('+'+(scenes.length-1)+' more scenes',()=>showFolderContents(n),'Browse all rendered scenes'));
      }else if(!children&&imageFolder)panel.append(el('div',info.images?'Compositor · '+info.images+' images':info.videos?info.videos+' videos':'No images yet','folderImagesEmpty'));
    }
  }
}
function folderListing(n){
  const info=state.folder_info?.[n.id]||{},box=el('div',undefined,'folderSequenceOverview'),sequences=RenderOverview.latestSequences(info);
  if(info.error||info.missing){box.append(muted(info.error||'Folder missing'));return box;}
  for(const s of sequences){const row=el('div',undefined,'folderSequenceRow'),title=el('strong',sequenceLabel(s)),description=el('small',sequenceFrames(s));row.append(title,description);if(s.version)row.append(badge('r'+String(s.version).padStart(3,'0')));if(s.expected_frames&&s.frame_count<s.expected_frames)row.append(el('small',s.frame_count+'/'+s.expected_frames+' saved','warning'));row.title=s.directory;box.append(row);}
  if(!sequences.length)box.append(muted('No rendered images in this folder'));
  const compositor=(info.sequences||[]).filter(s=>s.kind==='compositor');
  if(compositor.length){const passes=renderPanel('Compositor outputs · '+compositor.reduce((n,s)=>n+s.images,0)+' images','passes:'+n.id,false);for(const s of compositor)passes.append(el('div',s.prefix.replace(/_$/,'')+' · '+sequenceFrames(s),'folderDiskEntry'));box.append(passes);}
  if(info.truncated)box.append(muted('Showing a partial scan. Open folder for all output files.'));
  return box;
}
function showFolderContents(n){
  PipelineUI.outputs.open(n.id);
}
function folderDetailTabs(n){
  const tabs=el('div',undefined,'uxTabs folderDetailTabs'),items=[['folder','Folder']],active=folderRenderingTab?.id===n.id?folderRenderingTab.key:'folder';
  if(folderHasRendering(n))items.push(['render','Rendering']);
  if(folderHasRendering(n)||PipelineUI.outputModel.hasOutputs(state.project,n.id,state.folder_info))items.push(['outputs','Outputs']);
  tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Folder details');
  tabs.hidden=items.length===1;
  for(const [key,label] of items){const b=button(label,()=>{folderRenderingTab={id:n.id,key};inspect();});b.classList.toggle('active',key===active);b.setAttribute('role','tab');b.setAttribute('aria-selected',String(key===active));b.tabIndex=key===active?0:-1;tabs.append(b);}return tabs;
}
PipelineUI.use('render','nested-folders',1300,function(next){next();for(const n of state.project?.nodes||[]){const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;if(frameAncestors(n).some(f=>f.hidden||f.collapsed)){card.remove();continue;}const depth=frameAncestors(n).length;card.style.zIndex=['folder','frame'].includes(n.type)?String(depth+1):'100';if(n.type==='folder'&&card.querySelector('.frameResize'))card.querySelector('.frameResize').onpointerup=()=>{move=null;drawEdges();run('graph_edit',{node_id:n.id,group:n.group||null,width:n.width,height:n.height});};}paintFolderContents();drawEdges();});
PipelineUI.use('paintTasks','folder-contents',1301,function(next){next();paintFolderContents();});
PipelineUI.use('inspect','folder-details',1302,function(next){next();const n=state.project?.nodes.find(n=>n.id===selected);if(n?.type!=='folder')return;const pane=$('inspector');const images=renderPanel('Images','images:'+n.id,true);images.append(folderListing(n),button('Browse versions',()=>showFolderContents(n)));pane.append(images);const parent=el('select');parent.setAttribute('aria-label','Parent folder frame');for(const option of [{value:'',label:'No parent frame'},...state.project.nodes.filter(f=>['folder','frame'].includes(f.type)&&f.id!==n.id&&!f.hidden&&!inFrame(f,n.id)).map(f=>({value:f.id,label:f.name}))]){const o=el('option',option.label);o.value=option.value;parent.append(o);}parent.value=n.group||'';parent.onchange=()=>run('group_nodes',{groups:{[n.id]:parent.value||null}});const organization=renderPanel('Organization','organization:'+n.id,false);organization.append(parent,button('Add Folder inside',()=>createFolderHere({x:n.x+30,y:n.y+120},n.id)),button('Delete folder…',()=>deleteFolder(n)));organization.title=n.path;pane.append(organization);});
const folderArchives=openArchivedFiles;openArchivedFiles=function(){folderArchives();const records=state.project?.archived_folders||[];if(records.length){for(const p of $('fields').querySelectorAll('p'))if(p.textContent==='No archived files in this project.')p.remove();$('fields').append(muted('Folder recovery restores the frame and surviving members. Populated folders remain on disk.'));}for(const r of [...records].reverse())$('fields').append(section('Folder · '+r.node.name,muted(r.node.path),button('Restore folder',()=>{$('dialog').close();run('restore_folder',{archive_id:r.id});})));};
// Existing menu callback binds the former function; replace only that action.
for(const b of projectList.querySelectorAll('button'))if(b.textContent.trim()==='Archived files')b.onclick=openArchivedFiles;
const navigatorResize=el('div');navigatorResize.id='navigatorResize';navigatorResize.title='Drag to resize project files';navigatorResize.setAttribute('role','separator');navigatorResize.setAttribute('aria-label','Resize project files');navigatorResize.setAttribute('aria-orientation','vertical');navigatorResize.tabIndex=0;document.body.append(navigatorResize);
function setNavigatorWidth(w){const max=Math.min(520,Math.max(160,innerWidth-450));document.documentElement.style.setProperty('--navigator-width',Math.max(160,Math.min(max,w))+'px');}
navigatorResize.onpointerdown=e=>{e.preventDefault();navigatorResize.setPointerCapture(e.pointerId);};navigatorResize.onpointermove=e=>{if(navigatorResize.hasPointerCapture(e.pointerId))setNavigatorWidth(e.clientX);};navigatorResize.onpointerup=rememberPanels;navigatorResize.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();setNavigatorWidth(parseInt(getComputedStyle(document.documentElement).getPropertyValue('--navigator-width'))+(e.key==='ArrowRight'?20:-20));rememberPanels();}};
const panelsRead=api('ui_preferences',{read:true});panelsRead.then(p=>{if(p.navigator_width)setNavigatorWidth(p.navigator_width);}).catch(error);
// Keep hierarchy intact when arranging: folders are containers, not separate top-level lanes.
const flatArrange=arrangeGraph;arrangeGraph=function(){
  if(!state.project)return;if(!state.project.nodes.some(n=>['folder','frame'].includes(n.type)))return flatArrange();rememberLayout(layoutState());
  const nodes=state.project.nodes.filter(n=>!n.hidden),rankCache=new Map();
  function rank(n,seen=new Set()){if(rankCache.has(n.id))return rankCache.get(n.id);if(seen.has(n.id))return 0;seen.add(n.id);const incoming=nodes.filter(s=>s.type==='blend'&&s.id!==n.id&&connectionItems(s,n).length),r=incoming.length?1+Math.max(...incoming.map(s=>rank(s,new Set(seen)))):0;rankCache.set(n.id,r);return r;}
  function arrangeLevel(parent,x,y){let bottom=y,right=x;const children=nodes.filter(n=>(n.group||null)===parent),files=children.filter(n=>!['folder','frame'].includes(n.type)).sort((a,b)=>rank(a)-rank(b));for(let i=0;i<files.length;i++){const n=files[i],c=document.querySelector(`[data-id="${n.id}"]`);n.x=x+(i%3)*290;n.y=y+Math.floor(i/3)*300;right=Math.max(right,n.x+(c?.offsetWidth||260));bottom=Math.max(bottom,n.y+(c?.offsetHeight||260));}let cursor=files.length?bottom+35:y;for(const f of children.filter(n=>['folder','frame'].includes(n.type))){f.x=x;f.y=cursor;const size=arrangeLevel(f.id,x+28,cursor+125);f.width=Math.max(350,size.right-x+28);f.height=Math.max(240,size.bottom-cursor+28);right=Math.max(right,f.x+f.width);bottom=Math.max(bottom,f.y+f.height);cursor=bottom+35;}return {right,bottom};}
  arrangeLevel(null,50,50);for(const f of nodes.filter(n=>['folder','frame'].includes(n.type)))run('graph_edit',{node_id:f.id,group:f.group||null,width:f.width,height:f.height});render();persist();controls.get('frame').click();status('Arranged within nested folders · Ctrl Z undoes layout');
};
for(const b of viewList.querySelectorAll('button'))if(b.textContent.trim()==='Arrange by dependency')b.onclick=arrangeGraph;
$('hint').textContent='Left-drag to select · Shift-click adds · Middle-drag to pan · Right-click to add nodes · Wheel to zoom';
const oldShortcuts=showShortcuts;showShortcuts=function(){oldShortcuts();for(const p of $('fields').querySelectorAll('p'))p.textContent=p.textContent.replace('Shift-drag canvas — box select','Left-drag canvas — box select (Shift adds)');};
if(state.project)render();
