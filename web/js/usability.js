/* Preserve navigation context through background refreshes. Preferences stay local. */
let restoringPanels=false,panelPreferenceTimer;
function rememberPanels(){if(restoringPanels)return;clearTimeout(panelPreferenceTimer);panelPreferenceTimer=setTimeout(()=>api('ui_preferences',{navigator:navigatorOpen,inspector:inspectorOpen,navigator_width:Math.max(160,Math.min(520,parseInt(getComputedStyle(document.documentElement).getPropertyValue('--navigator-width'),10)||220)),width:Math.max(290,Math.min(600,parseInt(getComputedStyle(document.documentElement).getPropertyValue('--inspector-width'),10)||360))}).catch(error),150);}
api('ui_preferences',{read:true}).then(saved=>{if(typeof saved.navigator!=='boolean')return;restoringPanels=true;try{if(saved.navigator!==navigatorOpen)navButton.click();if(saved.inspector!==inspectorOpen)inspectorToggle.click();if(saved.width>=290&&saved.width<=600)document.documentElement.style.setProperty('--inspector-width',saved.width+'px');}finally{restoringPanels=false;}}).catch(error);
navButton.addEventListener('click',rememberPanels);inspectorToggle.addEventListener('click',rememberPanels);resizeHandle.addEventListener('pointerup',rememberPanels);
const inspectorPositions=new Map();
let inspectorContext=null;
let personalViewSignature='';
PipelineUI.use('inspect','personal-view',1800,function(next){
  next();if(!state.project)return;
  const signature=JSON.stringify([state.project.id,selected,inspectorTab]);
  if(signature===personalViewSignature)return;personalViewSignature=signature;
  const context={project_id:state.project.id,selected,tab:inspectorTab};
  api('project_view',context).catch(error);
});

PipelineUI.use('inspect','inspector-position',800,function(next){
  const pane=$('inspector');if(inspectorContext)inspectorPositions.set(inspectorContext,pane.scrollTop);
  const key=[state.project?.id,selected,selectedConnection?.source,selectedConnection?.target,inspectorTab].join(':');
  next();inspectorContext=key;pane.scrollTop=inspectorPositions.get(key)||0;
  const tabs=[...pane.querySelectorAll('[role=tab]')];
  for(const tab of tabs){tab.tabIndex=tab.getAttribute('aria-selected')==='true'?0:-1;tab.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const index=tabs.indexOf(tab),next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next].click();pane.querySelector('[role=tab][aria-selected=true]')?.focus();};}
});
// Background updates should not jump a collection or history list back to its top.
$('inspector').addEventListener('scroll',()=>{if(inspectorContext)inspectorPositions.set(inspectorContext,$('inspector').scrollTop);},{passive:true});
const usablePolish=polishInterface;
polishInterface=function(){usablePolish();for(const b of document.querySelectorAll('button')){if(b.title==='Expand children'||b.title==='Collapse children'||b.title==='Collapse folder frame'||b.title==='Expand folder frame')b.setAttribute('aria-expanded',String(b.title.startsWith('Collapse')));}}
inspect();polishInterface();
