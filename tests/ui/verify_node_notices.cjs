const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
function element(text=''){
  const classes=new Set();return {textContent:text,children:[],dataset:{},attributes:{},classList:{toggle(k,on){on?classes.add(k):classes.delete(k);},contains:k=>classes.has(k)},
    append(...children){for(const child of children){this.children.push(child);child.parent=this;}},replaceChildren(...children){this.children=[];this.append(...children);},
    setAttribute(k,v){this.attributes[k]=v;},remove(){this.parent.children=this.parent.children.filter(c=>c!==this);}};
}
const card=element(),footer=element('Unused image notices');card.querySelector=selector=>selector==='.nodeStatus'?footer:card.children.find(c=>c.className?.includes('dependencyBadge'));
const state={project:{id:'project',nodes:[{id:'source',name:'Scene file',type:'blend'}],renders:[{id:'run',status:'Complete',node_id:'source',config:{scene:'Scene'},output:'Outputs/r001'}]},
  health:{nodes:{source:{reasons:[{kind:'image_notice',source_id:'source',message:'1 unused missing image'}]}},outputs:{renders:{run:{outdated:true,changed_inputs:['Scene.blend']}}}}};
let paint,picked,opened=false;
const details={open:false,scrollIntoView(){opened=true;}};
const context=vm.createContext({state,problem:()=>'',renderRunEntry:()=>element(),paintVersionList:()=>{},
  document:{querySelector:()=>card},$:()=>({querySelector:()=>details}),inspectorOpen:false,inspectorToggle:{click(){}},pick:id=>picked=id,
  blenderIcon:icon=>({icon}),button:(label,click)=>Object.assign(element(label),{onclick:click}),
  PipelineUI:{use:(_stage,name,_priority,handler)=>{if(name==='dependency-badges')paint=handler;}}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/js/dependency_status.js'),'utf8'),context);
paint(()=>{});const shield=card.children[0];assert.equal(card.children.length,1);assert.equal(shield.children[0].icon,'warning_shield');
assert.equal(shield.textContent,'','persistent notices contain an icon, not a full-width text button');
assert(shield.title.includes('Unused image notices')&&shield.title.includes('Outputs outdated')&&shield.title.includes('Scene.blend'),'hover combines all relevant notice categories');
assert(shield.attributes['aria-label'].includes('Open dependencies'));assert(footer.hidden);assert(card.classList.contains('hasDependencyNotice'));
paint(()=>{});assert.equal(card.children[0],shield,'polling updates metadata without replacing the icon');
shield.onclick();assert.equal(picked,'source');assert(details.open&&opened,'clicking opens the dependency explanation');
state.health.outputs.renders.run.outdated=false;paint(()=>{});assert.equal(shield.dataset.severity,'notice');
state.health.nodes.source.reasons=[];paint(()=>{});assert.equal(card.children.length,0);assert(!footer.hidden);assert(!card.classList.contains('hasDependencyNotice'));
state.health.nodes.source.reasons=[{kind:'missing',source_id:'source'}];paint(()=>{});assert.equal(card.children[0].dataset.severity,'danger');

const overviewSource=fs.readFileSync(path.join(__dirname,'../../web/js/clarity.js'),'utf8'),pane=element(),panels=[];
const overviewState={project:{id:'p',name:'Project',nodes:[{id:'a',type:'blend',last_error:true},{id:'h',type:'blend',hidden:true}],renders:[{status:'Complete'}]},
  root:'/project',jobs:[{id:'failed',status:'Failed',error:'Error',action:'create'}],desktop_warning:'Launch locally'};
const noop=()=>{};
const overviewContext=vm.createContext({state:overviewState,$:()=>pane,heading:()=>element(),outputTargets:()=>[{id:'op:a',source_id:'a'},{id:'op:b',source_id:'a'}],
  savedAssets:()=>[{}],problem:()=> 'Needs review',muted:element,el:(_tag,text)=>element(text),actions:(...items)=>{const row=element();row.append(...items);return row;},button:label=>element(label),
  renderPanel:(title,key,open)=>{const panel=element();panel.isDisclosure=true;panel.title=title;panel.key=key;panel.open=open;panels.push(panel);return panel;},
  section:()=>{throw Error('Project overview regions must be collapsible');},openArchivedFiles:noop,templateManager:noop,showCompanionGuide:noop,quickGuide:noop});
vm.runInContext(overviewSource.slice(overviewSource.indexOf('function projectOverview('),overviewSource.indexOf('function folderOverview(')),overviewContext);
overviewContext.projectOverview();assert.equal(pane.children.length,8);assert(pane.children.slice(1).every(child=>child.isDisclosure));
assert(panels.some(p=>p.title==='Rendering · 2 setups'));assert(panels.find(p=>p.key==='project-workspace').open);assert(!panels.find(p=>p.key==='project-desktop').open);
console.log('PASS: compact accessible warning shields preserve hover/click details and clear on resolution; all project overview regions are collapsible');
