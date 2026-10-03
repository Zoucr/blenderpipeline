/* Start only after every UI feature has registered its lifecycle extensions. */
run('state').finally(()=>PipelineUI.startBackground(error));
window.addEventListener('pagehide',()=>PipelineUI.stopBackground());
window.addEventListener('pageshow',event=>{if(event.persisted)PipelineUI.startBackground(error);});
