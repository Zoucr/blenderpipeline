// Exercise the production pointer handlers: left selects, middle pans over nodes too.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const workspace={setPointerCapture(){},append(){},onpointerdown:null},menu={hidden:false};
const c=vm.createContext({$:id=>id==='workspace'?workspace:menu,state:{project:{}},move:null,view:{x:4,y:8},adding:false,box:null,emptyCanvas:e=>!e.onNode,placeAt(){},worldPoint:(x,y)=>({x,y}),el:()=>({})});
function handler(file){const source=fs.readFileSync(require('node:path').join(__dirname,'../../web/js',file),'utf8'),start=source.indexOf("$('workspace').onpointerdown=e=>{"),end=source.indexOf("$('workspace').onpointermove=",start);assert(start>=0&&end>start);return source.slice(start,end);}
vm.runInContext(handler('ui.js'),c);c.previousDown=workspace.onpointerdown;
const event=(button,onNode=false,shiftKey=false)=>({button,onNode,shiftKey,ctrlKey:false,clientX:10,clientY:20,pointerId:1,preventDefault(){},stopPropagation(){}});
workspace.onpointerdown(event(0));assert.equal(c.move,null);
workspace.onpointerdown(event(1,true));assert.equal(c.move.type,'pan');assert.equal(c.move.ox,4);
c.move=null;vm.runInContext(handler('workspace.js'),c);
workspace.onpointerdown(event(0));assert(c.box);assert.equal(c.move,null);assert.equal(c.box.additive,false);
c.box=null;workspace.onpointerdown(event(0,false,true));assert.equal(c.box.additive,true);
c.box=null;workspace.onpointerdown(event(1,true));assert.equal(c.move.type,'pan');assert.equal(c.box,null);
console.log('PASS: production pointer handlers keep left-drag selection separate from middle-only panning, including panning over nodes and additive box selection');
