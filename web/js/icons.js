/* Official Blender SVGs served locally. Labels remain accessible and explicit. */
function blenderIcon(name){const span=el('span',undefined,'blIcon');span.style.setProperty('--icon-url',`url('/icons/${name}.svg')`);span.setAttribute('aria-hidden','true');return span;}
function actionIcon(text){const t=text.toLowerCase();if(t.includes('collection'))return 'outliner_collection';if(t.includes('template'))return 'file_new';if(t.includes('snapshot')||t.includes('checkpoint')||t.includes('backup'))return 'file_backup';if(t.includes('refresh')||t.includes('reload'))return 'file_refresh';if(t.includes('queue'))return 'render_animation';if(t.includes('render')||t.includes('output'))return 'render_still';if(t.includes('duplicate'))return 'duplicate';if(t.includes('unlink')||t.includes('remove from graph'))return 'unlinked';if(t.includes('link')||t.includes('external')||t.includes('dependenc'))return 'linked';if(t.includes('folder'))return 'file_folder';if(t.includes('new project')||t.includes('create')||t.startsWith('add ')||t.startsWith('＋'))return 'add';if(t.includes('settings')||t.includes('preferences'))return 'preferences';if(t.includes('preflight')||t.includes('check project'))return 'checkmark';if(t.includes('frame')||t.includes('zoom')||t.includes('highlight'))return 'zoom_all';if(t.includes('blender')||t.includes('blend file'))return 'file_blend';if(t.includes('history')||t.includes('saved states'))return 'time';if(t.includes('files')||t.includes('navigator'))return 'outliner';if(t.includes('commands')||t.includes('find')||t.includes('search'))return 'viewzoom';if(t.includes('restore')||t.includes('adopt'))return 'back';if(t.includes('move')||t.includes('rename')||t.includes('label'))return 'filebrowser';if(t==='cancel'||t==='dismiss')return 'cancel';if(t==='confirm'||t==='done')return 'checkmark';if(t==='link')return 'linked';return null;}
function decorateControl(b){
  if(b.id==='quickGuide'||b.closest('#renderManager .rmTabs'))return;
  const text=b.textContent.trim(),label=b.getAttribute('aria-label')||b.title||text;
  if(!text&&b.dataset.iconName&&b.querySelector('.blIcon'))return;
  if(b.classList.contains('uxFileRow')||b.classList.contains('browserEntry'))return;
  let name=actionIcon(label),only=false;
  if(text.startsWith('History'))name='time';
  if(text.includes('Materials / node groups'))name='node_material';
  if(b.getAttribute('role')==='tab')name=({File:'file_blend',Assets:'node_material',History:'time',Render:'render_still',Links:'linked',Collections:'outliner_collection'})[text]||name;
  if(b.classList.contains('uxHistoryToggle'))name='time';
  if(b.id==='toggleNavigator'){name='outliner';only=true;}
  if(b.classList.contains('uxNodeMenu')){name='collapsemenu';only=true;}
  if(label==='Save snapshot'&&b.closest('.uxNodeActions')){name='file_backup';only=true;}
  if(label==='Refresh node'||label==='Refresh this node only'){name='file_refresh';only=true;}
  if(text==='☆'||text==='★'){name=text==='★'?'pinned':'unpinned';only=true;b.setAttribute('aria-pressed',String(text==='★'));}
  if(text==='▾'||text==='▸'){name=text==='▾'?'downarrow_hlt':'rightarrow';only=true;}
  if(!name)return;
  if(b.dataset.iconName===name&&b.querySelector('.blIcon')&&b.dataset.iconLabel===text)return;
  b.dataset.iconName=name;b.classList.add('iconControl');b.classList.toggle('iconOnly',only);
  if(only){b.setAttribute('aria-label',label);b.title=label;b.replaceChildren(blenderIcon(name));b.dataset.iconLabel='';}
  else{const clean=text.replace(/^[＋↻◈◇▧▣▸▾⋯]+\s*/u,'');b.replaceChildren(blenderIcon(name),el('span',clean,'controlLabel'));b.dataset.iconLabel=clean;}
}
function polishInterface(){
  for(const b of document.querySelectorAll('button'))decorateControl(b);
  for(const heading of document.querySelectorAll('#inspector>.uxInspectorHeading')){
    const marker=heading.querySelector('.uxEyebrow');
    if(marker&&!marker.querySelector('.blIcon')){
      const kind=marker.textContent.trim(),label=kind==='FOLDER'?'Folder':kind==='PROJECT'?'Project':'Blend file';
      marker.title=label;marker.setAttribute('role','img');marker.setAttribute('aria-label',label);
      marker.replaceChildren(blenderIcon(kind==='FOLDER'?'file_folder':kind==='PROJECT'?'nodetree':'file_blend'));
    }
    const title=heading.querySelector('h3');if(title)title.title=title.textContent;
  }
  for(const summary of document.querySelectorAll('#topbar .uxDropdown>summary')){const raw=summary.textContent.trim(),label=raw.replace(/^[＋◈]+\s*/u,''),name=label==='Project'?'file_blend':label==='View'?'nodetree':'add';if(!summary.querySelector('.blIcon'))summary.replaceChildren(blenderIcon(name),el('span',label),blenderIcon('downarrow_hlt'));}
  for(const n of state.project?.nodes||[]){const card=document.querySelector(`[data-id="${n.id}"]`);if(!card)continue;const header=card.querySelector('header');const marker=[...header.children].find(c=>c.tagName==='SPAN'&&!c.classList.contains('blIcon'));if(marker&&!marker.querySelector('.blIcon'))marker.replaceChildren(blenderIcon(n.type==='folder'?'file_folder':n.external?'linked':'file_blend'));}
  for(const row of document.querySelectorAll('.uxFileRow')){const marker=row.querySelector('.uxFileIcon');if(marker&&!marker.querySelector('.blIcon'))marker.replaceChildren(blenderIcon(row.title.toLowerCase().endsWith('.blend')?'file_blend':'file_folder'));}
  for(const heading of document.querySelectorAll('.uxSection h4')){if(heading.querySelector('.blIcon'))continue;const name=actionIcon(heading.textContent);if(name)heading.prepend(blenderIcon(name));}
}
const iconMenu=nodeMenu,iconModal=modal;
PipelineUI.use('render','blender-icons',700,function(next){next();polishInterface();});
PipelineUI.use('inspect','blender-icons',701,function(next){next();polishInterface();});
nodeMenu=function(...args){iconMenu(...args);polishInterface();};
modal=function(...args){iconModal(...args);polishInterface();};
PipelineUI.use('paintNavigator','blender-icons',702,function(next){next();polishInterface();});
// Render polling and browser rows can replace controls without rebuilding the whole graph.
let iconScheduled=false;const iconObserver=new MutationObserver(records=>{if(iconScheduled||!records.some(r=>[...r.addedNodes].some(n=>n.nodeType===1&&!n.classList.contains('blIcon')&&!n.classList.contains('controlLabel'))))return;iconScheduled=true;requestAnimationFrame(()=>{iconScheduled=false;polishInterface();});});
iconObserver.observe(document.body,{childList:true,subtree:true});
polishInterface();
