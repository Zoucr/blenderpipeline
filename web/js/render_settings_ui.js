/* Saved RNA settings, grouped like Blender panels with one outer scrollbar. */
function advancedSettingsEditor(parent,scene,initial={},options={}){
  const values=structuredClone(initial),entries=(scene.advanced_settings||[]).filter(e=>!e.common),root=el('div',undefined,'rmAllSettings'),tools=el('div',undefined,'rmAdvancedTools'),search=el('input'),changed=el('input'),only=el('label','Overrides only'),list=el('div',undefined,'rmAdvancedList'),groups=new Map();
  search.placeholder='Find Blender setting…';search.setAttribute('aria-label','Search all Blender render settings');changed.type='checkbox';changed.setAttribute('aria-label','Show only changed Blender settings');only.prepend(changed);tools.append(search,only);root.append(tools,list);parent.append(root);
  const notify=()=>options.onchange?.();
  function rowFor(entry){
    const row=el('div',undefined,'rmRNASetting'),title=el('label'),enable=el('input'),controls=el('div',undefined,'rmRNAValue');enable.type='checkbox';enable.checked=entry.key in values;enable.disabled=!entry.editable;enable.setAttribute('aria-label','Override '+entry.category+' / '+entry.label);title.append(enable,el('span',entry.label));title.title=entry.description||entry.property;row.title=[entry.description,entry.reason].filter(Boolean).join('\n');row.append(title,controls);let read;
    function input(type,value,name=entry.label){const e=el('input');e.type=type;e.value=value??'';e.setAttribute('aria-label',entry.category+' / '+name);if(type==='number'){e.min=String(entry.min);e.max=String(entry.max);e.step=entry.type==='INT'?'1':'any';}controls.append(e);return e;}
    const value=values[entry.key]??entry.value;
    if(entry.array){const components=value.map((v,i)=>input(entry.type==='BOOLEAN'?'checkbox':entry.type==='STRING'?'text':'number',v,entry.label+' '+(i+1)));components.forEach((e,i)=>{if(entry.type==='BOOLEAN')e.checked=value[i];});read=()=>components.map(e=>entry.type==='BOOLEAN'?e.checked:entry.type==='STRING'?e.value:Number(e.value));}
    else if(entry.type==='BOOLEAN'){const e=input('checkbox','');e.checked=!!value;read=()=>e.checked;}
    else if(entry.type==='ENUM'&&entry.options?.length){const e=el('select');e.setAttribute('aria-label',entry.category+' / '+entry.label);e.multiple=!!entry.flags;const choices=[...entry.options];for(const saved of (entry.flags?value:[value]))if(!choices.some(o=>o.value===saved))choices.push({value:saved,label:String(saved)});for(const option of choices){const o=el('option',option.label);o.value=option.value;o.selected=entry.flags?value.includes(option.value):value===option.value;e.append(o);}controls.append(e);read=()=>entry.flags?[...e.selectedOptions].map(o=>o.value):e.value;}
    else{const e=input(['INT','FLOAT'].includes(entry.type)?'number':'text',entry.flags?value.join(','):value);read=()=>['INT','FLOAT'].includes(entry.type)?Number(e.value):entry.flags?e.value.split(',').map(v=>v.trim()).filter(Boolean):e.value;}
    function sync(){const enabled=entry.editable&&enable.checked;row.classList.toggle('enabled',enabled);for(const e of controls.querySelectorAll('input,select'))e.disabled=!enabled;row.dataset.origin=enabled?'Override':'Saved';}
    sync();enable.onchange=()=>{if(enable.checked)values[entry.key]=read();else delete values[entry.key];sync();updateCounts();notify();};controls.oninput=()=>{if(enable.checked){values[entry.key]=read();updateCounts();notify();}};return row;
  }
  function updateCounts(){for(const {summary,entries:items} of groups.values()){const count=items.filter(e=>e.key in values).length;summary.querySelector('small').textContent=count?count+' override'+(count===1?'':'s'):'';}}
  function draw(){
    list.replaceChildren();groups.clear();const query=search.value.trim().toLowerCase().replace(/_/g,' '),found=entries.filter(e=>(!changed.checked||e.key in values)&&[e.label,e.description,e.property,e.category].join(' ').replace(/_/g,' ').toLowerCase().includes(query));
    for(const category of [...new Set(found.map(e=>e.category))]){
      const items=found.filter(e=>e.category===category),box=renderPanel(category,(options.key||'rna')+':'+category,false),summary=box.querySelector('summary'),content=el('div',undefined,'rmCategoryFields');summary.append(el('small',''));box.classList.add('rmSettingGroup');box.append(content);let painted=false;
      function populate(){if(painted)return;painted=true;content.append(...items.map(rowFor));}
      const toggle=box.ontoggle;box.ontoggle=()=>{toggle();if(box.open)populate();};if(query||changed.checked)box.open=true;if(box.open)populate();list.append(box);groups.set(category,{summary,entries:items});
    }
    for(const key of Object.keys(values).filter(k=>!entries.some(e=>e.key===k))){const warning=el('div',undefined,'warning');warning.append(el('span','Unavailable override'),button('Remove',()=>{delete values[key];draw();notify();}));warning.title=key;list.append(warning);}
    if(!found.length)list.append(muted(entries.length?'No matching settings':'No additional settings in the saved file'));
    updateCounts();
  }
  search.oninput=changed.onchange=draw;draw();return {root,read:()=>structuredClone(values)};
}
function lazyRenderSettings(parent,initial,loader,key,onchange=()=>{}){
  const root=el('div',undefined,'rmSettingsCatalogue');parent.append(root);let editor=null,loading=null,values=structuredClone(initial||{});
  async function load(){
    if(editor||loading)return loading;
    root.replaceChildren(el('span','Loading Blender settings…','muted'));
    loading=(async()=>{try{const entries=await loader();if(!root.isConnected)return;root.replaceChildren();editor=advancedSettingsEditor(root,{advanced_settings:entries},values,{key,onchange});}catch(e){root.replaceChildren(button('Retry loading settings',()=>{loading=null;load();}));root.title=String(e);}})();return loading;
  }
  return {root,load,read:()=>editor?editor.read():structuredClone(values)};
}
function renderSettingsCatalogue(parent,initial,loader,key,onchange=()=>{}){
  const panel=renderPanel('More Blender settings',key+':catalogue',false);parent.append(panel);
  const editor=lazyRenderSettings(panel,initial,loader,key,onchange),toggle=panel.ontoggle;
  panel.ontoggle=()=>{toggle();if(panel.open)editor.load();};
  if(panel.open)editor.load();return {...editor,panel};
}
