/* Explicit lifecycle composition. Feature order is data, not captured globals. */
(function(root) {
  'use strict';
  function createRuntime(scheduler={
    setInterval:(callback,period)=>globalThis.setInterval(callback,period),
    clearInterval:timer=>globalThis.clearInterval(timer)
  }) {
    const channels = new Map();
    const backgroundTasks = new Map();
    function channel(name) {
      if (!channels.has(name)) channels.set(name, {base:null, extensions:[], compiled:null});
      return channels.get(name);
    }
    function define(name, implementation) {
      const entry=channel(name);
      if(entry.base) throw Error('UI lifecycle already defined: '+name);
      entry.base=implementation;entry.compiled=null;
    }
    function use(name, feature, order, implementation) {
      const entry=channel(name);
      if(entry.extensions.some(extension=>extension.feature===feature)) throw Error('Duplicate UI extension: '+name+'/'+feature);
      if(!Number.isFinite(order)||typeof implementation!=='function') throw Error('Invalid UI extension: '+feature);
      entry.extensions.push({feature,order,implementation});entry.compiled=null;
    }
    function call(name,...args) {
      const entry=channel(name);
      if(!entry.compiled) {
        if(!entry.base) throw Error('UI lifecycle has no base: '+name);
        entry.compiled=entry.extensions.slice().sort((a,b)=>a.order-b.order||a.feature.localeCompare(b.feature))
          .reduce((next,extension)=>(...values)=>extension.implementation(next,...values),entry.base);
      }
      return entry.compiled(...args);
    }
    function describe() {
      return [...channels].map(([name,entry])=>({name,defined:!!entry.base,
        extensions:entry.extensions.slice().sort((a,b)=>a.order-b.order).map(({feature,order})=>({feature,order}))}));
    }
    const store={};
    function connectState(accessors) {
      for(const [key,accessor] of Object.entries(accessors)) {
        if(Object.hasOwn(store,key)) throw Error('UI state already connected: '+key);
        Object.defineProperty(store,key,{enumerable:true,get:accessor.get,set:accessor.set});
      }
    }
    function background(name,period,callback) {
      if(backgroundTasks.has(name)) throw Error('Duplicate background task: '+name);
      if(!Number.isFinite(period)||period<=0||typeof callback!=='function') throw Error('Invalid background task: '+name);
      backgroundTasks.set(name,{period,callback,timer:null,running:false});
    }
    function startBackground(onError) {
      for(const task of backgroundTasks.values()) {
        if(task.timer!==null) continue;
        task.timer=scheduler.setInterval(async()=>{
          if(task.running) return;
          task.running=true;
          try {await task.callback();} catch(error) {onError(error);} finally {task.running=false;}
        },task.period);
      }
    }
    function stopBackground() {
      for(const task of backgroundTasks.values()) {
        if(task.timer!==null) scheduler.clearInterval(task.timer);
        task.timer=null;
      }
    }
    return {define,use,call,describe,store,connectState,background,startBackground,stopBackground};
  }
  if(typeof module==='object'&&module.exports) module.exports={createRuntime};
  else root.PipelineUI=createRuntime();
})(globalThis);
