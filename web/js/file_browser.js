/* Standard Windows file/folder dialogs opened by the local desktop server. */
async function openPathBrowser(input,field){
 const folder=['parent','path'].includes(field.key),save=field.key==='destination';
 const mode=folder?'folder':save?'save':'file',extension=folder?'':field.key==='blender'?'.exe':save?'.zip':'.blend';
 const row=input.closest('.pathPicker'),browse=row?.querySelector('button');if(browse)browse.disabled=true;
 try{const chosen=await api('choose_system_path',{mode,extension,initial:input.value.trim()||state.root||''});if(chosen.path&&input.isConnected){input.value=chosen.path;input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));input.focus();}}
 catch(e){error(e);}finally{if(browse)browse.disabled=false;}
}
